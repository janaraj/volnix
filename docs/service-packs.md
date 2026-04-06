# Service Packs

Service packs are the backbone of Volnix's world simulation. They make simulated services behave like real APIs — when an agent calls `tickets.create`, it gets back a realistic Zendesk-style response with proper entity IDs, timestamps, and state transitions. No real API is called.

This document explains what service packs are, how they work at runtime, and how to create your own.

---

## What Is a Service Pack?

A service pack is a **self-contained simulation of a real-world service**. It provides:

- **Tools** — API operations the agent can call (e.g., `tickets.create`, `tickets.search`, `get_charge`)
- **Entity Schemas** — Data models for the objects managed by the service (tickets, customers, charges)
- **State Machines** — Valid lifecycle transitions (e.g., a ticket goes `new → open → pending → solved → closed`)
- **Action Handlers** — Functions that process each tool call and return a realistic response

When an agent calls a tool, the request flows through the governance pipeline and reaches the **World Responder** engine. The Responder dispatches to the appropriate service pack, which generates a deterministic response and produces state mutations (creating or updating entities in the world).

```
Agent calls tickets.create(subject="Refund request", priority="high")
  |
  v
Governance Pipeline: permission → policy → budget → capability
  |
  v
World Responder → finds "zendesk" verified pack → dispatches to TicketsPack
  |
  v
Handler creates ticket entity (id=ticket-a1b2c3, status="new")
  |
  v
State Engine commits the entity → Agent receives full ticket JSON response
```

---

## Two Fidelity Tiers

| Tier | What It Is | LLM at Runtime | Best For |
|------|-----------|----------------|----------|
| **Tier 1: Verified Pack** | Hand-built Python code with deterministic handlers, entity schemas, and state machines | No LLM | High-fidelity simulation, benchmarking, reproducible evaluation |
| **Tier 2: Service Profile** | YAML definition that constrains LLM-generated responses with schemas, examples, and behavioral rules | Yes (constrained) | Services without a verified pack, rapid prototyping, extending existing packs |

**Rule:** There is no Tier 3 at runtime. If a service has no pack or profile, it gets **bootstrapped** at compile time — the compiler generates a Tier 2 profile via LLM inference.

---

## Tier 1: Verified Packs

### Available Packs

Volnix ships with 10 verified service packs:

| Pack | Category | Tools | What It Simulates |
|------|----------|-------|-------------------|
| **gmail** | Communication | 14 | Gmail API — send, read, search, draft, label, thread messages |
| **slack** | Communication | 16 | Slack API — post messages, create channels, react, thread replies |
| **zendesk** | Work Management | 12 | Zendesk API — create/update/search tickets, comments, users, groups |
| **stripe** | Payments | 21 | Stripe API — charges, customers, refunds, payment intents, invoices |
| **github** | Code/DevOps | 15 | GitHub API — repos, issues, PRs, commits, file operations |
| **google_calendar** | Scheduling | 9 | Calendar API — events, calendars, attendees, recurring events |
| **twitter** | Social Media | 16 | Twitter API — tweets, replies, search, followers, timeline |
| **reddit** | Social Media | 18 | Reddit API — posts, comments, subreddits, votes, search |
| **alpaca** | Trading | 22 | Alpaca API — orders, positions, market data, account management |
| **browser** | Web Browsing | 11 | HTTP browsing — GET/POST to configured sites, page content |

### Using Packs in World YAML

Reference services in your world definition:

```yaml
world:
  services:
    gmail: verified/gmail       # Explicit: use the verified gmail pack
    slack: verified/slack
    zendesk: verified/zendesk
    stripe: verified/stripe
```

The `verified/` prefix is optional — Volnix auto-resolves service names and prefers verified packs when available.

### How a Pack Works at Runtime

Here's what happens when an agent calls `tickets.create`:

1. **Tool call arrives** — agent sends `{"action": "tickets.create", "input_data": {"subject": "Refund", "priority": "high", "requester_id": "usr-001"}}`

