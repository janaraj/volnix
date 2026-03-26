## E2c Phase 3: Webhook Event Delivery — Inbound Event Simulation

Saves to: `internal_docs/plans/E2c-phase3-webhook-delivery.md`

### Context

Phase 1-2 handle outbound agent requests (agent → Terrarium). Phase 3 handles INBOUND events (Terrarium → agent). When the animator generates "new email arrived" or "payment failed", the webhook module pushes these to the agent's registered endpoints — simulating real service webhooks (Gmail Pub/Sub, Slack Events API, Stripe webhooks, etc.).

**Architecture**: WebhookManager is a **bus subscriber** — it listens to events on the EXISTING event bus and delivers matching ones via HTTP POST. Zero changes to existing code paths. If disabled or no webhooks registered, zero impact.

**How real webhook shapes are known**: Each service pack defines its webhook payload format alongside existing schemas. Built-in formatters exist for email (Gmail Pub/Sub shape), chat (Slack Events API shape). For unknown services, raw Terrarium event format is used. Adding a new format = one function + one registry line.

**Current state**: 2265 tests, 1 failed (Google), 0 xfails.

---

### Architecture

```
terrarium/
  webhook/
    __init__.py
    config.py           ← WebhookConfig (frozen Pydantic)
    registry.py         ← WebhookSubscription storage + pattern matching
    payloads.py         ← Service-specific payload formatters (plugin pattern)
    delivery.py         ← Async HTTP POST with retry + HMAC signing
    manager.py          ← Orchestrator: bus subscriber → match → format → deliver
```

**Event flow** (additive — existing flows unchanged):

```
Existing (unchanged):
  Animator → Pipeline → Commit → Bus.publish(event)
    → AgencyEngine (internal actors react)
    → WebSocket streaming (connected clients see events)

NEW (Phase 3 — bus subscriber):
  Bus.publish(event)
    → WebhookManager._on_event()
      → registry.match(event_type, service_id)     # find matching webhooks
      → payloads.format(event, service)             # service-specific shape
      → delivery.send(url, payload, secret)         # httpx POST with retry
```

**Design rules**:
- WebhookManager subscribes to bus wildcard `"*"` (same pattern as WebSocket endpoint at `http_rest.py:160`)
- Zero changes to engines, pipeline, gateway, adapters, or packs
- Module disabled by default (`enabled = false` in config)
- Pattern matching uses `fnmatch.fnmatch()` — standard library, no regex
- Delivery is fully async via `httpx.AsyncClient`
- Each delivery attempt has its own timeout (default 10s)
- 4xx responses = don't retry (client error). 5xx = retry with backoff
- Optional HMAC-SHA256 signature per webhook for payload verification

---

### Component 1: WebhookConfig (`webhook/config.py`)

```python
class WebhookConfig(BaseModel, frozen=True):
    """Configuration for webhook event delivery."""
    enabled: bool = False
    max_retries: int = 3
    retry_backoff_base: float = 1.0   # seconds, doubles each retry
    delivery_timeout: float = 10.0    # per-request timeout
    max_registrations: int = 100      # prevent unbounded growth
```

**Wire into**: `config/schema.py` → `TerrariumConfig.webhook` field. `terrarium.toml` → `[webhook]` section.

---

### Component 2: WebhookRegistry (`webhook/registry.py`)

```python
class WebhookSubscription(BaseModel, frozen=True):
    """A registered webhook endpoint."""
    id: str                           # UUID
    url: str                          # e.g., http://agent:3000/hooks/gmail
    events: list[str]                 # patterns: ["world.email_*", "world.gmail_*"]
    service: str = ""                 # optional: match by service_id
    secret: str = ""                  # optional: HMAC signing secret
    created_at: str = ""
    active: bool = True


class WebhookRegistry:
    def __init__(self, max_registrations: int = 100) -> None:
        self._subscriptions: dict[str, WebhookSubscription] = {}

    def register(self, sub: WebhookSubscription) -> str:
        """Register. Returns subscription ID. Raises if at max."""

    def unregister(self, sub_id: str) -> bool:
        """Remove by ID. Returns True if found."""

    def match(self, event_type: str, service_id: str = "") -> list[WebhookSubscription]:
        """Find matching subscriptions using fnmatch glob patterns.
        Also matches by service filter if configured on the subscription."""

    def list_all(self) -> list[WebhookSubscription]:
        """All active subscriptions."""
```

