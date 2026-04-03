# Architecture

This document covers Terrarium's architectural design: the two-half model, the 10 engines, the governance pipeline, and the key patterns that hold the system together.

For the full design rules and enforcement mechanisms, see [DESIGN_PRINCIPLES.md](../DESIGN_PRINCIPLES.md).

---

## The Two Halves

Terrarium separates **structure** from **content**:

**World Law (Deterministic Engine)** owns state, events, the causal graph, permissions, policy enforcement, budget accounting, time, visibility, mutation validation, and replay. The engine never guesses, never generates text, never decides what a service "would probably do." It enforces structure.

**World Content (Generative Layer)** creates realistic data, service behavior, actor responses, and scenario complications. But it operates inside constraints set by the engine. The generative layer proposes; the engine disposes. A generated response that violates state consistency is rejected. A generated mutation that exceeds budget is denied.

This separation means the system is auditable: you can always trace why something happened (causal graph), what rules were checked (pipeline log), and whether the outcome was deterministic or generated (fidelity tier).

---

## Two-Phase Model

### Phase A: World Compilation

The compiler transforms user intent into a runnable world. The LLM generates all world data (entities, actors, service state) seeded for reproducibility and shaped by reality dimensions.

The compiler executes a 7-step pipeline:

```
Parse --> Classify --> Resolve --> Generate --> Validate --> Inject Seeds --> Snapshot
```

Reality dimensions determine what IS in the world at compile time. A "messy" world gets stale data, missing fields, and flaky services baked into the initial state.

### Phase B: Runtime

The governance pipeline processes every agent action. Services return data as it exists in state. No LLM decides runtime reality for Tier 1 services -- it was baked in during compilation.

---

## The 10 Engines

Every engine inherits from `BaseEngine`, which provides lifecycle hooks and event bus integration. Engines communicate only through the event bus and typed protocols -- never by importing each other directly.

### World Compiler (`engines/world_compiler/`)

Transforms natural language or YAML descriptions into runnable worlds. Handles schema resolution, data generation, and plan review. The compiler resolves services through a priority chain:

1. Semantic classification (map to category, inherit primitives)
2. Verified pack (Tier 1, deterministic)
3. Curated profile (Tier 2, LLM-constrained)
4. External spec (OpenAPI, MCP Registry)
5. LLM inference (bootstrap from category primitives)

### State Engine (`engines/state/`)

Single source of truth for all entity data. Manages entity storage, the event log, causal graph, and snapshot/fork/diff operations. All state mutations must go through its commit interface.

### Policy Engine (`engines/policy/`)

Evaluates governance rules written in a YAML condition language. Four enforcement modes, in precedence order:

| Mode | Behavior |
|------|----------|
| `block` | Reject the action immediately |
| `hold` | Pause for approval (e.g., supervisor sign-off) |
| `escalate` | Allow but flag for review |
| `log` | Record but don't interfere |

### Permission Engine (`engines/permission/`)

RBAC plus visibility scoping. Determines what each actor can see and do. Filters query results by actor scope -- an agent asking for "all tickets" only sees tickets they have permission to access.

### Budget Engine (`engines/budget/`)

Tracks resource consumption per actor across four dimensions: `api_calls`, `llm_spend_usd`, `world_actions`, and `time`. Emits warning, critical, and exhausted events as thresholds are crossed.

### World Responder (`engines/responder/`)

Generates service responses. Tier 1 (verified packs) uses deterministic pack logic with no LLM. Tier 2 (profiled services) uses LLM generation constrained by schemas, state machines, and response templates.

### World Animator (`engines/animator/`)

Generates events between agent turns. Controlled by behavior mode:

- **static**: off. World frozen after compilation.
- **reactive**: responds only to agent actions or inaction.
- **dynamic**: fully active. Generates contextual events on its own schedule.

Two layers: deterministic schedule (cron-like) plus generative content with a creativity budget.

### Agency Engine (`engines/agency/`)