2. **Governance pipeline** — checks the agent has permission to write to zendesk, the action isn't blocked by policy, and the budget allows it

3. **Responder dispatches** — finds `zendesk` is a verified pack → calls `TicketsPack.handle_action()`

4. **Handler executes** — `handle_tickets_create()` in `handlers.py`:
   - Generates a unique entity ID: `ticket-a1b2c3d4`
   - Sets initial status: `"new"` (per state machine)
   - Creates a `StateDelta(entity_type="ticket", operation="create", fields={...})`
   - Returns a `ResponseProposal` with the full ticket JSON + state delta

5. **State Engine commits** — the new ticket entity is persisted in SQLite

6. **Agent receives response** — realistic Zendesk-style JSON:
   ```json
   {
     "ticket": {
       "id": "ticket-a1b2c3d4",
       "subject": "Refund",
       "status": "new",
       "priority": "high",
       "requester_id": "usr-001",
       "created_at": "2026-04-05T19:15:31Z",
       "updated_at": "2026-04-05T19:15:31Z"
     }
   }
   ```

### State Machine Enforcement

When an agent tries to update a ticket's status, the pack validates the transition:

```python
# volnix/packs/verified/zendesk/state_machines.py
TICKET_TRANSITIONS = {
    "new":     ["open", "pending", "hold", "solved"],
    "open":    ["pending", "hold", "solved"],
    "pending": ["open", "hold", "solved"],
    "hold":    ["open", "pending", "solved"],
    "solved":  ["open", "closed"],
    "closed":  [],  # Terminal state — no transitions allowed
}
```

If an agent tries `tickets.update(status="closed")` on a ticket that's currently `"open"`, the pack rejects it — you can only close a ticket from `"solved"`.

### Inspecting Packs

```bash
# List all available tools across all packs
uv run volnix list tools

# Show a specific service's tools, entities, and state machines
uv run volnix show service zendesk

# Show details of a single tool
uv run volnix show tool tickets.create
```

---

## Tier 2: Service Profiles

Profiles are YAML files that define a service's API surface, entity schemas, behavioral rules, and examples. At runtime, the LLM generates responses constrained by the profile.

### Available Curated Profiles

| Profile | Category | Operations | Source |
|---------|----------|-----------|--------|
| **jira** | Work Management | 7 | Curated |
| **shopify** | Commerce | 8 | Curated |
| **twilio** | Communications | 7 | Curated |
| **email** | Communication | 11 | Curated |
| **stripe** | Money | 14 | Bootstrapped |
| **gmail** | Communication | 10 | Bootstrapped |

Profiles live in `volnix/packs/profiles/`.

### How a Profile Works at Runtime

When a service has a profile but no verified pack:

1. **Responder** checks the profile registry → finds `jira` profile
2. **Tier 2 Generator** builds an LLM prompt from:
   - The profile's `responder_prompt` (service personality/rules)
   - The profile's `behavioral_notes` (domain constraints)
   - The profile's `error_modes` (realistic failure cases)
   - The profile's `examples` (few-shot grounding)
   - The operation's `response_schema` (structural constraint)
   - Current world state (existing entities)
3. **LLM generates** a response within those constraints
4. **Response validated** against the operation's JSON schema
5. **State machine checked** if the operation mutates an entity

### Profile YAML Structure

