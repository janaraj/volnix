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

When the compiler encounters a service name in the world YAML, it resolves through a multi-step priority chain. The first two steps are fully deterministic. After that, the quality depends on what external sources are available.

```
1. Verified Pack?          → Tier 1, direct (deterministic Python, confidence=1.0)
   |                         No LLM. Hand-built handlers.
   v not found
2. Curated Profile?        → Tier 2, direct (hand-written YAML, confidence=0.8-0.9)
   |                         No LLM at resolution time. Profile already exists.
   v not found
3. OpenAPI spec on disk?   → Tier 2, direct (spec parsed → surface, confidence=0.5-0.6)
   |                         No LLM. Operations extracted programmatically from spec.
   v not found
4. Context Hub + LLM       → Tier 2, inferred (real docs → LLM → profile, confidence=0.7)
   |                         LLM generates profile, but from curated real documentation.
   v Context Hub has no docs
5. Kernel + LLM            → Tier 2, inferred (category primitives → LLM, confidence=0.4)
   |                         LLM generates profile from category knowledge only.
   v unknown category
6. LLM only                → Tier 2, inferred (general knowledge, confidence=0.3)
                             LLM generates profile with no external context.
```

**Key distinction:**
- Steps 1-3 are **fully deterministic** — no LLM involved at all
- Steps 4-6 all use the **LLM ProfileInferrer**, but with different quality of input:
  - Step 4: LLM reads **real curated API documentation** from Context Hub → highest quality inference
  - Step 5: LLM uses **category primitives** from the Semantic Kernel (e.g., "work_management" → work_item, lifecycle, assignment)
  - Step 6: LLM uses only its **general knowledge** → lowest quality, most likely to hallucinate

The confidence scores reflect this: real docs (0.7) > category knowledge (0.4) > nothing (0.3).

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

### Context Hub + LLM Inference (Step 4)

