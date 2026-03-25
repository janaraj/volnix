# Terrarium — Browser Pack Implementation

**Pack type:** Tier 1 Verified
**Category:** `browser`
**Location:** `terrarium/packs/verified/browser/`

---

## Overview

The browser pack simulates web browsing within the Terrarium world. It follows the exact same 4-file pattern as all other verified packs (tickets, email, payments, etc.) and integrates automatically with the existing infrastructure — no changes to the compiler, responder, gateway, or pipeline.

**Core principle:** The browser is a projection of world state into structured content, the same way APIs project world state into JSON.

---

## Architecture

### How It Fits Into the System

```
WorldDataGenerator (compile time)
    │ reads pack.get_entity_schemas()
    │ generates web_site, web_page, web_session entities via LLM
    ▼
State Engine (stores entities)
    │
    ├── Agent calls web_navigate/web_search/etc. via MCP/HTTP
    │       ▼
    │   Gateway → Pipeline (7-step) → Responder → BrowserPack.handle_action()
    │       │ handler reads from state, returns ResponseProposal
    │       ▼
    │   Response returned to agent
    │
    └── Animator calls web_page_modify/web_page_create (dynamic mode)
            ▼
        Same pipeline path → BrowserPack handles it deterministically
```

### Fidelity Model

- **Compile time:** LLM generates entity data (page content, links, forms) — same as all packs.
- **Runtime:** Deterministic handlers look up pre-generated entities. Zero LLM. `FidelityMetadata(tier=1, deterministic=True, benchmark_grade=True)`.
- **Dynamic mode:** Animator uses pack's own tools (`web_page_modify`, `web_page_create`) through the pipeline. LLM generates the `input_data` for these events; the pack handler processes them deterministically.

---

## Entity Types

| Entity | Purpose | Key Fields |
|--------|---------|-----------|
| `web_site` | A website/domain | domain, name, site_type, auth_required, renders_from |
| `web_page` | A page within a site | domain, path, title, content_text, links, forms, status, page_type |
| `web_session` | Agent's browsing session | actor_id, current_url, current_page_id, history, status |

### Three Content Layers

| Layer | What | How Pages Created | Pack's Role |
|-------|------|-------------------|-------------|
| Layer 1 (Entity Views) | Dashboard views of tickets, emails, etc. | Compiler generates `web_page` entities with `page_type: "entity_view"` | Handler returns stored content |
| Layer 2 (Known Sites) | Company websites, KBs, competitor sites | Compiler generates `web_page` entities from YAML `services.web.sites` | Handler returns stored content |
| Layer 3 (Unknown URLs) | URLs not pre-generated | Not handled at Tier 1 (returns 404) | Future Tier 2 profile scope |

---

## Tools (11)

### Agent-Facing (9)

| Tool | Type | What It Does |
|------|------|-------------|
| `web_navigate` | Mutating | Navigate to URL, return page, update session |
| `web_search` | Read-only | Search published pages by title/content/keywords |
| `web_read_page` | Read-only | Read current page (session) or specific page (ID) |
| `web_click_link` | Mutating | Follow link on current page, validate it exists |
| `web_submit_form` | Side Effect | Submit form → SideEffect to target service via pipeline |
| `web_back` | Mutating | Navigate back in session history |
| `web_list_sites` | Read-only | List all websites with optional filters |
| `web_get_page` | Read-only | Get page by ID |
| `web_create_session` | Mutating | Create new browser session for an actor |

### Animator/System (2)

| Tool | Type | What It Does |
|------|------|-------------|
| `web_page_modify` | Mutating | Modify page content (inject, update, replace, change status) |
| `web_page_create` | Mutating | Create new page at runtime |

---

## Form Submission Bridge

Forms on web pages define `action_type` and `target_service`. When `web_submit_form` is called, the handler creates a `SideEffect`:

```python
SideEffect(
    effect_type=form["action_type"],          # e.g. "create_refund"
    target_service=ServiceId("payments"),      # target pack
    parameters={**form_data, "_source_interface": "browser"},
)
```

The `SideEffectProcessor` picks this up and runs it through the full 7-step governance pipeline targeting the payments pack. Policy holds, budget checks, and permission enforcement all apply.

---

## Behavior Mode Integration

The pack is mode-agnostic. The Animator controls what happens:

| Mode | Effect on Browser |
|------|-------------------|
| Static | Pages frozen after compilation. No modifications. |
| Reactive | Pages change only when agent actions trigger related state updates. |
| Dynamic | Animator freely calls `web_page_modify` (compromise, update) and `web_page_create` (new articles). |

---

## State Machines

**web_page:** `draft → published → archived/compromised`, with recovery paths (`compromised → published`, `archived → published`).

**web_session:** `active → expired` (terminal).

---

## File Structure

```
terrarium/packs/verified/browser/
    __init__.py          # Re-export BrowserPack
    pack.py              # BrowserPack(ServicePack) — 11 handlers, 3 entity schemas, 2 state machines
    schemas.py           # Entity schemas + tool definitions (pure data)
    state_machines.py    # Transition dicts (pure data)
    handlers.py          # 11 async handler functions + shared helpers

tests/packs/
    test_browser_pack.py # 46 tests covering all handlers and edge cases
```

---

## Design Decisions

1. **URL normalization:** Strips protocol, lowercases domain, normalizes trailing slashes. Pages matched by domain + path only (no query params or fragments).

2. **Session auto-creation:** `web_navigate` creates a session automatically if none provided, reducing tool call overhead for simple browsing.

3. **Relative link resolution:** Links starting with `/` get the current page's domain prepended. Absolute URLs used as-is.

4. **Search scoring:** Simple substring matching with weighted scoring (title=3, keywords=2, content/meta=1). Deterministic and reproducible. More sophisticated ranking is Tier 2 territory.

5. **Compromised pages visible in search:** Pages with `status: "compromised"` still appear in navigation and search results. This is intentional — the agent should encounter compromised content as part of the simulation.

6. **No LLM at runtime:** Every handler is a deterministic lookup/mutation against state. The pack never calls the LLM Router.