```yaml
profile_name: jira
service_name: jira
category: work_management
version: "1.0.0"
fidelity_source: curated_profile    # "curated_profile" or "bootstrapped"
confidence: 0.9                     # 0.0-1.0, higher = more trusted

# API operations this service supports
operations:
  - name: jira_create_issue
    service: jira
    description: "Create a new Jira issue in a project"
    http_method: POST
    http_path: /rest/api/3/issue
    parameters:
      project_key: { type: string, description: "Project key (e.g., PROJ)" }
      summary: { type: string, description: "Issue summary" }
      issue_type: { type: string, enum: ["Bug", "Task", "Story", "Epic"] }
    required_params: [project_key, summary, issue_type]
    response_schema:
      type: object
      properties:
        id: { type: string }
        key: { type: string }
      required: [key]
    is_read_only: false
    creates_entity: issue

# Data types managed by this service
entities:
  - name: issue
    identity_field: key
    fields:
      key: { type: string }
      summary: { type: string }
      status: { type: string }
    required: [key, summary]

# Entity lifecycle transitions
state_machines:
  - entity_type: issue
    field: status
    transitions:
      open: [in_progress, closed]
      in_progress: [review, open]
      review: [done, in_progress]

# Realistic failure scenarios
error_modes:
  - code: ISSUE_NOT_FOUND
    when: "Referenced issue key does not exist"
    http_status: 404

# Domain rules for the LLM
behavioral_notes:
  - "Jira issue keys follow PROJECT-123 pattern"
  - "Status transitions must follow the workflow"

# LLM system prompt for generating responses
responder_prompt: |
  You are simulating a Jira instance. Return realistic JSON matching
  the Jira REST API v3 format. Use canonical issue keys like PROJ-123.

# Few-shot examples for grounding
examples:
  - operation: jira_create_issue
    request: { summary: "Login broken", project_key: "WEB", issue_type: "Bug" }
    response: { id: "10001", key: "WEB-42" }
```

---

## Service Resolution

When the compiler encounters a service name in the world YAML, it resolves through a multi-step priority chain. **Most steps produce a usable service surface directly — no LLM required.** The LLM is only the last fallback.

```
1. Verified Pack?          → Tier 1, direct (deterministic Python, confidence=1.0)
   |
   v not found
2. Curated Profile?        → Tier 2, direct (hand-written YAML, confidence=0.8-0.9)
   |
   v not found
3. Context Hub?            → Tier 2, direct (curated docs → surface, confidence=0.7)
   |                         NO LLM — operations extracted from real documentation
   v not found
4. OpenAPI spec?           → Tier 2, direct (spec parsed → surface, confidence=0.5-0.6)
   |                         NO LLM — operations extracted from real API spec
   v not found
5. Semantic Kernel?        → Category primitives (confidence=0.1-0.4)
   |                         NO LLM — static registry lookup
   v none of the above resolved
6. Profile Inference       → Tier 2 bootstrapped (LLM, but uses ALL sources above as context)
                             confidence=0.3-0.7 depending on what sources were available
```

**Key point:** Steps 3-5 are NOT "inputs to LLM generation." They are **direct resolution paths** that produce a working service surface without any LLM call. The LLM inference at Step 6 is only reached when all direct paths fail. And even then, it gathers whatever partial information the earlier steps found (Context Hub docs, OpenAPI operations, Kernel primitives) to give the LLM maximum context.

In world YAML, you can hint which tier to use:

```yaml
world:
  services:
    slack: verified/slack       # Force Tier 1 verified pack
    stripe: profiled/stripe     # Force Tier 2 profile
    jira: jira                  # Auto-resolve (compiler picks best tier)
    notion: notion              # Unknown — will be bootstrapped at compile time
```

### The Semantic Kernel

The Kernel is a static registry that maps service names to **semantic categories**. It doesn't call any LLM — it's a lookup table with inherited primitives.

**11 Categories:**

| Category | Services | Primitives |
|----------|----------|-----------|
| `communication` | Slack, Gmail, Outlook, Teams | channel, thread, message, delivery |
| `work_management` | Jira, Zendesk, Linear, Asana | work_item, lifecycle, assignment, SLA |
| `money_transactions` | Stripe, PayPal, Square | transaction, authorization, reversal, balance |
| `code_devops` | GitHub, GitLab, Bitbucket | repository, branch, pull_request, pipeline |
| `scheduling` | Google Calendar, Calendly | event, availability, recurrence, attendee |
| `social_media` | Reddit, Twitter, LinkedIn | post, comment, vote, feed, thread |
| `trading` | Alpaca, Interactive Brokers | order, position, quote, fill, account |
| `identity_auth` | Okta, Auth0, Azure AD | user, credential, session, role |
| `storage_documents` | Google Drive, Dropbox | document, folder, version, share |
| `monitoring_observability` | Datadog, PagerDuty | metric, alert, incident, dashboard |
| `authority_approvals` | ServiceNow, DocuSign | request, approval, delegation, audit_trail |