The **Context Hub** ([`@aisuite/chub`](https://github.com/andrewyng/context-hub)) is a curated API documentation provider. It fetches real, maintained documentation for services.

```
Context Hub-backed inference:
  1. chub search "hubspot" → finds content IDs: hubspot/api
  2. chub get hubspot/api --lang py → returns curated Python-focused markdown
  3. ProfileInferrer feeds the markdown into an LLM prompt
  4. LLM reads real docs → generates structured profile YAML
  5. Profile validated, saved to disk, registered for runtime use
```

**This is NOT blind LLM hallucination.** The LLM works from real, curated API documentation — it reads actual endpoint descriptions, parameter schemas, and response examples from the Context Hub markdown. The result is a bootstrapped profile with:
- `fidelity_source: "bootstrapped"`
- `confidence: 0.7`
- `source_chain: ["context_hub", "llm_inference"]`

Context Hub is optional — if `npx` is not available or the service isn't in the hub, the resolver falls back to Kernel + LLM (Step 5) or LLM-only (Step 6) with lower confidence.

### OpenAPI Specs (Step 3 — Direct Resolution, No LLM)

Volnix can parse **local OpenAPI 3.x specs** (YAML or JSON) placed in the spec directory. This is a **truly direct resolution** — operations are extracted programmatically, no LLM involved:

1. Loads `{service_name}.yaml` or `{service_name}.json` from the configured spec directory
2. Parses all paths + methods → tool definitions with parameter schemas
3. Resolves `$ref` references in parameters and response schemas
4. Produces a working `ServiceSurface` with real operations (confidence 0.5-0.6)

This is the only Tier 2 resolution path (besides curated profiles) that produces a **complete, working surface without any LLM call**. Drop the spec file in the spec directory and Volnix picks it up automatically:

```bash
# Place your spec in the configured spec directory
cp my_service_openapi.yaml volnix/specs/my_service.yaml

# Now reference it in your world YAML — Volnix auto-discovers the spec
```

### Profile Inference (Steps 4-6 — LLM with Available Context)

Profile inference runs when no verified pack, curated profile, or OpenAPI spec exists (Steps 1-3 fail). It gathers whatever external context is available before calling the LLM:

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

## BYOP — Bring Your Own Pack

Volnix simulates any API. You can add your own service at three levels:

| Level | Effort | How | Fidelity |
|-------|--------|-----|----------|
| **Automatic** | Zero | Just put the service name in your YAML — the compiler fetches Context Hub docs and generates a profile via LLM | Tier 2 (bootstrapped, confidence 0.3-0.7) |
| **YAML Profile** | Minutes | Write a `.profile.yaml` with operations, entities, and behavioral rules | Tier 2 (curated, confidence 0.9) |
| **Verified Pack** | Hours | Write Python handlers with deterministic logic, entity schemas, and state machines | Tier 1 (deterministic, confidence 1.0) |

---

## How the Registry Works

Volnix maintains two registries that together provide the complete tool surface:

**PackRegistry** — Discovers verified packs from `volnix/packs/verified/*/pack.py` at startup. Indexes by pack name and tool name. Provides deterministic handlers.

**ProfileRegistry** — Loads YAML profiles from `volnix/packs/profiles/*.profile.yaml` at startup. Also registers profiles bootstrapped during compilation. Provides LLM-constrained tool definitions.

**Gateway** — Merges both registries into a single tool map. Pack tools are registered first; profile tools fill gaps for services without a verified pack. The `not in tool_map` guard ensures pack tools always take precedence.

```
Startup:
  PackRegistry: 154 tools from 11 packs (gmail, slack, zendesk, stripe, notion, ...)
  ProfileRegistry: 55 tools from 6 profiles (jira, shopify, twilio, ...)
  Gateway: 209 tools total (packs take precedence)

At runtime:
  Agent calls "pages.create" → Gateway → PackRegistry → NotionPack.handle_action()  [Tier 1]
  Agent calls "jira_create_issue" → Gateway → ProfileRegistry → Tier2Generator.generate()  [Tier 2]
```

---

## Tier 2 Runtime — How Each Method Type Works

When an agent calls a Tier 2 profiled tool, the Responder's `Tier2Generator` makes an LLM call constrained by the profile. The LLM receives the current world state so it can generate realistic responses.

**GET / Retrieve**: LLM receives the full entity list from world state. It finds the requested entity by ID and returns it. If not found, it generates a 404 error matching the profile's error_modes.

**POST / Create**: LLM generates a realistic new entity with proper ID format, timestamps, and field values. The response is validated against the operation's `response_schema`. A `StateDelta(operation="create")` commits the new entity to world state.

**PATCH / Update**: LLM sees the current entity state plus the requested changes. Returns the updated entity. A `StateDelta(operation="update")` commits the changes with `previous_fields` for audit.

**POST / Search / Query**: LLM receives ALL existing entities of the relevant type from world state (up to 20). It reads the search criteria and returns matching entities. The LLM understands "search contacts where email contains 'acme'" and filters accordingly.

**DELETE**: LLM generates the appropriate response (often setting `archived: true`). A StateDelta commits the change.

**Validation**: Every response is checked against the operation's `response_schema`. If validation fails for create/mutate operations, the LLM is retried once with the validation errors as context. Read-only operations log warnings but don't block.

---

## Creating a Verified Pack (Tier 1) — Notion Walkthrough

This walkthrough uses the real Notion pack (`volnix/packs/verified/notion/`) as a reference. It has 15 tools matching the official Notion SDK, 5 entity types, and 67 tests.

### Step 1: Get the Real API Documentation

Before writing any code, get the actual API docs for your service:

```bash
# Context Hub has docs for many services
npx @aisuite/chub search notion
npx @aisuite/chub get notion/workspace-api --lang py > /tmp/notion-docs.md

# Check what SDK methods exist
grep -E "notion\.\w+\.\w+" /tmp/notion-docs.md | sort -u
```

This gives you the real method names, endpoints, parameters, and response formats. **Never invent API methods — use the real ones.**

### Step 2: Create the Directory

```
volnix/packs/verified/notion/
├── __init__.py          # Re-export NotionPack
├── schemas.py           # Entity schemas + tool definitions (pure data)
├── state_machines.py    # Entity lifecycle transitions (pure data)
├── handlers.py          # 15 async handler functions (logic)
└── pack.py              # ServicePack subclass (wiring)
```

### Step 3: Define State Machines (`state_machines.py`)

Identify which entity fields have lifecycle states. For Notion, pages/databases/blocks have an `archived` field — one-way transition from active to archived:

```python
"""State machine definitions for Notion entities.

Notion's archived field is one-way: once archived, objects cannot be unarchived.
Applied to pages, databases, and blocks.
"""
from __future__ import annotations

ARCHIVED_STATES: list[str] = ["active", "archived"]

ARCHIVED_TRANSITIONS: dict[str, list[str]] = {
    "active": ["archived"],
    "archived": [],  # One-way — Notion does not allow unarchive
}
```

### Step 4: Define Entity Schemas (`schemas.py`)

Each entity type needs a JSON-Schema-style dict. Key requirements:
- `"x-volnix-identity"` marks the primary key field
- `"required"` lists fields that must exist on every entity
- `"enum"` on state fields — must match state machine transitions
- Match the real API response structure

```python
"""Entity schemas and tool definitions for the Notion service pack.

All schemas match the official Notion API v2022-06-28+ response format.
Tool names match the official notion-client Python SDK methods.
"""
from __future__ import annotations

# -- Entity Schemas --

PAGE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "object", "parent", "properties", "archived",
                 "created_time", "last_edited_time"],
    "properties": {
        "id": {"type": "string"},
        "object": {"type": "string", "enum": ["page"]},
        "parent": {"type": "object"},
        "properties": {"type": "object"},
        "url": {"type": "string"},
        "archived": {"type": "boolean"},
        "created_time": {"type": "string"},
        "last_edited_time": {"type": "string"},
        "created_by": {"type": "object"},
        "last_edited_by": {"type": "object"},
        "cover": {},
        "icon": {},
    },
}

# DATABASE_ENTITY_SCHEMA, BLOCK_ENTITY_SCHEMA, USER_ENTITY_SCHEMA,
# COMMENT_ENTITY_SCHEMA follow the same pattern...
```

Then define tool definitions — one per SDK method:

```python
NOTION_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "pages.create",
        "description": "Create a new page in a database or as a child of another page",
        "pack_name": "notion",
        "http_method": "POST",
        "http_path": "/v1/pages",
        "parameters": {
            "type": "object",
            "required": ["parent", "properties"],
            "properties": {
                "parent": {
                    "type": "object",
                    "description": "Parent page or database: {database_id: '...'} or {page_id: '...'}",
                    "properties": {
                        "database_id": {"type": "string"},
                        "page_id": {"type": "string"},
                    },
                },
                "properties": {
                    "type": "object",
                    "description": "Page properties (title, etc.)",
                    "properties": {},
                },
                "children": {
                    "type": "array",
                    "description": "Child block objects to add to the page",
                    "items": {"type": "object"},
                },
            },
        },
    },
    # ... 14 more tools matching the Notion SDK
]
```

**Important**: Parameter schemas must be OpenAI-compatible — `type: "object"` must have a `properties` field (even if empty). `type: "array"` must have `items`.

### Step 5: Write Handlers (`handlers.py`)

Each handler is an async function: `(input_data: dict, state: dict) -> ResponseProposal`

The `state` dict contains entity lists keyed by type: `state["pages"]`, `state["blocks"]`, etc.

**Shared helpers** (every pack needs these):

```python
def _notion_error(status: int, code: str, message: str) -> dict:
    """Notion API error format."""
    return {"object": "error", "status": status, "code": code, "message": message}

def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"

def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
```

**Create handler** — generates entity, returns StateDelta:

```python
async def handle_pages_create(input_data: dict, state: dict) -> ResponseProposal:
    page_id = _new_id("page")
    now = _now_iso()

    page_fields = {
        "id": page_id,
        "object": "page",
        "parent": input_data["parent"],
        "properties": input_data.get("properties", {}),
        "url": f"https://www.notion.so/{page_id.replace('-', '')}",
        "archived": False,
        "created_time": now,
        "last_edited_time": now,
        "created_by": {"object": "user", "id": "bot-user-001"},
        "last_edited_by": {"object": "user", "id": "bot-user-001"},
    }

    delta = StateDelta(
        entity_type="page",
        entity_id=EntityId(page_id),
        operation="create",
        fields=page_fields,
    )
    return ResponseProposal(response_body=page_fields, proposed_state_deltas=[delta])
```

**Retrieve handler** — lookup from state, 404 if missing:

```python
async def handle_pages_retrieve(input_data: dict, state: dict) -> ResponseProposal:
    page_id = input_data["page_id"]
    for page in state.get("pages", []):
        if page.get("id") == page_id:
            return ResponseProposal(response_body=page)
    return ResponseProposal(
        response_body=_notion_error(404, "object_not_found",
                                     f"Could not find page with ID: {page_id}.")
    )
```

**Search handler** — fuzzy text match + filtering + cursor pagination:

```python
async def handle_search(input_data: dict, state: dict) -> ResponseProposal:
    query = input_data.get("query", "").lower()
    filter_obj = input_data.get("filter")

    # Collect searchable items
    items = list(state.get("pages", [])) + list(state.get("databases", []))

    # Filter by object type
    if filter_obj and filter_obj.get("value"):
        items = [i for i in items if i.get("object") == filter_obj["value"]]

    # Text search — case-insensitive match on titles and properties
    if query:
        results = []
        for item in items:
            searchable = _extract_searchable_text(item).lower()
            if query in searchable:
                results.append(item)
        items = results

    # Cursor pagination
    paginated, has_more, next_cursor = _paginate_cursor(items, input_data)
    return ResponseProposal(response_body={
        "object": "list",
        "results": paginated,
        "has_more": has_more,
        "next_cursor": next_cursor,
    })
```

**Database query** — filter by property conditions:

```python
async def handle_databases_query(input_data: dict, state: dict) -> ResponseProposal:
    database_id = input_data["database_id"]

    # Verify database exists
    db = None
    for d in state.get("databases", []):
        if d.get("id") == database_id:
            db = d
            break
    if db is None:
        return ResponseProposal(
            response_body=_notion_error(404, "object_not_found",
                                         f"Could not find database: {database_id}")
        )

    # Get pages in this database
    pages = [p for p in state.get("pages", [])
             if p.get("parent", {}).get("database_id") == database_id]

    # Apply filter
    filter_obj = input_data.get("filter")
    if filter_obj:
        pages = [p for p in pages if _match_filter(p, filter_obj)]

    # Cursor pagination
    paginated, has_more, next_cursor = _paginate_cursor(pages, input_data)
    return ResponseProposal(response_body={
        "object": "list",
        "results": paginated,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "type": "page_with_id",
    })
```

See `volnix/packs/verified/notion/handlers.py` for the complete implementation of all 15 handlers including the filter evaluation logic.

### Step 6: Wire the Pack (`pack.py`)

```python
class NotionPack(ServicePack):
    pack_name: ClassVar[str] = "notion"
    category: ClassVar[str] = "storage_documents"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "pages.create": handle_pages_create,
        "pages.retrieve": handle_pages_retrieve,
        "pages.update": handle_pages_update,
        "databases.create": handle_databases_create,
        "databases.retrieve": handle_databases_retrieve,
        "databases.query": handle_databases_query,
        "blocks.children.list": handle_blocks_children_list,
        "blocks.children.append": handle_blocks_children_append,
        "blocks.retrieve": handle_blocks_retrieve,
        "blocks.delete": handle_blocks_delete,
        "users.list": handle_users_list,
        "users.me": handle_users_me,
        "search": handle_search,
        "comments.create": handle_comments_create,
        "comments.list": handle_comments_list,
    }

    def get_tools(self) -> list[dict]:
        return list(NOTION_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        return {
            "page": PAGE_ENTITY_SCHEMA,
            "database": DATABASE_ENTITY_SCHEMA,
            "block": BLOCK_ENTITY_SCHEMA,
            "user": USER_ENTITY_SCHEMA,
            "comment": COMMENT_ENTITY_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        return {
            "page": {"field": "archived", "transitions": ARCHIVED_TRANSITIONS},
            "database": {"field": "archived", "transitions": ARCHIVED_TRANSITIONS},
            "block": {"field": "archived", "transitions": ARCHIVED_TRANSITIONS},
        }

    async def handle_action(self, action, input_data, state) -> ResponseProposal:
        return await self.dispatch_action(action, input_data, state)
```

### Step 7: Write Tests

Create `tests/packs/verified/test_notion.py` following the pattern in `test_tickets.py`:

```python
@pytest.fixture
def notion_pack():
    return NotionPack()

@pytest.fixture
def sample_state():
    """State with pre-existing pages, databases, blocks, users, comments."""
    return {
        "pages": [...],      # 3 pages (2 in db-001, 1 standalone)
        "databases": [...],  # 2 databases with property schemas
        "blocks": [...],     # 5 blocks (paragraph, heading, to_do)
        "users": [...],      # 1 person + 1 bot
        "comments": [...],   # 2 comments on page-001
    }

async def test_pages_create(notion_pack, sample_state):
    result = await notion_pack.handle_action(
        ToolName("pages.create"),
        {"parent": {"database_id": "db-001"}, "properties": {"Name": {...}}},
        sample_state,
    )
    assert result.response_body["object"] == "page"
    assert len(result.proposed_state_deltas) == 1
    assert result.proposed_state_deltas[0].operation == "create"
```

See `tests/packs/verified/test_notion.py` for the full 67-test suite.

### Step 8: Auto-Discovery

No registration code needed. Volnix auto-discovers packs at startup by scanning `volnix/packs/verified/*/pack.py` for `ServicePack` subclasses. Just create the directory and it works.

```bash
# Verify your pack is discovered
uv run volnix list services
# Should show: notion (storage_documents, 15 tools, tier 1)
```

### Step 9: Use in a World

```yaml
world:
  services:
    notion: verified/notion
    slack: verified/slack
```

---

## Creating a Service Profile (Tier 2)

If you don't need deterministic behavior, a YAML profile is simpler. The LLM generates responses at runtime constrained by the profile's schemas and rules.

### When to Use a Profile vs a Pack

| Use a Profile when... | Use a Pack when... |
|----------------------|-------------------|
| Prototyping quickly | You need reproducible results |
| The service isn't performance-critical | The service is on a benchmark-grade path |
| You want to test agent behavior, not service accuracy | You need exact API response formats |
| The service has simple CRUD operations | The service has complex query/filter logic |

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

### Or: Let the Compiler Bootstrap It

If the service is in Context Hub, you don't even need to write the profile. Just reference it in your world YAML:

```yaml
world:
  services:
    hubspot: hubspot    # No pack, no profile — compiler bootstraps from Context Hub
```

The compiler will fetch docs, generate a profile via LLM, save it to disk, and register it. Next time, the cached profile is reused.

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

## Acknowledgments

Service profile resolution uses [Context Hub](https://github.com/andrewyng/context-hub) by Andrew Ng — curated, versioned documentation for coding agents. Volnix uses Context Hub for dynamic API schema extraction, resolving service profiles directly from real documentation without LLM inference.

## Next Steps

- [Creating Worlds](creating-worlds.md) — Reference services in your world YAML
- [Blueprints Reference](blueprints-reference.md) — Which blueprints use which services
- [Architecture](architecture.md) — How the Responder engine fits in the pipeline
- [Configuration](configuration.md) — Service pack paths and LLM settings