**Pattern matching**: `fnmatch.fnmatch(event_type, pattern)` for each pattern in `sub.events`. Example: `"world.email_*"` matches `"world.email_send"`.

---

### Component 3: Payload Formatters (`webhook/payloads.py`)

Plugin pattern — same as `DRIFT_SOURCE_REGISTRY` and `SIGNAL_REGISTRY`.

```python
# Registry: service_name → formatter function
PAYLOAD_FORMATTERS: dict[str, Callable] = {}

def format_payload(event: Any, service: str = "") -> dict[str, Any]:
    """Format event for delivery. Uses service-specific formatter if available."""
    formatter = PAYLOAD_FORMATTERS.get(service)
    if formatter:
        return formatter(event)
    return _default_format(event)

def _default_format(event) -> dict:
    """Terrarium event envelope — used when no service formatter."""
    return {
        "source": "terrarium",
        "event_type": getattr(event, "event_type", "unknown"),
        "event_id": str(getattr(event, "event_id", "")),
        "timestamp": str(getattr(event, "timestamp", "")),
        "data": event.model_dump(mode="json") if hasattr(event, "model_dump") else {},
    }

def _gmail_format(event) -> dict:
    """Gmail Pub/Sub notification shape."""
    import base64, json
    data = event.model_dump(mode="json") if hasattr(event, "model_dump") else {}
    return {
        "message": {
            "data": base64.b64encode(json.dumps(data).encode()).decode(),
            "messageId": str(getattr(event, "event_id", "")),
            "publishTime": str(getattr(event, "timestamp", "")),
        },
        "subscription": "terrarium-simulated",
    }

def _slack_format(event) -> dict:
    """Slack Events API shape."""
    return {
        "type": "event_callback",
        "token": "terrarium-simulated",
        "event": {
            "type": getattr(event, "action", "message"),
            "ts": str(getattr(event, "timestamp", "")),
        },
    }

# Built-in formatters
PAYLOAD_FORMATTERS["email"] = _gmail_format
PAYLOAD_FORMATTERS["gmail"] = _gmail_format
PAYLOAD_FORMATTERS["chat"] = _slack_format
PAYLOAD_FORMATTERS["slack"] = _slack_format
```

**Adding a new formatter**: One function + one line. Same pattern as drift sources and signal collectors.

---

### Component 4: Webhook Delivery (`webhook/delivery.py`)

```python
class DeliveryResult(BaseModel, frozen=True):
    success: bool
    attempts: int
    status_code: int = 0
    error: str = ""

class WebhookDelivery:
    def __init__(self, max_retries=3, backoff_base=1.0, timeout=10.0): ...

    async def send(self, url, payload, secret="") -> DeliveryResult:
        """POST payload to url with retry on 5xx. No retry on 4xx.
        If secret provided, adds X-Terrarium-Signature HMAC header."""
        for attempt in range(self._max_retries + 1):
            try:
                headers = {"Content-Type": "application/json"}
                if secret:
                    headers["X-Terrarium-Signature"] = self._sign(payload, secret)
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code < 400:
                    return DeliveryResult(success=True, ...)
                if resp.status_code < 500:
                    return DeliveryResult(success=False, ...)  # 4xx: no retry
            except Exception as exc:
                if attempt == self._max_retries:
                    return DeliveryResult(success=False, error=str(exc))
            await asyncio.sleep(self._backoff_base * (2 ** attempt))
```

---

### Component 5: WebhookManager (`webhook/manager.py`)

