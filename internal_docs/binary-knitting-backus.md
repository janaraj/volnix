# Terrarium — Technical Design Guide & Implementation Plan

## Context

Terrarium is a world engine for AI agents — it creates complete, stateful, simulated realities where agents live and get evaluated before production deployment. The repo is currently empty. This design guide establishes the technical architecture, core abstractions, engine contracts, and implementation sequence. **All feature development must follow this guide.**

User requirements: pure async/event-driven, fully isolated engines, configurable DAG pipeline, SOLID principles, zero hardcoding, runtime-tunable TOML config, skeleton-first approach. Mandatory test coverage for every module — tests must catch regressions as development progresses.

**This run creates SKELETONS ONLY** — directory structure, all files with module docstrings, class/function signatures with `...` or `pass` bodies, type annotations, and test file stubs. No implementation logic. The skeleton establishes the architecture so that all future feature work fills in the stubs.

---

## Repo-Root Documents

Two mandatory documents live at the repo root:

### `DESIGN_PRINCIPLES.md` — The Law of the Codebase

The dos, don'ts, and enforcement rules that every contributor must follow. Created as part of the skeleton. Contents:

**Architecture Principles:**
- Every module is isolated. No module imports another module's internals. Cross-module communication is via events (bus) or protocol-typed references (DI).
- All inter-engine communication goes through the event bus. No direct function calls between engines.
- Engines depend on abstractions (Protocols from `core/protocols.py`), never on concrete classes.
- Concrete engine classes are imported only in the composition root (`registry/composition.py`). Nowhere else.
- The pipeline DAG is defined in TOML config, not in code. Steps are pluggable.

**Design Rules (DOs):**
- DO use Pydantic frozen models for all value objects and events.
- DO use `typing.Protocol` for all inter-module contracts.
- DO use `abc.ABC` only for `BaseEngine` (shared lifecycle plumbing).
- DO record every significant action in the ledger (pipeline steps, state mutations, LLM calls, gateway requests).
- DO use the persistence module for all database operations — never create standalone SQLite connections.
- DO use the LLM router for all LLM calls — never call provider SDKs directly.
- DO write tests alongside every module — no untested code.
- DO use config values from the config registry — never hardcode thresholds, timeouts, limits, or provider names.
- DO use typed IDs (EntityId, ActorId, etc.) — never pass raw strings for domain identifiers.