When the compiler encounters `jira`, the Kernel classifies it as `work_management` and provides category primitives (work_item, lifecycle, assignment, etc.). These primitives seed the profile inference even when no external docs exist.

Service mappings are in `volnix/kernel/data/services.toml` (33+ pre-mapped services).

### Context Hub (Direct Resolution — No LLM)

The **Context Hub** ([`@aisuite/chub`](https://github.com/andrewyng/context-hub)) is a curated API documentation provider. It fetches real, maintained documentation for popular services.

```
Context Hub resolution (NO LLM involved):
  1. chub search "stripe" → finds content IDs: stripe/api, stripe/webhooks
  2. chub get stripe/api --lang py → returns curated Python-focused markdown
  3. Volnix parses the docs → extracts operations, entities, patterns
  4. Converts directly to ServiceSurface (confidence=0.7)
```

This is a **direct resolution** — the Context Hub docs produce a working service surface without any LLM call. The operations, parameters, and response schemas come from real curated documentation.

Context Hub is an open-source library with curated docs for hundreds of services (Stripe, Twilio, Jira, Shopify, etc.). Volnix uses it as a primary source before falling back to LLM inference.

Context Hub is optional — if `npx` is not available or the service isn't in the hub, the resolver continues to the next source. If Context Hub partially resolves a service (docs found but incomplete), those docs are still used as context if LLM inference is needed later.

### OpenAPI Specs (Direct Resolution — No LLM)

Volnix can parse **local OpenAPI 3.x specs** (YAML or JSON) placed in the spec directory. Like Context Hub, this is a direct resolution with no LLM involved:

1. Loads `{service_name}.yaml` or `{service_name}.json` from the configured spec directory
2. Extracts all operations (paths + methods → tool definitions)
3. Resolves `$ref` references in parameters and response schemas
4. Converts directly to `ServiceSurface` with confidence 0.5-0.6

This is useful when you have the actual API spec for a service. Drop the spec file in the spec directory and Volnix picks it up automatically:

```bash
# Place your spec in the configured spec directory
cp my_service_openapi.yaml volnix/specs/my_service.yaml

# Now reference it in your world YAML — Volnix auto-discovers the spec
```

### Profile Inference (Last Resort — LLM with Context)

Profile inference is the **last fallback** — it only runs when Steps 1-5 all fail to produce a complete service surface. Even then, it's not blind LLM generation — it gathers whatever partial information the earlier steps found:

**Step 1: Gather sources**
```
sources = {
  "context_hub":  Curated docs from Context Hub (if available)
  "openapi":      Operations from local OpenAPI spec (if available)
  "category":     Semantic category from Kernel (e.g., "work_management")
  "primitives":   Category primitives (work_item, lifecycle, assignment, ...)
}
```

**Step 2: Build LLM prompt with ALL available context**
- Context Hub markdown docs (truncated to 8000 chars)
- OpenAPI operations (first 20)
- Category primitives from Kernel
- Instructions to generate a valid profile YAML

**Step 3: LLM generates profile YAML**
- Operations, entities, state machines, behavioral notes, responder prompt
- Validated against the `ServiceProfileData` schema

**Step 4: Confidence scoring based on sources used**

| Sources Available | Confidence | Source Chain |
|-------------------|-----------|-------------|
| Context Hub + Kernel | 0.7 | `["context_hub", "kernel:communication", "llm_inference"]` |
| OpenAPI + Kernel | 0.6 | `["openapi", "kernel:work_management", "llm_inference"]` |
| Kernel only | 0.4 | `["kernel:money_transactions", "llm_inference"]` |
| Nothing (LLM only) | 0.3 | `["llm_inference"]` |

**Step 5: Profile saved with provenance**

Every bootstrapped profile tracks its `source_chain` — the list of sources that contributed to its generation. This is visible in the profile YAML and in ledger entries, so you always know where a profile came from and how much to trust it.

### Drift Detection

Over time, real APIs change. Volnix can detect **API drift** — differences between your local profiles and the current external sources:

```bash
# Check a specific service
uv run volnix sync stripe

# Check all profiled services
uv run volnix sync --all

# Auto-apply updates
uv run volnix sync stripe --apply
```

Drift detection compares against:
- **Context Hub** — fetches latest docs, extracts operations, diffs against profile
- **OpenAPI specs** — compares version + operations

The `DriftReport` shows:
- Operations added/removed/changed
- Content hash changes
- Summary of what drifted

---

## Creating a New Verified Pack (Tier 1)

Follow this structure to add a deterministic service pack.

### Step 1: Create the Directory

```
volnix/packs/verified/my_service/
├── __init__.py
├── pack.py              # ServicePack subclass
├── handlers.py          # Action handler functions
├── schemas.py           # Tool definitions + entity schemas
└── state_machines.py    # Entity lifecycle transitions
```

### Step 2: Define Schemas (`schemas.py`)

```python
"""Entity schemas and tool definitions for my_service pack."""

# Entity schemas — JSON-Schema style
ITEM_ENTITY_SCHEMA = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "name", "status", "created_at"],
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "status": {"type": "string", "enum": ["draft", "active", "archived"]},
        "description": {"type": "string"},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
    },
}

# Tool definitions — what the agent sees
TOOL_DEFINITIONS = [
    {
        "name": "items.create",
        "description": "Create a new item",
        "pack_name": "my_service",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string", "description": "Item name"},
                "description": {"type": "string", "description": "Item description"},
            },
        },
    },
    {
        "name": "items.read",
        "description": "Get an item by ID",
        "pack_name": "my_service",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["item_id"],
            "properties": {
                "item_id": {"type": "string", "description": "Item ID"},
            },
        },
    },
    # ... more tools
]
```

### Step 3: Define State Machines (`state_machines.py`)

```python
"""State machine definitions for my_service entities."""

ITEM_TRANSITIONS = {
    "draft":    ["active", "archived"],
    "active":   ["archived"],
    "archived": [],  # Terminal state
}
```

### Step 4: Write Handlers (`handlers.py`)

Each handler is an async function that takes `(input_data, state)` and returns a `ResponseProposal`:

```python
"""Action handlers for my_service pack."""
import uuid
from datetime import UTC, datetime
from volnix.core.context import ResponseProposal
from volnix.core.types import EntityId, StateDelta


async def handle_items_create(input_data: dict, state: dict) -> ResponseProposal:
    """Create a new item."""
    item_id = f"item-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).isoformat()

    fields = {
        "id": item_id,
        "name": input_data["name"],
        "description": input_data.get("description", ""),
        "status": "draft",
        "created_at": now,
        "updated_at": now,
    }

    delta = StateDelta(
        entity_type="item",
        entity_id=EntityId(item_id),
        operation="create",
        fields=fields,
    )

    return ResponseProposal(
        response_body={"item": fields},
        state_deltas=[delta],
    )


async def handle_items_read(input_data: dict, state: dict) -> ResponseProposal:
    """Read an item by ID."""
    item_id = input_data["item_id"]
    items = state.get("item", {})
    item = items.get(item_id)

    if item is None:
        return ResponseProposal(
            response_body={"error": "not_found", "description": f"Item {item_id} not found"},
            state_deltas=[],
            status_code=404,
        )

    return ResponseProposal(
        response_body={"item": item},
        state_deltas=[],
    )
```

### Step 5: Wire the Pack (`pack.py`)

```python
"""My Service pack (Tier 1 — verified)."""
from typing import ClassVar
from volnix.core.context import ResponseProposal
from volnix.core.types import ToolName
from volnix.packs.base import ActionHandler, ServicePack
from volnix.packs.verified.my_service.handlers import (
    handle_items_create,
    handle_items_read,
)
from volnix.packs.verified.my_service.schemas import (
    ITEM_ENTITY_SCHEMA,
    TOOL_DEFINITIONS,
)
from volnix.packs.verified.my_service.state_machines import ITEM_TRANSITIONS


class MyServicePack(ServicePack):
    pack_name: ClassVar[str] = "my_service"
    category: ClassVar[str] = "work_management"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "items.create": handle_items_create,
        "items.read": handle_items_read,
    }

    def get_tools(self) -> list[dict]:
        return list(TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        return {"item": ITEM_ENTITY_SCHEMA}

    def get_state_machines(self) -> dict:
        return {"item": {"transitions": ITEM_TRANSITIONS}}

    async def handle_action(self, action: ToolName, input_data: dict, state: dict) -> ResponseProposal:
        return await self.dispatch_action(action, input_data, state)
```

### Step 6: Auto-Discovery

No registration code needed. Volnix auto-discovers packs at startup by scanning `volnix/packs/verified/*/pack.py` for `ServicePack` subclasses. Just create the directory and it works.

### Step 7: Use in a World

```yaml
world:
  services:
    my_service: verified/my_service
```

---

## Creating a Service Profile (Tier 2)

If you don't need deterministic behavior, a YAML profile is simpler:

### Step 1: Create the YAML File

Save as `volnix/packs/profiles/my_service.profile.yaml`:

```yaml
profile_name: my_service
service_name: my_service
category: work_management
version: "1.0.0"
fidelity_source: curated_profile
confidence: 0.9

operations:
  - name: my_service_create_item
    service: my_service
    description: "Create a new item"
    http_method: POST
    parameters:
      name: { type: string, description: "Item name" }
    required_params: [name]
    response_schema:
      type: object
      properties:
        id: { type: string }
        name: { type: string }
        status: { type: string }
      required: [id, name]
    creates_entity: item

entities:
  - name: item
    identity_field: id
    fields:
      id: { type: string }
      name: { type: string }
      status: { type: string }
    required: [id, name]

state_machines:
  - entity_type: item
    field: status
    transitions:
      draft: [active, archived]
      active: [archived]

behavioral_notes:
  - "Item IDs follow the pattern item-XXXXX"
  - "New items always start in draft status"

responder_prompt: |
  You are simulating My Service. Return realistic JSON responses.
  Use item IDs like item-12345. New items start as "draft".

examples:
  - operation: my_service_create_item
    request: { name: "Widget" }
    response: { id: "item-12345", name: "Widget", status: "draft" }
```

### Step 2: Auto-Discovery

Like packs, profiles are auto-discovered at startup. Just save the file and it works.

---

## Promoting Services

Volnix supports a service improvement lifecycle:

```
Bootstrapped (compile-time LLM inference, confidence 0.3-0.7)
  |
  v  annotate with feedback from runs
Curated Profile (hand-written YAML, confidence 0.9)
  |
  v  capture reference scenarios + build Python handlers
Verified Pack (deterministic Python, confidence 1.0)
```

```bash
# Annotate a service based on run results
uv run volnix annotate --run <run_id> --service stripe

# Promote bootstrapped → curated
uv run volnix promote --service jira --tier curated

# Capture reference scenarios for pack compilation
uv run volnix capture --world <world_id> --name jira_reference

# Generate a Tier 1 pack scaffold from a profile
uv run volnix compile-pack --profile jira --output volnix/packs/verified/jira/

# Verify the pack against reference scenarios
uv run volnix verify-pack --pack jira --scenarios jira_reference

# Check for API drift
uv run volnix sync --service jira
```

---

## Next Steps

- [Creating Worlds](creating-worlds.md) — Reference services in your world YAML
- [Blueprints Reference](blueprints-reference.md) — Which blueprints use which services
- [Architecture](architecture.md) — How the Responder engine fits in the pipeline
- [Configuration](configuration.md) — Service pack paths and LLM settings