```python
class WebhookManager:
    """Bus subscriber that delivers matching events to registered webhooks."""

    def __init__(self, config: WebhookConfig): ...
    async def start(self, bus) -> None:
        """Subscribe to bus wildcard."""
        if self._config.enabled:
            await bus.subscribe("*", self._on_event)

    async def stop(self) -> None:
        """Unsubscribe."""

    async def _on_event(self, event) -> None:
        """Bus callback: match → format → deliver."""
        matches = self._registry.match(event_type, service_id)
        for sub in matches:
            payload = format_payload(event, service=sub.service or service_id)
            result = await self._delivery.send(sub.url, payload, sub.secret)
            # Track stats

    # Public API (called by HTTP endpoints):
    def register(self, url, events, service="", secret="") -> str
    def unregister(self, sub_id) -> bool
    def list_webhooks(self) -> list[dict]
    def get_stats(self) -> dict
```

---

### Component 6: HTTP API Endpoints

Add to `http_rest.py` (4 endpoints):

```python
POST   /api/v1/webhooks          → register webhook
DELETE /api/v1/webhooks/{id}     → unregister webhook
GET    /api/v1/webhooks          → list registered webhooks
GET    /api/v1/webhooks/stats    → delivery statistics
```

---

### Component 7: App Wiring (`app.py`)

```python
# After bus is created and initialized:
from terrarium.webhook.config import WebhookConfig
if self._config.webhook.enabled:
    from terrarium.webhook.manager import WebhookManager
    self._webhook_manager = WebhookManager(self._config.webhook)
    await self._webhook_manager.start(self._bus)
```

Pass to HTTP adapter via gateway or direct attribute.

---

### TOML Config

```toml
[webhook]
enabled = false
max_retries = 3
retry_backoff_base = 1.0
delivery_timeout = 10.0
max_registrations = 100
```

---

### Test Harness

**Directory**: `tests/webhook/` (NEW)

**`tests/webhook/conftest.py`**: Shared fixtures for all webhook tests.

| File | Tests | What (happy + failure + edge) |
|------|-------|------|
| `test_registry.py` | 7 | register, unregister, match exact, match wildcard, match service, max limit reached, list all |
| `test_delivery.py` | 6 | success, 4xx no retry, 5xx retry, timeout, HMAC signature, max retries exhausted |
| `test_payloads.py` | 5 | default format, gmail format, slack format, unknown service defaults, custom formatter |
| `test_manager.py` | 5 | start subscribes to bus, event delivered, no match skipped, stop unsubscribes, stats tracking |
| `test_api.py` | 4 | register endpoint, unregister endpoint, list endpoint, register with empty URL rejected |
| **Total** | **27** | |

---

### Documentation

After implementation:
1. Save plan: `internal_docs/plans/E2c-phase3-webhook-delivery.md`
2. Update `IMPLEMENTATION_STATUS.md`
3. Update master roadmap: mark G9/G10 done

---

### Implementation Order

```
1. webhook/config.py + TerrariumConfig + terrarium.toml
   → Verify config loads
2. webhook/registry.py + test_registry.py
   → Run tests, verify
3. webhook/payloads.py + test_payloads.py
   → Run tests, verify
4. webhook/delivery.py + test_delivery.py
   → Run tests, verify
5. webhook/manager.py + test_manager.py
   → Run tests, verify
6. HTTP endpoints in http_rest.py + test_api.py
   → Run tests, verify
7. App wiring in app.py
   → Run full suite
8. Documentation
```

### Verification

```bash
uv run pytest tests/webhook/ -v  # 27 tests
uv run pytest tests/ --ignore=tests/live --ignore=tests/integration -q
# Target: 2292+ passed, 0 xfails

# Manual E2E test:
# Terminal 1: Start terrarium with webhook enabled
uv run terrarium serve world.yaml --port 8080

# Terminal 2: Start a simple webhook receiver
python -c "
from fastapi import FastAPI; import uvicorn
app = FastAPI()
@app.post('/hooks/test')
async def hook(data: dict):
    print(f'Received: {data}')
    return {'ok': True}
uvicorn.run(app, port=9999)
"

# Terminal 3: Register webhook + trigger event
curl -X POST http://localhost:8080/api/v1/webhooks \
  -H "Content-Type: application/json" \
  -d '{"url": "http://localhost:9999/hooks/test", "events": ["world.*"]}'
# Now any world event should POST to localhost:9999
```
