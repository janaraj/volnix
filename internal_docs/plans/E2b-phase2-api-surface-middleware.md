## E2b Phase 2: API Surface Middleware — Auth, Status Codes, URL Prefixes

Saves to: `internal_docs/plans/E2b-phase2-api-surface-middleware.md`

### Context

The core API simulation is ALREADY DONE (Phase E1). Routes are mounted at real API paths (`/gmail/v1/messages`, `/v1/payment_intents`, `/rest/api/3/issue`). Request parsing works. Response shapes match real APIs. What's missing is making Terrarium BEHAVE like a real API server: auth checking, proper HTTP status codes, and service-prefixed URLs.

These are cross-cutting concerns — they apply to ALL routes via middleware, not per-service code.

**Current state**: 2242 tests, 1 failed (Google), 0 xfails.

---

### Architecture

```
terrarium/
  middleware/
    __init__.py
    auth.py              ← G8: Auth token shape validation
    status_codes.py      ← G7a: Map response errors to HTTP status codes
    prefix_router.py     ← G7b: Mount service-prefixed URL aliases
    config.py            ← Middleware config model (frozen Pydantic)
```

**Request flow** (all middleware is optional, configurable):
```
Client request
  → CORS middleware (existing, line 71 of http_rest.py)
  → AuthMiddleware (NEW — validates token shape)
  → Route handler (EXISTING — pack handler or generic action)
  → StatusCodeMiddleware (NEW — maps error body to HTTP status)
  → Client response
```

**Design rules**:
- All middleware is OFF by default (backward compatible)
- Service-specific rules are DATA (TOML config), not CODE
- Middleware module has ZERO imports from engines/packs/gateway
- Only standard Starlette/FastAPI middleware patterns

---

### Component 1: MiddlewareConfig (`middleware/config.py`)

**File**: `terrarium/middleware/config.py` (NEW)

```python
class MiddlewareConfig(BaseModel, frozen=True):
    """Configuration for API surface middleware."""
    auth_enabled: bool = False
    status_codes_enabled: bool = True
    prefixes_enabled: bool = False
    auth_rules: dict[str, str] = Field(default_factory=dict)
    # key = service name, value = regex pattern for Authorization header
    # e.g., {"stripe": "Bearer sk_.*", "slack": "Bearer xoxb-.*"}
    service_prefixes: dict[str, str] = Field(default_factory=dict)
    # key = service name, value = URL prefix
    # e.g., {"stripe": "/stripe", "slack": "/slack/api"}
```

**Wire into TerrariumConfig** at `config/schema.py:72` — add:
```python
from terrarium.middleware.config import MiddlewareConfig
...
middleware: MiddlewareConfig = Field(default_factory=MiddlewareConfig)
```

**Wire into TOML** at `terrarium.toml`:
```toml
[middleware]
auth_enabled = false
status_codes_enabled = true
prefixes_enabled = false

[middleware.auth_rules]
stripe = "Bearer sk_.*"
slack = "Bearer xoxb-.*"
gmail = "Bearer ya29\\..*"
github = "Bearer (ghp_|gho_|github_pat_).*"
jira = "Bearer .*"
shopify = "Bearer shpat_.*"

[middleware.service_prefixes]
stripe = "/stripe"
slack = "/slack/api"
jira = "/jira"
shopify = "/shopify"
```

---

### Component 2: AuthMiddleware (`middleware/auth.py`)

**What**: Validates `Authorization` header shape per service. Accepts structurally valid tokens. Returns 401 if invalid.

**Spec requirements** (from section "Auth mimicry rules"):
- Validates token SHAPE only (not scopes)
- Simulated auth errors: return 401 with service-appropriate error body
- Refresh/expiry: not simulated in Phase 2 (acknowledged)

**Service resolution from URL path**: Extract service name from the URL path by checking registered service prefixes first, then falling back to tool name prefix extraction.

**Internal API bypass**: Routes starting with `/api/v1/` skip auth (these are Terrarium management endpoints).

**Code reference**: Use `BaseHTTPMiddleware` from Starlette (same pattern as CORS at http_rest.py:71).

```python
class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: MiddlewareConfig):
        super().__init__(app)
        self._enabled = config.auth_enabled
        self._rules = {
            svc: re.compile(pattern)
            for svc, pattern in config.auth_rules.items()
        }

    async def dispatch(self, request, call_next):
        if not self._enabled:
            return await call_next(request)

        # Skip internal Terrarium API + health + MCP
        path = request.url.path
        if path.startswith(("/api/v1/", "/mcp", "/health")):
            return await call_next(request)

        service = self._resolve_service(path)
        if service and service in self._rules:
            auth_header = request.headers.get("authorization", "")
            if not self._rules[service].fullmatch(auth_header):
                return JSONResponse(
                    status_code=401,
                    content={"error": {"message": "Invalid authentication", "type": "authentication_error"}},
                )

        return await call_next(request)

    def _resolve_service(self, path: str) -> str | None:
        # Check known service prefixes
        # Then fallback to first path segment heuristic
```

---

### Component 3: StatusCodeMiddleware (`middleware/status_codes.py`)

**What**: Maps response body error patterns to proper HTTP status codes.

**How it works**: After the route handler returns, if the body contains an `"error"` key and status is 200, reclassify to the appropriate HTTP status code.

**Error classification** (pattern matching on error message text):
```python
_ERROR_PATTERNS: list[tuple[int, list[str]]] = [
    (404, ["not found", "does not exist", "no such"]),
    (403, ["permission denied", "forbidden", "not authorized"]),
    (400, ["invalid", "required", "missing param"]),
    (422, ["validation failed", "schema error"]),
    (429, ["rate limit", "budget exhausted", "quota exceeded"]),
    (409, ["conflict", "already exists", "duplicate"]),
]
```