**Design Rules (DON'Ts):**
- DON'T hardcode any values. No magic numbers, no string literals for config. Everything comes from TOML config.
- DON'T put heuristics in code. Decision logic must be config-driven or data-driven.
- DON'T import between engine packages. `engines/policy/` must never import from `engines/state/`.
- DON'T bypass the pipeline. Every action (agent, animator, side effect) flows through the 7-step DAG.
- DON'T bypass the gateway for external requests. The gateway is the single entry/exit point.
- DON'T mutate state directly. All state changes go through the State Engine's commit interface.
- DON'T skip tests. Every PR must include tests for the code it adds or changes.
- DON'T merge without passing CI. Tests + coverage threshold must pass.
- DON'T use sync I/O. Everything is async. Use `aiosqlite`, `httpx`, async SDK methods.
- DON'T catch broad exceptions silently. Handle specific errors. Log everything to the ledger.

**Architectural Patterns:**
- **Event Bus is the nervous system**: all inter-engine communication flows through typed events. Engines never call each other directly. The bus persists every event to SQLite before delivery — the log is always complete.
- **Ledger is the flight recorder**: separate from the bus. Records every pipeline step, state mutation, LLM call, gateway request. Used for replay, debugging, and audit.
- **Pipeline is the law**: every action (agent, animator, side effect) flows through the same 7-step DAG. No bypassing.
- **Gateway is the single door**: all external requests enter and exit through the gateway. Monitoring, rate limiting, and audit happen here.
- **Composition root pattern**: concrete engine classes are imported only in `registry/composition.py`. Everywhere else, engines are referenced by Protocol type or engine_name string.
- **Category→Pack→Profile hierarchy**: Tier 1 packs implement semantic categories (email, chat, payments), not specific services. Service-specific features layer on as Tier 2 profiles.
- **LLM provider generalization**: use OpenAI-compatible base provider for most LLMs. Only implement native SDK wrappers for providers with unique APIs (Anthropic). New providers added via config (zero code).
- **Multi-agent isolation**: agents share world state but see different slices via visibility scoping. All inter-agent communication goes through world channels (pipeline enforced).
- **Dynamic policies**: policies defined in YAML condition language, contributed as community templates, creatable at runtime. Not Turing-complete — fast and deterministic.

**Async Flow Pattern:**
- All I/O is async (aiosqlite, httpx, async SDK calls)
- Each engine has its own asyncio.Queue on the bus (consumer task drains it)
- Pipeline steps are awaited sequentially within one action (dependency chain)
- Multiple agents' actions can be in-flight concurrently (different pipeline instances)
- State Engine commit is serialized (single-writer SQLite, WAL mode for concurrent reads)
- Side effects are processed asynchronously via a background task
- Animator runs as a concurrent background task between agent turns

**Enforcement:**
- Test harness is mandatory: minimum 80% coverage per module, 95% for critical paths (pipeline, bus, state engine).
- Ledger is mandatory: every pipeline step, every state mutation, every LLM call must produce a ledger entry.
- Modularity is mandatory: import analysis in CI ensures no cross-engine imports.
- Config-driven is mandatory: no string literals or numeric constants that should be configurable.

### `OPEN_QUESTIONS.md` — Unresolved Design Questions

Questions that need resolution before their dependent phases begin. Tracked with phase dependencies.

| # | Question | Phase Dependency | Status |
|---|----------|-----------------|--------|
| 1 | **Side effect recursion limit behavior** — When max depth is hit, should the pipeline silently drop the side effect, log a warning, or raise an error event? What signals should the agent/report receive? | Resolve before Phase 2 (pipeline module) | Open |
| 2 | **Semantic Kernel query interface** — How should engines query the kernel? Direct function calls (it's a static registry) or through a protocol? What's the lookup API signature for service→category→primitives? | Resolve before Phase 5 (kernel + responder) | Open |
| 3 | **Pack handler contract (Tier 1 handler interface)** — What's the exact interface a pack handler implements? How does it receive state, how does it return ResponseProposal? How are pack-specific state machines registered with the validation framework? | Resolve before Phase 5 (packs) | Open |
| 4 | **Natural language world compilation prompt architecture** — What's the prompt chain for NL→YAML? Single-shot or multi-step (extract services → resolve schemas → generate entities → validate)? How is the world plan presented for user review? | Resolve before Phase 6 (world compiler engine) | Open |
| 5 | **World Compiler output schema for NL input** — What's the exact intermediate representation between NL parsing and YAML world definition? Is there a `WorldPlan` schema that captures the compiler's output before instantiation? | Resolve before Phase 6 (world compiler engine) | Open |
| 6 | **Animator scheduling semantics** — Time-triggered events (fire at absolute simulated time) vs event-triggered (fire in reaction to world state changes). Or both? How does the animator interact with the simulated clock? What's the tick model? | Resolve before Phase 6 (animator engine) | Open |
| 7 | **Policy condition language parser** — What parser do we use for the condition expression language? Hand-written recursive descent, or a library like `lark`? How do we handle registered function calls within conditions? | Resolve before Phase 4 (policy engine) | Open |
| 8 | **Visualization protocol** — SSE vs WebSocket for live event streaming to UX layers? Do we need a separate observation protocol or is the bus subscription model sufficient? | Resolve before Phase 8 (dashboard) | Open |

These questions will be resolved through design spikes during or just before their dependent phases.

---

## Tech Stack

| Concern | Choice | Why |
|---------|--------|-----|
| Language | Python 3.12+ / asyncio | Spec alignment, LLM SDK ecosystem |
| Config | TOML (layered) | Python-native, comments, readable |
| Event Bus | In-process async fanout + SQLite append-only ledger | Fast delivery + durable persistence |
| State Storage | SQLite (via aiosqlite) | Zero-infra, file-based, snapshot-friendly |
| Data Models | Pydantic v2 | Validation, serialization, frozen models |
| LLM | Provider-agnostic ABC (anthropic/openai SDKs) | Swappable, per-engine configurable |
| CLI | Typer | Modern, type-safe |
| Dashboard | FastAPI + htmx | Lightweight, SSE for live updates |
| Testing | pytest + pytest-asyncio + coverage | Mandatory coverage, regression protection |
| MCP | mcp (Python SDK) | Agent ↔ world service communication protocol |
| ACP | acp SDK (when available) | Agent ↔ agent communication protocol |
| HTTP Server | FastAPI / uvicorn | REST endpoints for HTTP adapter + dashboard |

---

## Design Principles

1. **Single Responsibility** — each engine/module does one thing
2. **Open/Closed** — extend via Protocols/ABCs, not modification
3. **Liskov Substitution** — any engine implementation is swappable
4. **Interface Segregation** — minimal interface per engine
5. **Dependency Inversion** — engines depend on abstractions (Protocols), never on concrete classes
6. **Event-Driven** — all inter-engine communication via typed events on async bus
7. **Config-Driven** — all behavior parameterized through TOML; zero hardcoding
8. **Composition Root** — concrete classes imported only in `registry.py`
9. **Ledger Everything** — every step, every mutation, every LLM call recorded for replay/debug
10. **Test-First** — every module ships with tests; no untested code enters the codebase

---

## Project Structure

```
terrarium/
├── pyproject.toml
├── DESIGN_PRINCIPLES.md                    # The Law — dos, don'ts, enforcement rules
├── OPEN_QUESTIONS.md                       # Unresolved design questions with phase deps
├── .gitignore
├── terrarium.toml                          # Base config (committed)
├── terrarium.development.toml              # Dev overrides
├── terrarium.local.toml                    # Local overrides (gitignored)
│
├── terrarium/
│   ├── __init__.py                         # Exports __version__
│   ├── __main__.py                         # Entry: calls cli.main()
│   ├── cli.py                              # Typer CLI commands
│   │
│   ├── core/                               # Shared abstractions — NO engine logic
│   │   ├── __init__.py
│   │   ├── types.py                        # NewType IDs, enums, frozen value objects
│   │   ├── events.py                       # Event type hierarchy (Pydantic frozen models)
│   │   ├── protocols.py                    # Protocol classes for all engines + PipelineStep
│   │   ├── engine.py                       # BaseEngine ABC with lifecycle
│   │   ├── errors.py                       # Error hierarchy
│   │   └── context.py                      # ActionContext, StepResult, ResponseProposal
│   │
│   ├── bus/                                # Event Bus — full module (the nervous system)
│   │   ├── __init__.py                     # Exports EventBus
│   │   ├── types.py                        # Bus-specific types (Subscriber, Subscription, etc.)
│   │   ├── bus.py                          # Core EventBus: orchestrates fanout + persistence
│   │   ├── fanout.py                       # Topic-based async fanout to subscriber queues
│   │   ├── persistence.py                  # SQLite append-only ledger for events
│   │   ├── replay.py                       # Replay engine: read from ledger, re-deliver
│   │   ├── middleware.py                   # Bus middleware chain (logging, metrics, filtering)
│   │   └── config.py                       # BusConfig schema
│   │
│   ├── ledger/                             # Ledger — audit trail for everything
│   │   ├── __init__.py                     # Exports Ledger
│   │   ├── ledger.py                       # Core ledger: append-only structured log
│   │   ├── entries.py                      # Ledger entry types (PipelineStep, StateMutation,
│   │   │                                   #   LLMCall, EngineAction, GatewayRequest, etc.)
│   │   ├── query.py                        # Query interface: filter, search, aggregate
│   │   ├── export.py                       # Export: JSON, CSV, replay-compatible format
│   │   └── config.py                       # LedgerConfig schema
│   │
│   ├── persistence/                        # Unified persistence layer
│   │   ├── __init__.py                     # Exports connection management
│   │   ├── manager.py                      # ConnectionManager: pool, lifecycle, health
│   │   ├── database.py                     # Database ABC: async CRUD, transactions, migrations
│   │   ├── sqlite.py                       # SQLite implementation (via aiosqlite)
│   │   ├── migrations.py                   # Schema migration runner
│   │   ├── snapshot.py                     # Snapshot storage: save/load full world state
│   │   └── config.py                       # PersistenceConfig schema (paths, pool sizes, etc.)
│   │
│   ├── gateway/                            # Gateway — single entry/exit point
│   │   ├── __init__.py                     # Exports Gateway
│   │   ├── gateway.py                      # Core gateway: route requests, emit responses
│   │   ├── router.py                       # Request router: map inbound to ActionContext
│   │   ├── monitor.py                      # Observability: request/response logging, metrics
│   │   ├── rate_limiter.py                 # Per-actor rate limiting (configurable)
│   │   ├── auth.py                         # Authentication for hosted/remote mode
│   │   ├── middleware.py                   # Gateway middleware chain
│   │   └── config.py                       # GatewayConfig schema
│   │
│   ├── llm/                                # LLM Provider — full module, per-engine configurable
│   │   ├── __init__.py                     # Exports LLMRouter
│   │   ├── types.py                        # LLMRequest, LLMResponse, LLMUsage, ProviderInfo
│   │   ├── provider.py                     # LLMProvider ABC (the interface all providers implement)
│   │   ├── router.py                       # LLMRouter: route requests to provider per engine/use-case
│   │   ├── registry.py                     # ProviderRegistry: discover, register, lookup providers
│   │   ├── providers/                      # Provider implementations
│   │   │   ├── __init__.py
│   │   │   ├── anthropic.py               # Anthropic native API (uses anthropic SDK)
│   │   │   ├── openai_compat.py           # OpenAI-compatible — works with OpenAI, Gemini, Together,
│   │   │   │                              #   Groq, Ollama, vLLM, any provider with OpenAI-format API
│   │   │   │                              #   Configurable via base_url. Zero code needed for new providers.
│   │   │   ├── google.py                  # Google Gemini native API (optional, for Gemini-specific features)
│   │   │   └── mock.py                    # Mock provider: deterministic responses for testing
│   │   ├── tracker.py                      # Token usage + cost tracking per-actor, per-engine, per-model
│   │   └── config.py                       # LLMConfig: provider configs, routing table, defaults
│   │
│   ├── config/                             # Configuration system — full module
│   │   ├── __init__.py                     # Exports ConfigLoader, TerrariumConfig
│   │   ├── loader.py                       # TOML loader: layering, env vars, secure refs
│   │   ├── schema.py                       # TerrariumConfig root + all section schemas
│   │   ├── registry.py                     # ConfigRegistry: runtime access + change notification
│   │   ├── tunable.py                      # Runtime-tunable field system (watch + callback)
│   │   └── validation.py                   # Config validation beyond Pydantic (cross-field, etc.)
│   │
│   ├── pipeline/                           # Runtime Pipeline — full module (the 7-step DAG)
│   │   ├── __init__.py                     # Exports PipelineDAG
│   │   ├── dag.py                          # DAG definition, execution, short-circuit logic
│   │   ├── step.py                         # PipelineStep protocol + base step utilities
│   │   ├── builder.py                      # Build pipeline from TOML config + registry
│   │   ├── side_effects.py                 # Side effect queue + re-entry processing
│   │   └── config.py                       # PipelineConfig schema
│   │
│   ├── validation/                         # Validation Framework — full module
│   │   ├── __init__.py                     # Exports validators
│   │   ├── schema.py                       # JSON schema validation for LLM outputs
│   │   ├── state_machine.py               # State transition validation
│   │   ├── consistency.py                 # Cross-entity reference validation
│   │   ├── temporal.py                     # Temporal constraint validation
│   │   ├── amounts.py                      # Amount/constraint validation (refund <= charge, etc.)
│   │   └── pipeline.py                     # Validation pipeline: chain validators, retry logic
│   │
│   ├── registry/                           # Engine Registry / DI — full module
│   │   ├── __init__.py                     # Exports EngineRegistry
│   │   ├── registry.py                     # EngineRegistry: holds instances, topological sort
│   │   ├── wiring.py                       # Wire engines to bus, inject protocol dependencies
│   │   ├── composition.py                  # Composition root: create_default_registry()
│   │   └── health.py                       # Health check aggregator across all engines
│   │
│   ├── engines/                            # Each engine in its own package
│   │   ├── __init__.py
│   │   ├── world_compiler/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py                   # WorldCompilerEngine
│   │   │   ├── schema_resolver.py          # Priority chain: verified→profiled→external→inferred
│   │   │   ├── data_generator.py           # Batch entity creation with cross-linking
│   │   │   ├── plan_reviewer.py            # Present compiled world plan
│   │   │   └── config.py
│   │   ├── state/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py                   # StateEngine
│   │   │   ├── store.py                    # Entity CRUD (uses persistence/ module)
│   │   │   ├── event_log.py               # World event log (uses persistence/ module)
│   │   │   ├── causal_graph.py            # DAG: add edge, traverse fwd/bwd
│   │   │   └── config.py
│   │   ├── policy/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py                   # PolicyEngine (also PipelineStep)
│   │   │   ├── evaluator.py               # Condition parser + evaluator (expression language)
│   │   │   ├── enforcement.py             # Hold/block/escalate/log dispatch
│   │   │   ├── templates.py               # Policy template loader + instantiation
│   │   │   ├── functions.py               # Registered policy function registry (escape hatch)
│   │   │   ├── loader.py                  # Load policies from YAML files (world def + standalone)
│   │   │   ├── runtime.py                 # Runtime policy CRUD (add/modify/delete during simulation)
│   │   │   ├── config.py
│   │   │   └── data/                      # Policy data — YAML definitions & templates
│   │   │       ├── builtin/               # Built-in policy templates (ship with Terrarium)
│   │   │       │   ├── financial_guardrails.yaml    # Refund approval chains
│   │   │       │   ├── sla_enforcement.yaml         # SLA escalation rules
│   │   │       │   ├── communication_protocol.yaml  # Communication expectations
│   │   │       │   └── authority_boundaries.yaml    # Role-based action limits
│   │   │       ├── community/             # Community-contributed policy templates
│   │   │       │   └── .gitkeep
│   │   │       └── schema/                # Policy YAML schema definitions
│   │   │           ├── policy_schema.yaml           # Schema for policy definitions
│   │   │           └── template_schema.yaml         # Schema for policy templates
│   │   ├── permission/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py                   # PermissionEngine (also PipelineStep)
│   │   │   ├── scope.py                    # Visibility scope computation
│   │   │   ├── authority.py               # Action-specific constraint validation
│   │   │   └── config.py
│   │   ├── budget/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py                   # BudgetEngine (also PipelineStep)
│   │   │   ├── tracker.py                 # Per-actor resource accounting
│   │   │   └── config.py
│   │   ├── responder/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py                   # WorldResponderEngine (also PipelineStep)
│   │   │   ├── tier1.py                    # Route to verified pack handler
│   │   │   ├── tier2.py                    # Profile-constrained LLM generation
│   │   │   ├── tier3.py                    # Inferred LLM generation
│   │   │   └── config.py
│   │   ├── animator/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py                   # WorldAnimatorEngine
│   │   │   ├── scheduler.py               # Deterministic timer-based events
│   │   │   ├── generator.py               # LLM-driven organic events
│   │   │   └── config.py
│   │   ├── adapter/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py                   # AgentAdapterEngine (also PipelineStep for capability)
│   │   │   ├── protocols/                  # Protocol implementations (one per protocol)
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py                 # ProtocolAdapter ABC (translate inbound/outbound)
│   │   │   │   ├── mcp_server.py           # MCP Server — exposes world services as MCP tools
│   │   │   │   │                           #   Uses `mcp` Python SDK. Agents connect as MCP clients.
│   │   │   │   │                           #   Each world service → set of MCP tools.
│   │   │   │   │                           #   Tool calls → ActionContext → pipeline.
│   │   │   │   │                           #   Pipeline result → MCP tool result.
│   │   │   │   ├── acp_server.py           # ACP Server — agent-to-agent communication
│   │   │   │   │                           #   Agent discovery through world social fabric.
│   │   │   │   │                           #   Messages routed through world channels (chat/email).
│   │   │   │   │                           #   Visibility rules enforced by Permission Engine.
│   │   │   │   ├── openai_compat.py        # OpenAI-compatible function calling endpoint
│   │   │   │   ├── anthropic_compat.py     # Anthropic-compatible tool use endpoint
│   │   │   │   └── http_rest.py            # Raw REST API — service endpoints look like real APIs
│   │   │   ├── tool_manifest.py            # Generate tool manifests per protocol per actor
│   │   │   ├── observation.py              # Deliver world observations to agents (state changes)
│   │   │   └── config.py
│   │   ├── reporter/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py                   # ReportGeneratorEngine
│   │   │   ├── scorecard.py               # Governance scores from event log
│   │   │   ├── capability_gaps.py         # Gap response classification
│   │   │   ├── causal_trace.py            # Render causal chains
│   │   │   ├── diff.py                     # Counterfactual comparison
│   │   │   └── config.py
│   │   └── feedback/
│   │       ├── __init__.py
│   │       ├── engine.py                   # FeedbackEngine
│   │       ├── annotations.py             # Annotation store per service
│   │       ├── promotion.py               # Tier promotion pipeline
│   │       ├── sync.py                     # External source drift detection
│   │       └── config.py
│   │
│   ├── kernel/                             # Semantic Kernel (static registry, not an engine)
│   │   ├── __init__.py
│   │   ├── registry.py                     # Lookup: service → category → primitives
│   │   ├── categories.py                  # Category definitions
│   │   ├── primitives.py                  # Primitives per category
│   │   └── data/
│   │       ├── categories.toml            # Static category data
│   │       └── services.toml              # Service-to-category mappings
│   │
│   ├── templates/                          # World Templates — inheritance & composition
│   │   ├── __init__.py                     # Exports TemplateRegistry
│   │   ├── base.py                         # BaseTemplate ABC: define, inherit, compose
│   │   ├── registry.py                     # TemplateRegistry: discover, load, validate templates
│   │   ├── composer.py                     # Template composition: merge multiple templates
│   │   ├── loader.py                       # Load template from YAML file
│   │   ├── builtin/                        # Built-in templates
│   │   │   ├── __init__.py
│   │   │   ├── customer_support.yaml      # Customer Support Team template
│   │   │   ├── customer_support.py        # Template class with customization hooks
│   │   │   ├── incident_response.yaml     # Incident Response template
│   │   │   ├── incident_response.py
│   │   │   ├── open_sandbox.yaml          # Open Sandbox template
│   │   │   └── open_sandbox.py
│   │   └── config.py                       # TemplateConfig schema
│   │
│   ├── runs/                               # Run Management — track, snapshot, compare
│   │   ├── __init__.py                     # Exports RunManager
│   │   ├── manager.py                      # RunManager: create, track, complete runs
│   │   ├── snapshot.py                     # SnapshotManager: save/restore full world state
│   │   ├── artifacts.py                    # Run artifacts: reports, logs, events, config used
│   │   ├── comparison.py                   # Compare multiple runs (counterfactual diffs)
│   │   ├── replay.py                       # Replay a run from snapshot + event log
│   │   └── config.py                       # RunConfig schema (storage paths, retention, etc.)
│   │
│   ├── packs/                              # World Packs (category→pack→profile hierarchy)
│   │   ├── __init__.py
│   │   ├── base.py                         # ServicePack ABC (Tier 1), ServiceProfile ABC (Tier 2)
│   │   ├── verified/                      # Tier 1: CATEGORY-LEVEL packs (not service-level)
│   │   │   ├── __init__.py                #   "email" pack works for Gmail, Outlook, Yahoo, etc.
│   │   │   ├── email/                     #   Implements universal email primitives
│   │   │   │   ├── {__init__,pack,handlers,state_machines}.py
│   │   │   ├── chat/                      #   Implements universal chat primitives (Slack, Teams, etc.)
│   │   │   │   ├── {__init__,pack,handlers,state_machines}.py
│   │   │   ├── tickets/                   #   Universal ticket lifecycle (Jira, Zendesk, etc.)
│   │   │   │   ├── {__init__,pack,handlers,state_machines}.py
│   │   │   ├── payments/                  #   Universal payment primitives (Stripe, PayPal, etc.)
│   │   │   │   ├── {__init__,pack,handlers,state_machines}.py
│   │   │   ├── repos/                     #   Universal repo primitives (GitHub, GitLab, etc.)
│   │   │   │   ├── {__init__,pack,handlers,state_machines}.py
│   │   │   └── calendar/                  #   Universal scheduling (GCal, Outlook Cal, etc.)
│   │   │       ├── {__init__,pack,handlers,state_machines}.py
│   │   └── profiled/                      # Tier 2: SERVICE-SPECIFIC profiles (extend packs)
│   │       ├── __init__.py
│   │       ├── stripe/                    #   Extends payments pack with Stripe endpoints
│   │       │   ├── __init__.py
│   │       │   └── profile.py
│   │       ├── gmail/                     #   Extends email pack with Gmail features (labels, filters)
│   │       │   ├── __init__.py
│   │       │   └── profile.py
│   │       └── slack/                     #   Extends chat pack with Slack features (reactions, apps)
│   │           ├── __init__.py
│   │           └── profile.py
│   │
│   └── dashboard/
│       ├── __init__.py
│       ├── app.py                          # FastAPI app
│       ├── routes/{__init__,live,replay,reports,api}.py
│       ├── templates/{base,live,replay,report}.html
│       └── static/style.css
│
└── tests/                                  # MANDATORY — every module has tests
    ├── conftest.py                         # MockEventBus, MockLedger, StubStateEngine, factories
    ├── core/
    │   └── test_{types,events,protocols,engine,errors,context}.py
    ├── bus/
    │   └── test_{bus,fanout,persistence,replay,middleware}.py
    ├── ledger/
    │   └── test_{ledger,entries,query,export}.py
    ├── persistence/
    │   └── test_{manager,sqlite,migrations,snapshot}.py
    ├── gateway/
    │   └── test_{gateway,router,monitor,rate_limiter}.py
    ├── llm/
    │   └── test_{provider,router,registry,openai_compat,anthropic_provider,mock,tracker}.py
    ├── config/
    │   └── test_{loader,schema,registry,tunable}.py
    ├── pipeline/
    │   └── test_{dag,step,builder,side_effects}.py
    ├── validation/
    │   └── test_{schema,state_machine,consistency,temporal,amounts}.py
    ├── registry/
    │   └── test_{registry,wiring,composition,health}.py
    ├── engines/
    │   ├── test_{state,policy,permission,budget,responder,animator,reporter,feedback,world_compiler}.py
    │   └── adapter/
    │       ├── test_engine.py                  # Adapter engine tests
    │       ├── test_mcp_server.py              # MCP server: tool manifest, tool call → pipeline, result translation
    │       ├── test_acp_server.py              # ACP server: agent discovery, message routing through channels
    │       ├── test_openai_compat.py           # OpenAI function calling compatibility
    │       ├── test_anthropic_compat.py        # Anthropic tool use compatibility
    │       ├── test_http_rest.py               # REST endpoint simulation
    │       ├── test_tool_manifest.py           # Per-actor tool manifest generation
    │       └── test_observation.py             # World observation delivery to agents
    ├── kernel/
    │   └── test_{registry,categories,primitives}.py
    ├── templates/
    │   └── test_{base,registry,composer,loader,builtin}.py
    ├── runs/
    │   └── test_{manager,snapshot,artifacts,comparison,replay}.py
    ├── packs/
    │   └── test_{email,chat,tickets,payments}_pack.py
    ├── integration/
    │   ├── test_pipeline_integration.py    # Full pipeline with real bus + persistence
    │   ├── test_world_run.py              # End-to-end: compile → run → report
    │   └── test_gateway_to_report.py      # Full flow: gateway → pipeline → ledger → report
    └── fixtures/
        ├── worlds/                         # Test world YAML definitions
        ├── snapshots/                      # Test snapshot data
        └── events/                         # Test event sequences for replay
```

**~130+ skeleton files total, plus repo-root docs (DESIGN_PRINCIPLES.md, OPEN_QUESTIONS.md, .gitignore, terrarium.toml, pyproject.toml).**

---

## Module Responsibilities

### core/ — Shared Abstractions (no logic, just contracts)
- `types.py` — NewType IDs (EntityId, ActorId, etc.), enums (FidelityTier, StepVerdict, etc.), frozen value objects (FidelityMetadata, ActionCost, StateDelta, SideEffect)
- `events.py` — Event type hierarchy. Base `Event` (event_id, event_type, timestamp, caused_by). Subtypes: WorldEvent, PermissionDeniedEvent, PolicyBlockEvent, PolicyHoldEvent, BudgetExhaustedEvent, CapabilityGapEvent, AnimatorEvent, ValidationFailureEvent, etc.
- `protocols.py` — Protocol classes for all 10 engines + PipelineStep + Gateway + Ledger + Persistence
- `engine.py` — BaseEngine ABC: lifecycle (initialize/start/stop), event subscription, health check, dependency declaration via class vars (`engine_name`, `subscriptions`, `dependencies`)
- `errors.py` — Full hierarchy: TerrariumError → ConfigError, EngineError, PipelineError, BusError, ValidationError, StateError, LLMError, GatewayError, LedgerError
- `context.py` — `ActionContext` (mutable, enriched by pipeline steps), `StepResult` (immutable per-step output), `ResponseProposal` (responder output)

### bus/ — Event Bus (the nervous system)
Promoted from single file to full module because it's the core communication backbone.

- **bus.py** — Core `EventBus` class: orchestrates fanout + persistence. All engines publish/subscribe through this.
- **fanout.py** — Topic-based async fanout. Each subscriber gets its own `asyncio.Queue`. Publishing fans out to all matching queues. Supports wildcard (`"*"`) subscriptions.
- **persistence.py** — SQLite append-only ledger for events. Every event persisted **before** fanout (log never behind in-memory state). Schema: `sequence_id, event_id, event_type, timestamp, caused_by, payload, created_at`.
- **replay.py** — Replay engine: read events from SQLite, re-deliver in order. Supports filtering by event_type, time range, sequence range. Used for debugging and run replay.
- **middleware.py** — Pluggable middleware chain on the bus. Use cases: logging every event, metrics collection, event filtering, transformation. Middleware configured in TOML.
- **types.py** — Bus-specific types: `Subscriber` (callback type), `Subscription` (topic + callback + queue), `BusMetrics`.
- **config.py** — `BusConfig` schema: db_path, queue_size, middleware list, persistence_enabled, replay settings.

### ledger/ — Audit Trail for Everything
A structured, append-only log that captures every significant action across the system — not just events, but pipeline step executions, LLM calls, state mutations, gateway requests, validation failures.

- **ledger.py** — Core `Ledger` class: `append(entry)`, async, writes to SQLite. Separate from the event bus — the bus carries events between engines; the ledger records **everything** for observability.
- **entries.py** — Typed ledger entry classes:
  - `PipelineStepEntry` — which step, what context, what verdict, duration_ms
  - `StateMutationEntry` — which entity, what changed, before/after
  - `LLMCallEntry` — provider, model, prompt_tokens, completion_tokens, cost_usd, latency_ms, success
  - `GatewayRequestEntry` — protocol, actor, action, response_code, latency_ms
  - `ValidationEntry` — what was validated, pass/fail, details
  - `EngineLifecycleEntry` — engine, event (init/start/stop/error)
  - `SnapshotEntry` — when snapshot was taken, what was captured
- **query.py** — Query the ledger: filter by entry_type, time range, actor, engine. Aggregate: counts, durations, costs.
- **export.py** — Export ledger to JSON, CSV, or replay-compatible format.
- **config.py** — `LedgerConfig`: db_path, retention_days, entry_types_enabled, flush_interval.

**Key distinction**: The event bus carries events between engines (reactive communication). The ledger records everything for observability and replay (audit trail). They are separate concerns — the bus is the nervous system, the ledger is the flight recorder.

### persistence/ — Unified Persistence Layer
All engines use this module for database operations instead of managing their own connections.

- **manager.py** — `ConnectionManager`: manages SQLite connection pool, provides async context managers, tracks active connections, handles lifecycle (open/close/health).
- **database.py** — `Database` ABC: defines async CRUD interface, transaction support, query builder. All database operations go through this abstraction.
- **sqlite.py** — SQLite implementation of `Database` ABC using aiosqlite. Handles connection pooling (via a semaphore-limited pool since SQLite is single-writer), WAL mode for concurrent reads.
- **migrations.py** — Schema migration runner: discovers migration files, tracks applied versions, applies in order. Each engine registers its schema migrations with the migration runner.
- **snapshot.py** — `SnapshotStore`: save/load complete world state as a SQLite backup or serialized file. Supports incremental snapshots (only changed tables). Used by runs/ module.
- **config.py** — `PersistenceConfig`: base data directory, connection pool size, WAL mode, backup interval, migration auto-run.

### gateway/ — Single Entry/Exit Point
All external requests enter through the gateway. All responses exit through it. This gives a single place for monitoring, authentication, rate limiting, and request/response logging.

- **gateway.py** — Core `Gateway` class: receives raw requests from any protocol (MCP, HTTP, OpenAI, Anthropic), routes them to the pipeline, returns responses. Emits ledger entries for every request/response.
- **router.py** — `RequestRouter`: maps inbound protocol-specific requests to `ActionContext`. Determines which actor is making the request, which service it targets, what action it's performing.
- **monitor.py** — `GatewayMonitor`: observability layer. Tracks requests/sec, latency p50/p95/p99, error rates, per-actor metrics. Exposes metrics via the dashboard. Logs every request/response to the ledger.
- **rate_limiter.py** — Per-actor rate limiting. Configurable in TOML per actor role. Prevents runaway agents from flooding the system.
- **auth.py** — Authentication for hosted/remote mode. Actor identity verification. (Stub in v1, implemented in v2 for remote mode.)
- **middleware.py** — Gateway middleware chain: ordered list of middleware (auth → rate_limit → monitor → route). Configurable in TOML.
- **config.py** — `GatewayConfig`: host, port, middleware list, rate_limit settings, auth settings.

**Flow**: `Agent → Gateway → Router → ActionContext → Pipeline → Response → Gateway → Agent`
The gateway also delivers observations (world state changes) to agents based on their visibility scope.

### llm/ — LLM Provider Module
Full module with per-engine model configuration and generalized provider system. Different engines can use different providers/models (Opus for compilation, Haiku for animator, Ollama for local dev).

- **types.py** — `LLMRequest` (system_prompt, user_content, output_schema, seed, max_tokens, temperature), `LLMResponse` (content, usage, model, latency_ms), `LLMUsage` (prompt_tokens, completion_tokens, cost_usd), `ProviderInfo` (name, type, base_url).
- **provider.py** — `LLMProvider` ABC: `async def generate(request: LLMRequest) -> LLMResponse`. Also: `async def validate_connection() -> bool`.
- **router.py** — `LLMRouter`: routes requests to the correct provider based on engine/use-case. Per-engine config:
  ```toml
  [llm.routing.world_compiler]
  provider = "anthropic"
  model = "claude-opus-4-20250514"

  [llm.routing.animator]
  provider = "ollama"
  model = "llama3"
  ```
- **registry.py** — `ProviderRegistry`: discover, register, lookup providers. Built-in providers auto-registered. Community providers added via config.
- **providers/anthropic.py** — Anthropic native SDK wrapper (Anthropic has its own API format).
- **providers/openai_compat.py** — OpenAI-compatible provider. Works with **any** provider exposing the OpenAI chat completions format: OpenAI, Gemini, Together, Groq, Ollama, vLLM, etc. Configurable via `base_url`. Adding a new provider = adding 3 lines of TOML config, zero code.
- **providers/google.py** — Google Gemini native SDK (optional, for Gemini-specific features beyond OpenAI compat).
- **providers/mock.py** — Mock provider: deterministic responses based on seed. Essential for reproducible tests.
- **tracker.py** — `UsageTracker`: tracks token usage and cost per-actor, per-engine, per-model. Feeds into budget engine. Logs every LLM call to the ledger.
- **config.py** — `LLMConfig`: provider registry configs, routing table, global defaults, retry/timeout settings.

### config/ — Configuration System
Promoted to full module for layered loading, schema validation, runtime tunability, and change notification.

- **loader.py** — `ConfigLoader`: load layered TOML (base → env → local → env vars), deep merge, resolve `*_ref` secure store references. Returns validated `TerrariumConfig`.
- **schema.py** — `TerrariumConfig` root Pydantic model + all section schemas. Every config section is a Pydantic model with defaults and validation.
- **registry.py** — `ConfigRegistry`: runtime access to config values. Thread-safe. Provides `get(section, key)` and `subscribe(section, key, callback)` for change notification.
- **tunable.py** — Runtime-tunable field system. Marks certain fields as tunable. Changes via dashboard/CLI trigger callbacks to notify engines. Tunable fields: creativity_budget, chaos probabilities, budget thresholds, simulation speed.
- **validation.py** — Cross-field validation beyond Pydantic (e.g., pipeline steps must reference registered engines, LLM routing targets must be valid providers).

### pipeline/ — Runtime Pipeline (the 7-step DAG)
Promoted to full module.

- **dag.py** — `PipelineDAG`: takes ordered list of `PipelineStep` implementations. Executes sequentially. Short-circuit on terminal verdicts. Records each step execution in the ledger.
- **step.py** — `PipelineStep` protocol + base step utilities (timing, error wrapping, ledger recording).
- **builder.py** — `build_pipeline_from_config()`: reads step names from TOML, looks up engine implementations in registry, assembles DAG.
- **side_effects.py** — Side effect queue: after commit, side effects are enqueued and re-enter the pipeline as new `ActionContext` instances. Max depth configurable to prevent infinite cascades.
- **config.py** — `PipelineConfig`: step ordering, max_retries, timeout_per_step, side_effect_max_depth.

### validation/ — Validation Framework
Promoted to full module with separate validators per concern.

- **schema.py** — JSON schema validation for LLM-generated outputs. Validates required fields, types, enum values, nested objects.
- **state_machine.py** — State transition validation. Checks current_state → new_state is a valid transition per the entity's state machine definition.
- **consistency.py** — Cross-entity reference validation. Every `ref:entity_type` field must point to an existing entity.
- **temporal.py** — Temporal constraint validation. Events can't reference future timestamps. SLA deadlines must be after ticket creation. Refunds must be after charge creation.
- **amounts.py** — Amount/constraint validation. Refund <= charge. Budget deduction <= remaining. No negative balances.
- **pipeline.py** — `ValidationPipeline`: chains all validators, runs them in order, collects failures, supports retry with error context for LLM-generated content.

### registry/ — Engine Registry / DI
Promoted to full module for wiring, composition root, and health aggregation.

- **registry.py** — `EngineRegistry`: holds all engine instances by `engine_name`. Topological sort via `resolve_initialization_order()`. Detects circular dependencies. Protocol-based lookup.
- **wiring.py** — `wire_engines()`: connects engines to bus, injects protocol-typed dependencies. Each engine receives references to the engines it depends on (via protocol types, never concrete classes).
- **composition.py** — `create_default_registry()`: the **sole composition root**. Only place concrete engine classes are imported and instantiated.
- **health.py** — `HealthAggregator`: runs health_check() on all engines, aggregates results, reports overall system health.

### templates/ — World Templates
Template system with inheritance and composition.

- **base.py** — `BaseTemplate` ABC: defines template interface. Templates produce world definitions (YAML-compatible dicts). Support inheritance (`extends: base_template`).
- **registry.py** — `TemplateRegistry`: discovers templates (built-in + user-provided), validates, provides lookup.
- **composer.py** — `TemplateComposer`: merge multiple templates together. Support additive composition (template A's services + template B's policies).
- **loader.py** — Load template from YAML file. Resolve `extends` references. Validate against template schema.
- **builtin/** — Three built-in templates: Customer Support Team, Incident Response, Open Sandbox. Each has a YAML definition + Python class with customization hooks.

### runs/ — Run Management
Track, snapshot, compare simulation runs.

- **manager.py** — `RunManager`: create runs, track status (initializing → running → completed/failed), store metadata (config used, world definition, start/end time, seed).
- **snapshot.py** — `SnapshotManager`: save world state at any point during a run. Restore from snapshot. Used for fork/replay. Snapshots are stored as SQLite backups + metadata JSON.
- **artifacts.py** — `ArtifactStore`: store run outputs — reports, governance scorecards, event logs, ledger exports, config used. Each run gets a directory under `data/runs/{run_id}/`.
- **comparison.py** — `RunComparator`: compare two or more runs. Diff entity states, event sequences, scores. Produces counterfactual comparison reports.
- **replay.py** — `RunReplayer`: replay a run from its snapshot + event log. Can replay at different speeds, pause at any tick, inject different agents.
- **config.py** — `RunConfig`: data directory, retention policy, snapshot interval, auto-snapshot on completion.

---

## Core Abstractions (Code)

### types.py — Domain Types

```python
from typing import Any, NewType
from pydantic import BaseModel, Field
import enum

# Identity types (NewType for type safety, zero runtime cost)
EntityId = NewType("EntityId", str)
ActorId = NewType("ActorId", str)
ServiceId = NewType("ServiceId", str)
EventId = NewType("EventId", str)
WorldId = NewType("WorldId", str)
SnapshotId = NewType("SnapshotId", str)
PolicyId = NewType("PolicyId", str)
ToolName = NewType("ToolName", str)
RunId = NewType("RunId", str)

# Enums
class FidelityTier(enum.IntEnum):
    VERIFIED = 1; PROFILED = 2; INFERRED = 3

class EnforcementMode(enum.StrEnum):
    HOLD = "hold"; BLOCK = "block"; ESCALATE = "escalate"; LOG = "log"

class StepVerdict(enum.StrEnum):
    ALLOW = "allow"; DENY = "deny"; HOLD = "hold"
    ESCALATE = "escalate"; ERROR = "error"

class ActorType(enum.StrEnum):
    AGENT = "agent"; HUMAN = "human"; SYSTEM = "system"

class WorldMode(enum.StrEnum):
    GOVERNED = "governed"; UNGOVERNED = "ungoverned"

# Frozen value objects
class FidelityMetadata(BaseModel, frozen=True):
    tier: FidelityTier
    source: str
    profile_version: str | None = None
    deterministic: bool = False
    replay_stable: bool = False

class ActionCost(BaseModel, frozen=True):
    api_calls: int = 0
    llm_spend_usd: float = 0.0
    world_actions: int = 0

class StateDelta(BaseModel, frozen=True):
    entity_type: str
    entity_id: EntityId
    operation: str  # "create" | "update" | "delete"
    fields: dict[str, Any]
    previous_fields: dict[str, Any] | None = None

class SideEffect(BaseModel, frozen=True):
    effect_type: str
    target_service: ServiceId | None = None
    target_entity: EntityId | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
```

### engine.py — BaseEngine ABC

```python
class BaseEngine(abc.ABC):
    engine_name: ClassVar[str]          # unique identifier
    subscriptions: ClassVar[list[str]]  # event types to listen to
    dependencies: ClassVar[list[str]]   # engine names this depends on

    async def initialize(self, config, bus) -> None  # lifecycle: setup
    async def start(self) -> None                    # lifecycle: subscribe to bus
    async def stop(self) -> None                     # lifecycle: cleanup
    async def health_check(self) -> dict             # health status

    # Subclass hooks:
    async def _on_initialize(config) -> None
    async def _on_start() -> None
    async def _on_stop() -> None
    @abstractmethod
    async def _handle_event(event: Event) -> None    # handle bus events

    async def publish(event: Event) -> None          # publish to bus
```

### context.py — ActionContext & StepResult

```python
class ActionContext(BaseModel):  # MUTABLE — enriched by pipeline steps
    request_id: str
    actor_id: ActorId
    service_id: ServiceId
    action: ToolName
    input_data: dict[str, Any]
    target_entity: EntityId | None
    world_time: datetime
    tick: int
    run_id: RunId | None = None
    # Enriched by steps:
    permission_result: StepResult | None = None
    policy_result: StepResult | None = None
    budget_result: StepResult | None = None
    response_proposal: ResponseProposal | None = None
    # Pipeline control:
    short_circuited: bool = False
    short_circuit_step: str | None = None

class StepResult(BaseModel, frozen=True):  # IMMUTABLE
    step_name: str
    verdict: StepVerdict
    message: str = ""
    events: list[Event] = []
    duration_ms: float = 0.0
    @property
    def is_terminal(self) -> bool:
        return self.verdict in (StepVerdict.DENY, StepVerdict.HOLD,
                                StepVerdict.ESCALATE, StepVerdict.ERROR)

class ResponseProposal(BaseModel, frozen=True):
    response_body: dict[str, Any]
    proposed_state_deltas: list[StateDelta] = []
    proposed_side_effects: list[SideEffect] = []
    fidelity: FidelityMetadata | None = None
```

---

## Engine Interface Contracts

| Engine | Protocol | PipelineStep | Publishes | Subscribes | Dependencies |
|--------|----------|-------------|-----------|------------|--------------|
| **State** | StateEngineProtocol | commit | `world`, `engine_lifecycle` | `world`, `simulation` | None (root) |
| **Permission** | PermissionEngineProtocol | permission | `permission_denied` | — | State |
| **Policy** | PolicyEngineProtocol | policy | `policy_block/hold/escalate/flag` | `approval` | State |
| **Budget** | BudgetEngineProtocol | budget | `budget_deduction/warning/exhausted` | `world` | State |
| **Adapter** | AdapterProtocol | capability | `capability_gap` | `world` | State, Permission |
| **Responder** | ResponderProtocol | responder | — (commit publishes) | — | State, Kernel |
| **Animator** | AnimatorProtocol | — | `animator` | `simulation`, `world` | State, Pipeline |
| **Compiler** | WorldCompilerProtocol | — | `simulation.*` | — | State, Kernel |
| **Reporter** | ReporterProtocol | — | `simulation.report_generated` | `simulation` | State |
| **Feedback** | FeedbackProtocol | — | `annotation`, `tier_promotion` | `capability_gap`, `world` | State |

---

## MCP / ACP Protocol Architecture

### How Agents Connect to the World

Terrarium is a **protocol server**. Agents connect to it using standard protocols. The adapter engine runs protocol servers that translate between external protocols and the internal pipeline.

```
┌─────────────────────────────────────────────────────┐
│                  AGENT ADAPTER ENGINE                │
│                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │
│  │ MCP      │  │ ACP      │  │ OpenAI/Anthropic/ │ │
│  │ Server   │  │ Server   │  │ HTTP Compat       │ │
│  │ (mcp sdk)│  │ (acp sdk)│  │ (FastAPI)         │ │
│  └────┬─────┘  └────┬─────┘  └────────┬─────────┘ │
│       │              │                 │            │
│       └──────────────┼─────────────────┘            │
│                      │                              │
│              ProtocolAdapter ABC                     │
│              translate_inbound()                     │
│              translate_outbound()                    │
│                      │                              │
│                      ▼                              │
│              ActionContext                           │
│              → Gateway → Pipeline                   │
└─────────────────────────────────────────────────────┘
```

### MCP Server (`adapter/protocols/mcp_server.py`)

**What it does**: Exposes every world service as MCP tools. When an agent connects via MCP:
1. Agent receives a tool manifest (list of available tools based on their actor permissions)
2. Agent calls a tool (e.g., `stripe_refunds_create`)
3. MCP server translates the tool call into an `ActionContext`
4. Context goes through gateway → pipeline → response
5. Response is translated back to MCP tool result format
6. World state changes are delivered as MCP notifications/resources

**SDK dependency**: `mcp` Python SDK (server mode). We run the MCP server, agents are MCP clients.

**Per-actor tool manifest**: The tool list is filtered by the Permission Engine. Agent-alpha sees different tools than supervisor-maya based on their permissions.

### ACP Server (`adapter/protocols/acp_server.py`)

**What it does**: Handles agent-to-agent communication via the Agent Communication Protocol.
1. Agent A sends a message to Agent B
2. ACP server routes the message through world communication channels (chat, email)
3. The message goes through the pipeline (permission check, visibility rules apply)
4. Agent B receives the message through the world's communication service
5. Agent discovery happens through the world's actor registry

**Key constraint**: Agents don't communicate directly. All agent-to-agent communication flows through world channels and is subject to visibility rules. ACP is the transport; the world is the medium.

### OpenAI / Anthropic Compatibility (`adapter/protocols/openai_compat.py`, `anthropic_compat.py`)

Agents built with OpenAI function calling or Anthropic tool use can connect without modification. The compatibility layer translates:
- OpenAI function definitions ↔ world service tools
- Anthropic tool use blocks ↔ world service tools
- Function call results / tool results ↔ pipeline responses

### HTTP REST (`adapter/protocols/http_rest.py`)

Raw REST endpoints that mimic real service APIs. Example: `POST /v1/charges` looks like a Stripe API call but routes through the pipeline. For agents that interact via HTTP rather than MCP.

### Dependencies (pyproject.toml)

```toml
[project]
dependencies = [
    "pydantic>=2.0",
    "aiosqlite>=0.19",
    "typer>=0.9",
    "fastapi>=0.100",
    "uvicorn>=0.23",
    "httpx>=0.24",
    "mcp>=1.0",                  # MCP Python SDK — server mode
    # "acp>=...",                 # ACP SDK — when available, stub for now
    "anthropic>=0.30",           # Anthropic SDK for LLM provider
    "openai>=1.0",               # OpenAI SDK for LLM provider
    "tomli>=2.0; python_version<'3.11'",  # TOML parsing (stdlib in 3.11+)
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.0",
    "ruff>=0.1",
    "mypy>=1.5",
]
```

---

## Multi-Agent Isolation

Multiple agents share the **same world state** but see different slices through visibility scoping.

**Concurrency model:**
- Each agent's actions go through the pipeline independently and concurrently
- Reads are concurrent (SQLite WAL mode)
- State Engine commit is serialized (single-writer) — intentional for consistency
- Conflict resolution: first-to-commit wins; second agent gets "already assigned" / stale state
- How agents handle conflicts is observable behavior

**Isolation guarantees:**
- Permission Engine filters every query result to the actor's visibility scope
- Agent-alpha's `list_tickets()` returns only tickets they can see — others don't exist from their perspective
- Agents discover each other through world channels (chat, email), not direct connections
- All inter-agent messages go through the pipeline — permission/policy checks apply
- Information asymmetry is enforced: agents can't see each other's budgets or private channels

---

## Real-Time Visualization & Observability

The architecture natively supports real-time visualization. **No special additions needed** — the event bus + ledger + state snapshots capture everything.

**How visualization layers connect:**

```
Event Bus (all events)
    │
    ├── SSE endpoint (GET /api/events/stream)       ← Dashboard, web UX
    ├── WebSocket endpoint (ws://host/events)        ← Low-latency 3D visualization
    └── REST polling (GET /api/world/state?tick=N)   ← Point-in-time queries
```

**What can be shown at any given second:**
- Per-agent: current action, pipeline step, pending holds, budget
- World state: all entities, states, relationships
- Live event stream: every event with timestamp, actor, action, outcome
- Causal graph: interactive trace of causes and effects

**Subscription modes for visualization:**
- `"*"` wildcard — see everything (god mode / dashboard)
- Per-agent filter — track what agent-alpha is doing
- Per-service filter — see all payment activity
- Per-entity filter — track a specific ticket lifecycle

**Tick-based snapshots** enable timeline scrubbing and replay at any speed.

A 3D/UX layer is just another bus subscriber that renders events spatially. The architecture doesn't need to change.

---

## Dynamic Policy System

Policies are **not hardcoded**. They are defined in YAML, created at runtime, and contributed by community as templates.

### Policy Condition Language (not Turing-complete, by design)

```yaml
# Simple condition
condition: "input.amount > 5000"

# Compound conditions
condition: "input.amount > 5000 AND actor.role != 'supervisor'"
condition: "world.time.hour >= 17 OR world.time.hour < 9"
condition: "target.customer.sentiment == 'frustrated' AND target.sla_remaining <= 0"
```

**Supported operators:**
- Comparisons: `==`, `!=`, `>`, `<`, `>=`, `<=`
- Logic: `AND`, `OR`, `NOT`
- Field access: `input.*`, `actor.*`, `target.*`, `world.*`
- String: `contains()`, `starts_with()`
- Lists: `in`, `not_in`
- Math: `+`, `-`, `*`, `/`
- Time: `duration_since()`, `within()`

### Three Levels of Policy Extensibility

1. **YAML conditions** — no code, covers ~95% of cases
2. **Community policy templates** — parameterized YAML:
   ```yaml
   policy_template:
     id: financial-guardrails
     parameters:
       threshold: 5000
       approver_role: "supervisor"
     policies:
       - trigger:
           action: "*_refund_*"
           condition: "input.amount > {threshold}"
         enforcement: hold
         hold_config:
           approver_role: "{approver_role}"
   ```
3. **Registered policy functions** — Python functions for complex logic:
   ```yaml
   condition: "risk_score(input, actor) > 0.8"
   ```
   Where `risk_score` is a Python function registered with the PolicyEngine.

### Runtime Policy Creation (during simulation)

Policies can be added/modified via API during a running simulation:
```
POST /api/policies → PolicyEngine picks up immediately → enforced on next action
```

### Policy Engine modules (updated)

```
engines/policy/
  ├── engine.py           # PolicyEngine (also PipelineStep)
  ├── evaluator.py        # Condition parser + evaluator (the expression language)
  ├── enforcement.py      # Hold/block/escalate/log dispatch
  ├── templates.py        # Policy template loader + instantiation from parameterized YAML
  ├── functions.py        # Registered policy function registry (Python escape hatch)
  ├── loader.py           # Load policies from YAML (world definition + standalone files)
  ├── runtime.py          # Runtime policy CRUD (add/modify/delete during simulation via API)
  ├── config.py
  └── data/               # Policy YAML data
      ├── builtin/        # Built-in templates (ship with Terrarium)
      │   ├── financial_guardrails.yaml    # Refund approval chains, spend limits
      │   ├── sla_enforcement.yaml         # SLA breach → escalation rules
      │   ├── communication_protocol.yaml  # Expected messages on state changes
      │   └── authority_boundaries.yaml    # Role-based action constraints
      ├── community/      # Community-contributed policy templates (git submodule / registry)
      └── schema/         # YAML schemas for policies and templates
          ├── policy_schema.yaml           # Validates policy YAML definitions
          └── template_schema.yaml         # Validates parameterized templates
```

**Where policies come from:**
1. **World YAML** — inline in the world definition (`policies:` section)
2. **Built-in templates** — `data/builtin/*.yaml` — activated by referencing template ID in world YAML
3. **Community templates** — `data/community/*.yaml` — contributed, reviewed, versioned
4. **Runtime API** — `POST /api/policies` — created during simulation
5. **Registered functions** — Python functions in `functions.py` — for complex conditions beyond the expression language

---

## LLM Provider Generalization

Most LLM providers support the OpenAI-compatible API format. The architecture leverages this:

```
LLMProvider ABC
    │
    ├── AnthropicProvider          — native SDK (Anthropic's own API format)
    ├── OpenAICompatibleProvider   — works with ANY OpenAI-format provider:
    │   │                            configurable base_url, zero code for new providers
    │   ├── OpenAI      → base_url: api.openai.com/v1
    │   ├── Gemini      → base_url: generativelanguage.googleapis.com/v1beta/openai
    │   ├── Together    → base_url: api.together.xyz/v1
    │   ├── Groq        → base_url: api.groq.com/openai/v1
    │   ├── Ollama      → base_url: localhost:11434/v1
    │   ├── vLLM        → base_url: my-server:8000/v1
    │   └── Any new     → just add base_url in TOML config
    ├── GoogleNativeProvider       — optional, for Gemini-specific features
    └── MockProvider               — deterministic responses for testing
```

**Adding a new provider (zero code):**
```toml
[llm.providers.my_provider]
type = "openai_compatible"
base_url = "https://my-provider-api.com/v1"
api_key_ref = "MY_PROVIDER_KEY"
```

**Per-engine model routing:**
```toml
[llm.routing.world_compiler]
provider = "anthropic"
model = "claude-opus-4-20250514"      # Best model for complex schema inference

[llm.routing.animator]
provider = "ollama"
model = "llama3"                       # Local open-source model, fast + free
temperature = 0.9
```

---

## Pack Hierarchy (Category → Pack → Profile)

Tier 1 packs are **category-level** (not service-level). Tier 2 profiles add service-specific features on top.

```
Semantic Category: communication/email
    │
    ├── Tier 1: "email" Verified Pack (category-level)
    │   Universal email primitives: inbox, send, receive, thread, read/unread
    │   Works for ANY email service (Gmail, Outlook, Yahoo, ProtonMail)
    │
    ├── Tier 2: Service-Specific Profiles (extend the pack)
    │   ├── "gmail" profile — labels, filters, Google-specific threading
    │   ├── "outlook" profile — categories, focused inbox, Exchange rules
    │   └── Community-contributed profiles for other services
    │
    └── Tier 3: No profile exists
        User says "my world has ProtonMail"
        → Kernel maps to communication/email → inherits email pack
        → LLM infers ProtonMail-specific surface differences

Semantic Category: money/transactions
    │
    ├── Tier 1: "payments" Verified Pack
    │   charge, refund, dispute, authorization, settlement, balance
    │
    ├── Tier 2: "stripe" profile (Stripe-specific: payment intents, customer portal)
    │           "paypal" profile (PayPal-specific: disputes API, seller protection)
    │
    └── Tier 3: user says "Braintree" → inherits payments pack → LLM infers
```

---

## Request Flow (End-to-End)

```
Agent A (MCP client)     Agent B (ACP)     Agent C (OpenAI func calling)
    │                       │                    │
    ▼                       ▼                    ▼
┌──────────┐          ┌──────────┐         ┌───────────┐
│ MCP      │          │ ACP      │         │ OpenAI    │
│ Server   │          │ Server   │         │ Compat    │
│ (mcp sdk)│          │ (acp sdk)│         │ (FastAPI) │
└─────┬────┘          └─────┬────┘         └─────┬─────┘
      └──────────────────────┼───────────────────┘
                             │
                    ProtocolAdapter.translate_inbound()
                             │
                             ▼
┌─────────────────────────────────┐
│  GATEWAY                        │
│  auth → rate_limit → monitor    │
│  → router → ActionContext       │
│  → ledger(GatewayRequestEntry)  │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  PIPELINE DAG                    │
│                                  │
│  1. Permission  → ledger step    │
│  2. Policy      → ledger step    │
│  3. Budget      → ledger step    │
│  4. Capability  → ledger step    │
│  5. Responder   → ledger step    │
│  6. Validation  → ledger step    │
│  7. Commit      → ledger step    │
│                                  │
│  Each step: execute → record     │
│  Short-circuit: stop + events    │
│  Side effects: re-enter pipeline │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  STATE ENGINE                    │
│  commit → event_log → causal    │
│  → bus.publish(WorldEvent)       │
│  → ledger(StateMutationEntry)    │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  EVENT BUS                       │
│  fanout to subscribers           │
│  → persistence (SQLite)          │
│  → middleware (logging, metrics)  │
└──────────────┬──────────────────┘
               │
     ┌─────────┼─────────┐
     ▼         ▼         ▼
  Budget    Animator   Adapter
  (deduct)  (react)   (deliver observation to agent)
               │
               ▼
┌─────────────────────────────────┐
│  GATEWAY (outbound)              │
│  response → monitor → ledger     │
│  → Agent                         │
└─────────────────────────────────┘
```

---

## LLM Routing Configuration

```toml
[llm.defaults]
provider = "anthropic"
model = "claude-sonnet-4-20250514"
max_tokens = 4096
temperature = 0.7
timeout_seconds = 30
max_retries = 2

# Provider registry — zero code to add new providers
[llm.providers.anthropic]
type = "anthropic"                     # Native Anthropic SDK
api_key_ref = "ANTHROPIC_API_KEY"

[llm.providers.openai]
type = "openai_compatible"             # OpenAI native
base_url = "https://api.openai.com/v1"
api_key_ref = "OPENAI_API_KEY"

[llm.providers.gemini]
type = "openai_compatible"             # Gemini supports OpenAI format
base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
api_key_ref = "GOOGLE_API_KEY"

[llm.providers.together]
type = "openai_compatible"             # Together AI
base_url = "https://api.together.xyz/v1"
api_key_ref = "TOGETHER_API_KEY"

[llm.providers.ollama]
type = "openai_compatible"             # Local Ollama (no API key needed)
base_url = "http://localhost:11434/v1"

[llm.providers.custom_vllm]
type = "openai_compatible"             # Self-hosted vLLM
base_url = "http://my-server:8000/v1"

# Per-engine routing (overrides defaults)
[llm.routing.world_compiler]
provider = "anthropic"
model = "claude-opus-4-20250514"       # Best model for complex schema inference
max_tokens = 8192

[llm.routing.responder_tier2]
provider = "anthropic"
model = "claude-sonnet-4-20250514"     # Good balance for constrained generation

[llm.routing.responder_tier3]
provider = "openai"
model = "gpt-4o"                       # Can use different provider per tier

[llm.routing.animator]
provider = "ollama"
model = "llama3"                       # Local open-source model, fast + free
temperature = 0.9

[llm.routing.data_generator]
provider = "anthropic"
model = "claude-sonnet-4-20250514"
max_tokens = 8192
```

---

## Implementation Sequence

### Phase 0 — Repo Root Setup
0. `pyproject.toml`, `.gitignore`, `terrarium.toml`, `terrarium.development.toml`
0. `DESIGN_PRINCIPLES.md` — the law of the codebase
0. `OPEN_QUESTIONS.md` — unresolved design questions with phase dependencies
0. `terrarium/__init__.py`, `terrarium/__main__.py`

### Phase 1 — Core Foundations + Tests
1. `core/types.py` + `core/errors.py` + tests
2. `core/events.py` + tests
3. `core/context.py` + tests
4. `core/protocols.py` + tests
5. `core/engine.py` + tests

### Phase 2 — Infrastructure Modules + Tests
6. `persistence/` — manager, database ABC, SQLite impl, migrations, snapshot + tests
7. `bus/` — types, fanout, persistence, replay, middleware, bus + tests
8. `ledger/` — entries, ledger, query, export + tests
9. `config/` — loader, schema, registry, tunable, validation + tests
10. `llm/` — types, provider ABC, mock provider, router, tracker + tests
11. `validation/` — schema, state_machine, consistency, temporal, amounts, pipeline + tests
12. `registry/` — registry, wiring, composition, health + tests
13. `pipeline/` — step, dag, builder, side_effects + tests
14. `gateway/` — types, router, monitor, rate_limiter, middleware, gateway + tests

### Phase 3 — State Engine (root dependency) + Tests
15. `engines/state/` — store, event_log, causal_graph, engine + tests

### Phase 4 — Pipeline Engines + Tests
16. `engines/permission/` + tests
17. `engines/policy/` + tests
18. `engines/budget/` + tests
19. `engines/adapter/` + tests

### Phase 5 — Responder + Kernel + Packs + Tests
20. `kernel/` — registry, categories, primitives, data files + tests
21. `packs/base.py` — ServicePack + ServiceProfile ABCs + tests
22. `engines/responder/` — tier1, tier2, tier3, engine + tests
23. `packs/verified/email/` — reference Tier 1 pack + tests

### Phase 6 — Remaining Engines + Tests
24. `engines/animator/` + tests
25. `engines/world_compiler/` + tests
26. `engines/reporter/` + tests
27. `engines/feedback/` + tests

### Phase 7 — Templates + Runs + Tests
28. `templates/` — base, registry, composer, loader, builtins + tests
29. `runs/` — manager, snapshot, artifacts, comparison, replay + tests

### Phase 8 — CLI + Dashboard + Integration Tests
30. `cli.py` — all CLI commands
31. `dashboard/` — FastAPI app, routes, templates
32. Integration tests: pipeline, world run, gateway-to-report

### Phase 9 — Remaining Packs
33. Remaining Tier 1 packs (chat, tickets, payments, repos, calendar) + tests

---

## Testing Strategy

### Mandatory Rule
**Every module ships with tests. No untested code enters the codebase.** Tests must be written alongside the skeleton/implementation — not after.

### Test Types

| Type | Scope | Tools | Location |
|------|-------|-------|----------|
| **Unit** | Single module in isolation | MockEventBus, MockLedger, StubStateEngine, MockLLMProvider | `tests/{module}/` |
| **Integration** | Multiple modules with real persistence | Real bus + SQLite (`:memory:`), real engines | `tests/integration/` |
| **Pipeline** | Full 7-step DAG | Stub engines with configurable StepResult | `tests/pipeline/` |
| **E2E** | Gateway → Pipeline → Report | Everything real with in-memory SQLite | `tests/integration/test_world_run.py` |
| **Pack** | Tier 1 pack state machines | Direct pack handler calls | `tests/packs/` |

### Key Test Fixtures (`tests/conftest.py`)
- `MockEventBus` — captures published events in a list, no SQLite
- `MockLedger` — captures ledger entries in a list
- `StubStateEngine` — returns canned entity data
- `MockLLMProvider` — returns deterministic responses based on seed
- `make_action_context()` — factory with sensible defaults
- `make_world_event()` — factory for WorldEvent
- `temp_sqlite_db()` — creates in-memory SQLite for integration tests
- `test_config()` — minimal valid TerrariumConfig

### Coverage Enforcement
- Minimum coverage target: 80% per module
- CI blocks PRs that decrease coverage
- Critical paths (pipeline, bus, state engine) target 95%

---

## Verification Plan

1. **Core**: `pytest tests/core/` — types serialize, events route, protocols satisfied
2. **Infrastructure**: `pytest tests/{bus,ledger,persistence,config,llm,validation,pipeline,gateway,registry}/` — each module works independently
3. **Engines**: `pytest tests/engines/` — each engine satisfies protocol, handles events
4. **Integration**: `pytest tests/integration/` — full pipeline with real bus, world run produces valid report, gateway-to-report flow works
5. **Packs**: `pytest tests/packs/` — state machines correct, deterministic behavior
6. **Smoke test**: `python -m terrarium create "Support team with email and chat, 5 customers" && python -m terrarium plan --show`
7. **Ledger verification**: after any run, `python -m terrarium ledger --run latest` shows complete audit trail of every step
