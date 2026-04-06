# Pending Work Items

Tracked items that need resolution before or immediately after launch.

---

## P0: Governance Event Observability (DONE)

**Status**: Complete — all governance events now carry `run_id`, `action`, `service_id` via base `Event` class. Pipeline DAG stamps context fields on every event before publishing to the bus.

**Problem**: Governance pipeline events (permission, budget, capability, animator) are not visible in the dashboard event log or WebSocket live feed. Only `WorldEvent` and `PolicyEvent` (just fixed) carry `run_id`, so other governance events are lost when the event log is built from bus persistence filtered by `run_id`.

**Impact**: Dashboard shows agent actions but not the governance decisions around them. Users cannot see permission denials, budget warnings, or escalations in the event feed — critical for understanding why an agent was blocked or throttled.

**Affected event types**:

| Engine | Event Type | Has `run_id` | Visible in Dashboard |
|--------|-----------|-------------|---------------------|
| Policy | `policy.flag`, `policy.block`, `policy.hold`, `policy.escalate` | Yes (fixed this session) | Yes |
| Permission | `permission.denied` | No | No |
| Budget | `budget.deduction`, `budget.warning`, `budget.exhausted` | No | No |
| Capability | `capability.gap` | No | No |
| Animator | `animator.*` | No | No |

**Root cause**: Each event class inherits from `Event` (base) which has no `run_id`. Only `WorldEvent` and `PolicyEvent` define it. The bus persistence stores events with `run_id`, and `query_raw(filters={"run_id": run_id})` skips events without one.

**Fix approach**: Add `run_id` to the base `Event` class in `volnix/core/events.py`, then set it from `ActionContext.run_id` in each enforcement handler / engine that produces events. Also update the WebSocket `_classify()` in `http_rest.py` to forward all governance events (not just `world.*`).

**Files to modify**:
- `volnix/core/events.py` — add `run_id` to base `Event` or to `PermissionEvent`, `BudgetEvent`, etc.
- `volnix/engines/permission/engine.py` — pass `run_id` to permission denied events
- `volnix/engines/budget/engine.py` + `tracker.py` — pass `run_id` to budget events
- `volnix/engines/adapter/engine.py` — pass `run_id` to capability gap events
- `volnix/engines/animator/engine.py` — pass `run_id` to animator events
- `volnix/engines/adapter/protocols/http_rest.py` — WebSocket `_classify()` already updated this session

**What's already done (this session)**:
- `PolicyEvent` now has `run_id` field
- All 4 enforcement handlers set `run_id` from `ActionContext`
- Base `Event` class now has `run_id`, `action`, `service_id` — inherited by all event types
- Pipeline DAG stamps these fields from `ActionContext` before publishing (single point, all engines covered)
- WebSocket `_classify()` updated to forward `policy.*`, `permission.*`, `capability.*`, `animator.*`
- Frontend filter keys fixed from underscores to dots (matching backend convention)
- HTTP API event filter supports prefix matching (`event_type=animator` matches `animator.*`)

---

## P0: Auto-Create Run for External Agents (DONE)

**Status**: Complete

**Problem**: When a run completes and a new external agent connects (via MCP/HTTP/crewAI), `handle_request` had no active run — events got `run_id=None` and weren't tracked in the dashboard.

**Fix**: Added `_ensure_active_run()` to `VolnixApp` — called at the top of `handle_request`. If there's a world but no active run, it loads the plan via `world_manager.load_plan()` and calls `create_run()`. Same pattern as the CLI serve path (`cli.py:765-776`).

---

## P0: OpenAI Provider Compatibility (DONE)

**Status**: Complete — world compilation works with both Gemini and OpenAI providers

**Fixes**:
- `max_tokens` → `max_completion_tokens`: 3-level fallback (try `max_completion_tokens` → `max_tokens` → omit)
- Array schema wrapping: OpenAI requires root `type: "object"` in `response_format`. Arrays auto-wrapped in object, response auto-unwrapped.
- File: `volnix/llm/providers/openai_compat.py`

---

## P0: Policy Engine NL Trigger Compilation (DONE)

**Status**: Complete, validated end-to-end

**Problem**: NL string triggers in policies used word-overlap matching that caused false positives. `pages.retrieve` matched "archiving pages" because "pages" appeared in both.

**Fix**: Compile NL triggers to structured dict triggers during world compilation via LLM. Runtime policy engine uses only deterministic dict matching.

**Validation**:
- Notion world: NL trigger compiled to `{action: "pages.update", condition: "input.archived == true"}`
- Market prediction: 3 NL triggers compiled to 5 dict triggers across twitter/reddit/slack
- Dynamic support center: 4 NL triggers compiled to 9 dict triggers across zendesk/stripe/slack
- Stock analysis: 4 NL triggers compiled to 5 dict triggers (alpaca), tested with CrewAI (Mode 2) and PydanticAI (Mode 1)
- 2781 tests passing, zero regressions
- All enforcement types tested: block, hold, escalate, log

**Files changed**:
- `volnix/engines/world_compiler/prompt_templates.py` — `POLICY_TRIGGER_COMPILATION` template
- `volnix/engines/world_compiler/engine.py` — `_compile_policy_triggers()` method
- `volnix/engines/policy/engine.py` — removed word-overlap, string triggers return False at runtime
- `volnix/engines/policy/enforcement.py` — `run_id` on all policy events
- `volnix/core/events.py` — `run_id`, `action`, `service_id` on base `Event`
- `volnix/pipeline/dag.py` — stamps context fields on all pipeline events
- `volnix/app.py` — `compiled_policies` passed through `configure_governance()`, `_ensure_active_run()`
- `volnix.toml` — LLM routing for `policy_trigger_compilation`
- `tests/engines/policy/test_engine.py` — updated string trigger tests, added compiled trigger tests
- `tests/engines/world_compiler/test_policy_compiler.py` — 8 new compilation tests
- Frontend: event type filter keys fixed to match backend dot convention
