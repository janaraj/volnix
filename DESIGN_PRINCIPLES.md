# Terrarium Design Principles

This document defines the architectural principles, design rules, patterns, and enforcement mechanisms that govern all Terrarium development. Every contributor must read and follow these principles. Code reviews must verify compliance.

---

## Architecture Principles

1. **Every module is isolated.** No module imports another module's internals. Cross-module communication is via events (bus) or protocol-typed references (dependency injection). If you find yourself writing `from terrarium.engines.state.internals import ...` in another engine, stop. You are violating isolation.

2. **All inter-engine communication goes through the event bus.** No direct function calls between engines. The bus is the nervous system. Engines publish events and subscribe to event types. There is no other pathway.

3. **Engines depend on abstractions (Protocols from `core/protocols.py`), never on concrete classes.** An engine receives its collaborators as protocol-typed constructor arguments. It never knows — and never needs to know — the concrete implementation.

4. **Concrete engine classes are imported only in the composition root (`registry/composition.py`).** Nowhere else. This is the single place where the dependency graph is wired together. All other modules import only protocols and value types.

5. **The pipeline DAG is defined in TOML config, not in code.** Steps are pluggable. The 7-step pipeline (permission, policy, budget, capability, responder, validation, commit) is the default, but the step list comes from config. Adding or reordering steps requires only a config change, not a code change.

---

## Design Rules

### DOs

- **DO use Pydantic frozen models for all value objects and events.** Every event, command, and domain value object is a `pydantic.BaseModel` with `model_config = ConfigDict(frozen=True)`. Immutability prevents accidental mutation and makes events safe to persist and replay.

- **DO use `typing.Protocol` for all inter-module contracts.** Protocols define the shape of what an engine expects from its collaborators. They are structural (duck-typed), not nominal. This keeps modules decoupled.

- **DO use `abc.ABC` only for `BaseEngine` (shared lifecycle plumbing).** `BaseEngine` provides `start()`, `stop()`, and health-check scaffolding. All other abstractions use `Protocol`.

- **DO record every significant action in the ledger** (pipeline steps, state mutations, LLM calls, gateway requests). The ledger is the flight recorder. If it did not produce a ledger entry, it did not happen.

- **DO use the persistence module for all database operations** — never create standalone SQLite connections. The persistence module manages connection pooling, WAL mode, migrations, and cleanup. Going around it creates resource leaks and consistency bugs.

- **DO use the LLM router for all LLM calls** — never call provider SDKs directly. The router handles provider selection, retry logic, budget tracking, and fallback. Direct SDK calls bypass all of this.

- **DO write tests alongside every module** — no untested code. Tests are not an afterthought. They are written as part of the module, not bolted on later.

- **DO use config values from the config registry** — never hardcode thresholds, timeouts, limits, or provider names. If a value might change between environments or deployments, it belongs in `terrarium.toml`.

- **DO use typed IDs (`EntityId`, `ActorId`, etc.)** — never pass raw strings for domain identifiers. Typed IDs prevent accidentally swapping an entity ID for an actor ID. They are cheap (`NewType` wrappers) and the type checker enforces them.

### DON'Ts

- **DON'T hardcode any values.** No magic numbers, no string literals for config. Everything comes from TOML config. If you write `timeout = 30` in engine code, that 30 must come from config.

- **DON'T put heuristics in code.** Decision logic must be config-driven or data-driven. If a threshold determines behavior, it lives in config or in a policy definition, not in a Python `if` statement with a hardcoded number.

- **DON'T import between engine packages.** `engines/policy/` must never import from `engines/state/`. `engines/responder/` must never import from `engines/budget/`. Engines communicate through the bus and depend only on protocols.

- **DON'T bypass the pipeline.** Every action flows through the 7-step DAG. There are no shortcuts. If an action needs special handling, add a pipeline step or configure conditional logic within a step — do not route around the pipeline.