**Important**: Only reclassifies when `status_code == 200` AND body has `"error"` key. Doesn't touch non-200 responses or responses without errors.

**Pipeline short-circuit mapping**: When the pipeline short-circuits at a step:
- `permission` → 403
- `policy` (block) → 403
- `budget` → 429
- `capability` → 404
- `validation` → 422

---

### Component 4: PrefixRouter (`middleware/prefix_router.py`)

**What**: At startup, duplicates existing routes under service prefixes so SDKs that set `base_url` work.

**Not middleware** — runs once during `start_server()`, not per-request.

```python
def mount_service_prefixes(
    app: Any,
    routes: list[dict],
    service_prefixes: dict[str, str],
    gateway: Any,
):
    """Duplicate routes under service prefixes.

    Example: /v1/charges (Stripe) → also available at /stripe/v1/charges
    """
    for route_def in routes:
        tool_name = route_def.get("tool_name", "")
        service = tool_name.split("_")[0] if "_" in tool_name else ""
        prefix = service_prefixes.get(service)
        if not prefix:
            continue

        original_path = route_def["path"]
        prefixed_path = f"{prefix}{original_path}"
        method = route_def.get("method", "POST").upper()

        # Same handler closure pattern as _mount_pack_routes (http_rest.py:778-796)
        ...
```

---

### Wiring into http_rest.py

**File**: `terrarium/engines/adapter/protocols/http_rest.py`

**Where**: In `start_server()`, after CORS middleware (line 77), before routes:

```python
# Add API surface middleware (Phase E2b)
from terrarium.middleware.config import MiddlewareConfig
from terrarium.middleware.auth import AuthMiddleware
from terrarium.middleware.status_codes import StatusCodeMiddleware

mw_config = getattr(gateway._app, '_config', None)
if mw_config and hasattr(mw_config, 'middleware'):
    middleware_cfg = mw_config.middleware
else:
    middleware_cfg = MiddlewareConfig()

if middleware_cfg.status_codes_enabled:
    app.add_middleware(StatusCodeMiddleware, config=middleware_cfg)

if middleware_cfg.auth_enabled:
    app.add_middleware(AuthMiddleware, config=middleware_cfg)
```

**For prefix router**: Call after `_mount_pack_routes()`:

```python
if middleware_cfg.prefixes_enabled:
    from terrarium.middleware.prefix_router import mount_service_prefixes
    routes = await gateway.get_tool_manifest(protocol="http")
    mount_service_prefixes(
        app, routes, middleware_cfg.service_prefixes, gateway
    )
```

---

### Test Harness

**Directory**: `tests/middleware/` (NEW)

**`tests/middleware/conftest.py`**:
```python
@pytest.fixture
def middleware_config():
    return MiddlewareConfig(
        auth_enabled=True,
        status_codes_enabled=True,
        prefixes_enabled=True,
        auth_rules={"stripe": "Bearer sk_.*", "slack": "Bearer xoxb-.*"},
        service_prefixes={"stripe": "/stripe", "slack": "/slack/api"},
    )

@pytest.fixture
def mock_gateway():
    # Same pattern as tests/sdk/conftest.py
```

**Test files**:

| File | Tests | What |
|------|-------|------|
| `test_auth.py` | 8 | Valid token, invalid token, missing header, disabled skips, internal API skipped, unknown service, empty token, default rule |
| `test_status_codes.py` | 7 | 404 not found, 403 denied, 400 invalid, 429 rate limit, 409 conflict, 200 passthrough, non-error passthrough |
| `test_prefix_router.py` | 5 | Prefixed URL works, original still works, unknown prefix 404, disabled skips, multiple services |
| **Total** | **20** | |

---

### Documentation Updates

After implementation:
1. Save plan to `internal_docs/plans/E2b-phase2-api-surface-middleware.md`
2. Update `IMPLEMENTATION_STATUS.md`:
   - Mark E2b as done
   - Test count: 2262+ (current 2242 + ~20 new)
   - Document middleware config options
3. Update `internal_docs/plans/E2-agent-integration-master.md` — mark G7/G8 as done

---

### Implementation Order

```
1. Create middleware/config.py (MiddlewareConfig model)
2. Add to config/schema.py (TerrariumConfig.middleware field)
3. Add to terrarium.toml (defaults)
4. Create middleware/auth.py + tests
   → Run tests, verify
5. Create middleware/status_codes.py + tests
   → Run tests, verify
6. Create middleware/prefix_router.py + tests
   → Run tests, verify
7. Wire into http_rest.py start_server()
   → Run full suite, verify 0 regressions
8. Save docs
```

### Verification

```bash
uv run pytest tests/middleware/ -v
uv run pytest tests/ --ignore=tests/live --ignore=tests/integration -q
# Target: 2262+ passed, 0 xfails

# Manual E2E:
uv run terrarium serve world.yaml --port 8080

# Without auth (disabled by default):
curl http://localhost:8080/v1/payment_intents
# → 200 with Stripe-format response

# With auth enabled (terrarium.toml: auth_enabled = true):
curl -H "Authorization: Bearer sk_test_123" http://localhost:8080/stripe/v1/charges
# → 200 with charges list

curl -H "Authorization: Bearer bad_token" http://localhost:8080/stripe/v1/charges
# → 401 authentication_error

curl http://localhost:8080/stripe/v1/charges/nonexistent
# → 404 not found
```