Manages internal actor lifecycle. Handles event-driven activation (which actors should respond after each event), tiered action generation (Tier 1 deterministic check, Tier 2 batch LLM, Tier 3 individual LLM), and collaborative communication through subscriptions.

### Agent Adapter (`engines/adapter/`)

Translates between external protocols (MCP, HTTP REST, OpenAI function calling, Anthropic tool use) and internal world actions. Handles tool discovery, request routing, and capability gap detection.

### Report Generator (`engines/reporter/`)

Produces governance scorecards, capability gap logs, causal traces, and counterfactual diffs. Scores are derived from events, not LLM judgment. Observes in two directions: world challenges presented to agents, and agent behavior within the world.

---

## The 7-Step Governance Pipeline

Every action flows through this pipeline. No exceptions -- agent actions, animator events, side effects, and approval responses all follow the same path.

```
Permission --> Policy --> Budget --> Capability --> Responder --> Validation --> Commit
```

| Step | What It Does |
|------|-------------|
| **Permission** | Checks RBAC: does this actor have access to this service and action? |
| **Policy** | Evaluates governance rules: should this action be blocked, held, escalated, or logged? |
| **Budget** | Checks resource limits: does this actor have remaining API calls, LLM spend, etc.? |
| **Capability** | Verifies the target service can handle this action type |
| **Responder** | Generates the service response (deterministic for Tier 1, LLM-constrained for Tier 2) |
| **Validation** | Checks the response for state consistency and schema conformance |
| **Commit** | Writes the event to state, updates the causal graph, publishes to the event bus |

Steps can short-circuit: if policy blocks an action, the pipeline stops before reaching the responder. The pipeline is configured in `terrarium.toml` under `[pipeline]`.

---

## Event Bus and Ledger

These are separate concerns:

**Event Bus** (`bus/`): Inter-engine communication via typed, immutable Pydantic events. Events are persisted to SQLite before delivery. Each engine has its own `asyncio.Queue` for non-blocking consumption.

**Ledger** (`ledger/`): Audit log for observability. Records pipeline steps, state mutations, LLM calls, and gateway requests. The ledger is append-only and queryable. It is not used for inter-engine communication.

---

## Semantic Kernel

The kernel (`kernel/`) maps services to semantic categories: communication, work-management, money, authority, identity, storage, code, scheduling, monitoring. This is a static registry with no LLM involvement.

When the compiler encounters a service name (e.g., "Stripe"), the kernel classifies it to a category, inherits core primitives, then specializes. Bootstrapped services start from category semantics rather than from zero.

---

## Fidelity Tiers

| Tier | Name | LLM at Runtime? | Reproducibility |
|------|------|-----------------|----------------|
| **Tier 1** | Verified Pack | No | Fully deterministic. Same seed = same world. |
| **Tier 2** | Profile-Backed | Yes (constrained) | Seeded. Similar character across runs. |

There is no Tier 3 at runtime. Bootstrapping (LLM inference of unknown services) happens at compile time and produces a Tier 2 profile.

---

## Composition Root

`registry/composition.py` is the **only** place that imports concrete engine classes. All other code depends on `typing.Protocol` interfaces from `core/protocols.py`. This is strictly enforced: no cross-engine imports are allowed.

---

## Key Patterns

### Async Everywhere
All I/O is async. `aiosqlite` for persistence, `httpx` for HTTP, async SDK methods for LLM providers. Sync libraries are wrapped with `asyncio.to_thread()`.

### Frozen Pydantic Models
All value objects and events use `model_config = ConfigDict(frozen=True)`. Events are immutable once created.

### Typed IDs
`EntityId`, `ActorId`, `ServiceId`, `EventId`, `WorldId`, `RunId`, etc. are `NewType` wrappers in `core/types.py`. Raw strings are never used for domain identifiers.

### No Hardcoded Values
Thresholds, timeouts, limits, and provider names come from TOML config. Engine code reads from its injected config, not from constants.

### Single Source of Truth
- State changes go through the State Engine's commit interface
- External requests go through the Gateway
- LLM calls go through the LLM Router
- The composition root is the only place that wires concrete implementations