- **DON'T bypass the gateway for external requests.** The gateway is the single entry/exit point for all external communication. MCP calls, HTTP requests, webhook deliveries — everything goes through the gateway. This ensures consistent authentication, rate limiting, and audit logging.

- **DON'T mutate state directly.** All state changes go through the State Engine's commit interface. The State Engine validates, versions, and persists state transitions atomically. Direct mutation creates inconsistencies that are impossible to debug.

- **DON'T skip tests.** Every PR must include tests for the code it adds or changes. No exceptions. Untested code is broken code that has not failed yet.

- **DON'T merge without passing CI.** Tests + coverage threshold must pass. No force-merges to bypass failing checks.

- **DON'T use sync I/O.** Everything is async. Use `aiosqlite`, `httpx`, async SDK methods. A single blocking call in the event loop degrades the entire system. If a library does not support async, wrap it in `asyncio.to_thread()`.

- **DON'T catch broad exceptions silently.** Handle specific errors. Log everything to the ledger. `except Exception: pass` is never acceptable. Catch the specific exception type, log it with context, and either recover or propagate.

---

## Architectural Patterns

### Event Bus — The Nervous System

All inter-engine communication flows through typed events. The bus persists every event to SQLite before delivery, creating an append-only event log. Events are immutable Pydantic models. Subscribers receive events via per-engine `asyncio.Queue` instances. The bus guarantees at-least-once delivery within a process.

### Ledger — The Flight Recorder

Separate from the bus. The ledger records every pipeline step, state mutation, LLM call, and gateway request. It is a structured audit log optimized for querying and replay. The ledger is not used for inter-engine communication — that is the bus's job. The ledger is for observability, debugging, and compliance.

### Pipeline — The Law

Every action flows through the same 7-step DAG: permission, policy, budget, capability, responder, validation, commit. No bypassing. The pipeline is configured in TOML and executed by the pipeline engine. Each step is an async callable that receives a context object and returns a result. Steps can short-circuit (e.g., policy can reject an action before it reaches the responder).

### Gateway — The Single Door

All external requests enter and exit through the gateway. The gateway handles protocol adaptation (MCP, HTTP, WebSocket), authentication, rate limiting, and audit logging. No engine makes external calls directly. If an engine needs to call an external API, it publishes a gateway request event and the gateway handles it.

### Composition Root Pattern

Concrete classes are imported only in `registry/composition.py`. This is the single place where the dependency graph is assembled. All other modules depend only on protocols and value types. This makes it trivial to swap implementations for testing (inject mocks) or for different deployment configurations.

### Category-Pack-Profile Hierarchy

Tier 1 packs implement semantic categories (communication, productivity, social), not specific services. Service-specific features layer as Tier 2 profiles on top of category packs. This means adding a new service does not require a new pack — it requires a profile that maps the service's specifics onto an existing category's semantics.

### LLM Provider Generalization

OpenAI-compatible base provider handles most LLMs (OpenAI, Gemini via compatibility endpoint, Ollama, vLLM, etc.). Native SDK wrappers exist only for APIs with unique features (Anthropic's extended thinking, etc.). Adding a new OpenAI-compatible provider requires only a config entry — zero code changes.

### Multi-Agent Isolation

Agents share world state but see different slices via visibility scoping. Each agent's perception is filtered through their visibility rules before reaching the pipeline. All inter-agent communication goes through world channels — agents cannot directly access each other's internal state.

### Dynamic Policies

Policies use a YAML condition language with registered functions (`time_since`, `count_today`, `has_role`, etc.). Community templates provide starting points. Policies can be created, modified, and deleted at runtime. The condition language is intentionally not Turing-complete — it supports boolean logic, comparisons, and registered functions, but not loops or arbitrary computation.

**The Two-Phase Model:**
- Phase A (compilation) generates all world data via LLM, seeded for reproducibility, shaped by reality dimensions. Dimensions determine what IS in the world (stale data, difficult actors, auth gaps) — they are baked into entities at compile time.
- Phase B (runtime) has services respond to whatever exists in state. Services don't decide "should this be stale?" — the data already IS stale. Services return reality as it exists.
- This separation applies to every tier: Tier 1 packs and Tier 2 profiles both serve data that was shaped by dimensions during compilation.

**Behavior Modes:**
- Worlds have three behavior modes: static (frozen after compilation), reactive (responds to agent actions), dynamic (alive, generates events). The behavior mode controls the Animator, not the reality dimensions.

**Reality Dimensions Are Personality Traits:**
- Reality dimensions are personality traits of the world, not engineering parameters. They guide LLM generation and animation, not code-applied percentages. "Somewhat neglected information" means the LLM creates a world where data management has been neglected — contextually and narratively coherent, not randomly distributed. Two-level config: labels for simple users, per-attribute numbers for advanced.

**Five User-Facing Concepts (the stable mental model):**
- Description, reality, behavior, fidelity, mode — these are the API contract from day one to horizon. The surface stays simple as internals grow. This is the design constraint that prevents feature creep.

**Progressive Disclosure:**
- Level 1: one-line CLI with preset (ideal/messy/hostile) -> Level 2: preset + dimension overrides (labels or per-attribute numbers) -> Level 3: full YAML (two files: world definition + compiler settings) -> Level 4: custom packs + plugins.
- Every level produces the same internal WorldPlan. More depth is optional, never forced.

**Governed vs. Ungoverned:**
- Running the same world in both modes and diffing the results is a core feature, not an afterthought. Mode is a first-class dimension alongside reality and fidelity.

**Service Fidelity (corrected):**
- Tier 1: deterministic code (no LLM at runtime). Tier 2: profile-constrained LLM.
- There is no Tier 3 runtime mode. Unknown services are bootstrapped at compile time (inference produces a Tier 2-like surface). At runtime, only Tier 1 and Tier 2 exist.

**Condition Overlays (post-MVP growth strategy):**
- Reality dimensions expand via focused overlays (economics, compliance, market-noise), not by growing a flat parameter list. Each overlay is self-contained and additive.

---

## Async Flow Pattern

The entire system is async-first:

- **All I/O is async.** Database access via `aiosqlite`. HTTP via `httpx`. LLM calls via async SDK methods. File I/O via `aiofiles` where needed.

- **Each engine has its own `asyncio.Queue` on the bus.** Events are dispatched to the appropriate queue based on subscription. Each engine processes its queue independently.

- **Pipeline steps are awaited sequentially within one action.** A single action flows through permission -> policy -> budget -> capability -> responder -> validation -> commit in order. Each step completes before the next begins.

- **Multiple agents' actions can be in-flight concurrently.** The pipeline processes one action at a time per agent, but different agents' pipelines run concurrently.

- **State Engine commit is serialized.** Single-writer SQLite with WAL mode for concurrent reads. Commits are queued and processed one at a time to prevent conflicts.

- **Side effects are processed asynchronously.** When a pipeline step produces side effects, they are enqueued for processing after the current action completes. Side effects flow through the full pipeline.

- **Animator runs as a concurrent background task.** The animator observes state changes and generates narrative/environmental effects independently of the action pipeline.

---

## Enforcement

These principles are not aspirational — they are enforced mechanically:

- **Test harness:** 80% coverage per module, 95% for critical paths (pipeline, bus, state engine). CI fails below these thresholds.

- **Ledger completeness:** Every pipeline step, state mutation, and LLM call must produce a ledger entry. Integration tests verify ledger entries exist for every code path.

- **Modularity enforcement:** Import analysis in CI ensures no cross-engine imports. A script scans all `import` and `from` statements and fails if any engine package imports from another engine package.

- **Config-driven enforcement:** Linting rules flag string literals and numeric constants in engine code that should be configurable. Code review catches what linting misses.
