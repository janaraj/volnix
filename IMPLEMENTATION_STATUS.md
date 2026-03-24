# Terrarium — Implementation Status

> Single source of truth for what's real, what's stub, and what's next.
> Updated after every implementation session.

## Current Focus

**Phase:** D — World Building
**Item:** D4b compiler (generation) — IN PROGRESS
**Status:** World compiler generation phase: WorldGenerationContext framework, live Gemini LLM integration (gemini-3-flash-preview), batched entity/personality/seed generation, compiler presets (ideal/messy/hostile). 1033 tests (24 skipped), 0 failures. Live E2E test passing with real Gemini output.

---

## Architecture Gaps — Clearly Documented

### GAP: G3 Animator NOT in D4b (Runtime behavior modes)

**What the spec says:** Behavior mode (static/dynamic/reactive) controls the Animator at RUNTIME, not at compilation.

**Two-phase application (from spec):**
1. **Compilation (D4b — DONE):** Reality dimensions shape entity generation. The LLM generates entities with baked-in character, actors with baked-in personalities, services with baked-in quirks. This is the SAME regardless of behavior mode.
2. **Runtime (G3 — NOT BUILT):** The behavior mode determines whether the Animator generates events during simulation:
   - **Static:** Animator OFF. World frozen after compilation. Only agent actions change state.
   - **Dynamic:** Animator ON. Generates organic events contextually (customer follow-ups, service degradation, situation evolution).
   - **Reactive:** Animator generates events ONLY in response to agent actions or inaction.

**Current state:** Behavior mode is stored in WorldPlan and passed to entity generation as a hint (LLM uses it for entity state flavor — dynamic entities have "in-flight" states, static have "settled" states). But there is NO runtime Animator. The world is effectively always "static" at runtime regardless of mode setting.

**G3 scope: ✅ COMPLETE**
- `terrarium/engines/animator/engine.py` — WorldAnimatorEngine with tick(), configure(), behavior modes
- `terrarium/engines/animator/context.py` — AnimatorContext reusing WorldGenerationContext pattern
- `terrarium/engines/animator/generator.py` — OrganicGenerator with ANIMATOR_EVENT PromptTemplate
- `terrarium/scheduling/scheduler.py` — Shared WorldScheduler (one-shot, recurring, trigger)
- Level 2 per-attribute numbers drive probabilistic events (reliability.failures=20 → 20% per tick)
- Creativity budget enforced (creativity_budget_per_tick)
- All events through 7-step pipeline via app.handle_action()
- 56 tests, all passing

### GAP: G4 Promotion Pipeline NOT in D4b

**What the spec says:** After a run, captured service surfaces can be compiled into verified packs:
```
terrarium capture --service salesforce --run last
terrarium compile-pack --service salesforce
terrarium promote --service salesforce --submit-pr
```

**Current state:** `ServiceBootstrapper.capture_surface()` and `compile_to_pack()` raise `NotImplementedError("Phase G4")`. This is intentional — promotion requires runtime capture data that doesn't exist until G3 (Animator) runs simulations.

### Infer Path Status (moved from G2 to D4 — COMPLETE)

The service inference chain for unknown services is **fully implemented and tested**:

| Step | Component | Status | Confidence |
|------|-----------|--------|-----------|
| 1. Verified Pack | PackRegistry.get_pack() | ✅ Real | 1.0 |
| 2. Curated Profile | PackRegistry.get_profiles_for_pack() | ✅ Real | 0.8 |
| 3. Context Hub | ContextHubProvider (chub CLI subprocess) | ✅ Real (70+ known services) | 0.7 |
| 4. OpenAPI Spec | OpenAPIProvider (full 3.x parser with $ref) | ✅ Real | 0.5 |
| 5. LLM Callback | ServiceResolver LLM hook | ✅ Real (awaitable) | 0.3 |
| 6. Kernel Classification | SemanticRegistry (33 services, 9 categories) | ✅ Real | 0.1 |
| 7. Promotion Gate | capture_surface → compile_to_pack | ❌ Phase G4 | — |

---

## Module Status

### Legend
- ✅ `done` — Fully implemented, tests passing
- 🔧 `in-progress` — Being implemented in current phase item
- 📦 `partial` — Some functionality implemented, rest is stub
- 📋 `stub` — Skeleton only (signatures, no logic)
- 🔲 `todo` — Not yet created (future work)

### Core & Infrastructure

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **Core types** | `terrarium/core/types.py` | ✅ done | A1 | NewTypes, enums, value objects |
| **Core events** | `terrarium/core/events.py` | ✅ done | A1 | Event hierarchy |
| **Core context** | `terrarium/core/context.py` | ✅ done | A1 | ActionContext, StepResult, ResponseProposal |
| **Core protocols** | `terrarium/core/protocols.py` | ✅ done | A1 | 14 runtime_checkable protocols |
| **Core engine** | `terrarium/core/engine.py` | ✅ done | B4 | BaseEngine lifecycle (12 methods) |
| **Core errors** | `terrarium/core/errors.py` | ✅ done | B4 | Error hierarchy (4 constructors) |
| **Persistence — manager** | `terrarium/persistence/manager.py` | ✅ done | A1 | Connection pool — 4 methods |
| **Persistence — database** | `terrarium/persistence/database.py` | ✅ done | A1 | Database ABC — 7 abstract methods |
| **Persistence — sqlite** | `terrarium/persistence/sqlite.py` | ✅ done | A1 | SQLite impl — 10 methods, WAL mode |
| **Persistence — migrations** | `terrarium/persistence/migrations.py` | ✅ done | A1 | Schema migrations — 6 methods |
| **Persistence — snapshot** | `terrarium/persistence/snapshot.py` | ✅ done | A1 | Snapshot storage — 5 methods |
| **Config — loader** | `terrarium/config/loader.py` | ✅ done | A2 | Layered TOML: base→env→local→envvars→refs |
| **Config — schema** | `terrarium/config/schema.py` | ✅ done | A2 | Imports from 20 subsystem configs, assembles TerrariumConfig |
| **Config — registry** | `terrarium/config/registry.py` | ✅ done | A2 | Typed get/set, subscriptions, tunable updates |
| **Config — tunable** | `terrarium/config/tunable.py` | ✅ done | A2 | Field registry with validators + listeners |
| **Config — validation** | `terrarium/config/validation.py` | ✅ done | A2 | Pipeline steps, LLM routing, cross-references |
| **Bus — bus** | `terrarium/bus/bus.py` | ✅ done | A3 | EventBus orchestrator — middleware→persist→fanout |
| **Bus — fanout** | `terrarium/bus/fanout.py` | ✅ done | A3 | Topic routing + wildcard + back-pressure |
| **Bus — persistence** | `terrarium/bus/persistence.py` | ✅ done | A3 | Event log via AppendOnlyLog (DI'd Database) |
| **Bus — replay** | `terrarium/bus/replay.py` | ✅ done | A3 | Range, timerange, callback replay |
| **Bus — middleware** | `terrarium/bus/middleware.py` | ✅ done | A3 | Chain + Logging + Metrics middleware |
| **Ledger — ledger** | `terrarium/ledger/ledger.py` | ✅ done | A4 | Core ledger — append, query (SQL-filtered), get_count |
| **Ledger — entries** | `terrarium/ledger/entries.py` | ✅ done | A4 | 7 entry types + registry + typed deserialization |
| **Ledger — query** | `terrarium/ledger/query.py` | ✅ done | A4 | LedgerQuery, LedgerQueryBuilder (fluent) |
| **Ledger — export** | `terrarium/ledger/export.py` | ✅ done | A4 | JSON, CSV, JSONL export |

### Pipeline & Validation

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **Validation — schema** | `terrarium/validation/schema.py` | ✅ done | B1 | ValidationResult + SchemaValidator (type/enum/min/max) |
| **Validation — state_machine** | `terrarium/validation/state_machine.py` | ✅ done | B1 | State transition + valid transitions lookup |
| **Validation — consistency** | `terrarium/validation/consistency.py` | ✅ done | B1 | Async ref validation via entity schemas + StateEngineProtocol |
| **Validation — temporal** | `terrarium/validation/temporal.py` | ✅ done | B1 | Timestamp + ordering validation |
| **Validation — amounts** | `terrarium/validation/amounts.py` | ✅ done | B1 | Refund/budget/non-negative checks |
| **Validation — pipeline** | `terrarium/validation/pipeline.py` | ✅ done | B1 | Orchestrator with LLM retry, config-driven max_retries |
| **Pipeline — dag** | `terrarium/pipeline/dag.py` | ✅ done | B2 | Sequential execution, short-circuit, ledger + bus integration |
| **Pipeline — step** | `terrarium/pipeline/step.py` | ✅ done | B2 | BasePipelineStep ABC with timing helper |
| **Pipeline — builder** | `terrarium/pipeline/builder.py` | ✅ done | B2 | Config → step registry → PipelineDAG |
| **Pipeline — side_effects** | `terrarium/pipeline/side_effects.py` | ✅ done | B2 | Queue + depth-bounded re-entry |
| **Registry — registry** | `terrarium/registry/registry.py` | ✅ done | B4 | Engine DI container (8 methods, Kahn's topo sort) |
| **Registry — wiring** | `terrarium/registry/wiring.py` | ✅ done | B4 | wire_engines + shutdown_engines + inject_dependencies |
| **Registry — composition** | `terrarium/registry/composition.py` | ✅ done | B4 | Composition root (10 engines) |
| **Registry — health** | `terrarium/registry/health.py` | ✅ done | B4 | Health aggregator (4 methods) |

### LLM

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **LLM — types** | `terrarium/llm/types.py` | ✅ done | B3 | LLMRequest, LLMResponse, LLMUsage, ProviderType |
| **LLM — secrets** | `terrarium/llm/secrets.py` | ✅ done | B3 | SecretResolver: EnvVar, File, Chain (NEW) |
| **LLM — provider** | `terrarium/llm/provider.py` | ✅ done | B3 | LLMProvider ABC |
| **LLM — router** | `terrarium/llm/router.py` | ✅ done | B3 | Config-driven routing by engine/use-case |
| **LLM — registry** | `terrarium/llm/registry.py` | ✅ done | B3 | Factory: 6 provider types (api/acp/cli/mock) |
| **LLM — tracker** | `terrarium/llm/tracker.py` | ✅ done | B3 | Ledger + in-memory aggregates by actor/engine |
| **LLM — mock** | `terrarium/llm/providers/mock.py` | ✅ done | B3 | Deterministic seed-based responses |
| **LLM — anthropic** | `terrarium/llm/providers/anthropic.py` | ✅ done | B3 | Real AsyncAnthropic SDK + cost estimation |
| **LLM — openai compat** | `terrarium/llm/providers/openai_compat.py` | ✅ done | B3 | Real AsyncOpenAI SDK + configurable base_url |
| **LLM — google** | `terrarium/llm/providers/google.py` | ✅ done | B3 | Real google.genai SDK |
| **LLM — acp client** | `terrarium/llm/providers/acp_client.py` | ✅ done | B3 | ACP stdio JSON-RPC (NEW) |
| **LLM — cli subprocess** | `terrarium/llm/providers/cli_subprocess.py` | ✅ done | B3 | Async subprocess CLI fallback (NEW) |
| **LLM — conversation** | `terrarium/llm/conversation.py` | ✅ done | B3 | Provider-aware multi-turn context (NEW) |

### Engines

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **State — migrations** | `terrarium/engines/state/migrations.py` | ✅ done | C1 | 12 versioned migrations (entities, events, causal_edges + indexes) |
| **State — store** | `terrarium/engines/state/store.py` | ✅ done | C1 | EntityStore CRUD (6 methods, retractable update/delete) |
| **State — event_log** | `terrarium/engines/state/event_log.py` | ✅ done | C1 | Append-only EventLog (5 methods, indexed columns + JSON payload) |
| **State — causal_graph** | `terrarium/engines/state/causal_graph.py` | ✅ done | C1 | CausalGraph DAG (6 methods, BFS traversal) |
| **State — engine** | `terrarium/engines/state/engine.py` | ✅ done | C1 | StateEngine: commit step, bus+ledger integration, snapshot, replay |
| **Policy — evaluator** | `terrarium/engines/policy/evaluator.py` | 📋 stub | F1 | Condition language |
| **Policy — enforcement** | `terrarium/engines/policy/enforcement.py` | 📋 stub | F1 | Hold/block/escalate/log |
| **Policy — templates** | `terrarium/engines/policy/templates.py` | 📋 stub | F1 | Template instantiation |
| **Policy — functions** | `terrarium/engines/policy/functions.py` | 📋 stub | F1 | Registered functions |
| **Policy — loader** | `terrarium/engines/policy/loader.py` | 📋 stub | F1 | YAML loading |
| **Policy — runtime** | `terrarium/engines/policy/runtime.py` | 📋 stub | F1 | Runtime CRUD |
| **Policy — engine** | `terrarium/engines/policy/engine.py` | 📦 partial | F1 | execute() pass-through (Phase F) |
| **Permission — engine** | `terrarium/engines/permission/engine.py` | 📦 partial | F2 | execute() pass-through (Phase F) |
| **Permission — scope** | `terrarium/engines/permission/scope.py` | 📋 stub | F2 | Visibility scoping |
| **Permission — authority** | `terrarium/engines/permission/authority.py` | 📋 stub | F2 | Authority checks |
| **Budget — engine** | `terrarium/engines/budget/engine.py` | 📦 partial | F2 | execute() pass-through (Phase F) |
| **Budget — tracker** | `terrarium/engines/budget/tracker.py` | 📋 stub | F2 | Resource accounting |
| **Responder — engine** | `terrarium/engines/responder/engine.py` | ✅ done | C3 | WorldResponderEngine with Tier1Dispatcher |
| **Responder — tier1** | `terrarium/engines/responder/tier1.py` | ✅ done | C2 | Verified pack dispatch via PackRuntime |
| **Responder — tier2** | `terrarium/engines/responder/tier2.py` | 📋 stub | C3 | Profile-constrained LLM |
| **Adapter — engine** | `terrarium/engines/adapter/engine.py` | 📦 partial | E1 | execute() pass-through (Phase F) |
| **Adapter — MCP** | `terrarium/engines/adapter/protocols/mcp_server.py` | 📋 stub | E1 | MCP server |
| **Adapter — ACP** | `terrarium/engines/adapter/protocols/acp_server.py` | 📋 stub | E1 | ACP server |
| **Adapter — OpenAI** | `terrarium/engines/adapter/protocols/openai_compat.py` | 📋 stub | E1 | OpenAI compat |
| **Adapter — HTTP** | `terrarium/engines/adapter/protocols/http_rest.py` | 📋 stub | E1 | REST endpoints |
| **Adapter — manifest** | `terrarium/engines/adapter/tool_manifest.py` | 📋 stub | E1 | Tool manifest gen |
| **Adapter — observation** | `terrarium/engines/adapter/observation.py` | 📋 stub | E1 | Observation delivery |
| **Animator — engine** | `terrarium/engines/animator/engine.py` | ✅ done | G3 | WorldAnimatorEngine — tick(), configure(), behavior modes |
| **Animator — context** | `terrarium/engines/animator/context.py` | ✅ done | G3 | AnimatorContext (reuses WorldGenerationContext) |
| **Animator — generator** | `terrarium/engines/animator/generator.py` | ✅ done | G3 | OrganicGenerator — LLM events |
| **Shared scheduler** | `terrarium/scheduling/scheduler.py` | ✅ done | G3 | WorldScheduler — one-shot, recurring, trigger events |
| **Reporter — engine** | `terrarium/engines/reporter/engine.py` | ✅ done | F3 | ReportGeneratorEngine orchestrator |
| **Reporter — scorecard** | `terrarium/engines/reporter/scorecard.py` | ✅ done | F3 | 8 metrics per-actor + collective |
| **Reporter — gaps** | `terrarium/engines/reporter/capability_gaps.py` | ✅ done | F3 | 3-action lookahead classification |
| **Reporter — causal** | `terrarium/engines/reporter/causal_trace.py` | ✅ done | F3 | Causal chain rendering |
| **Reporter — diff** | `terrarium/engines/reporter/diff.py` | ✅ done | F3 | Counterfactual comparison |
| **Reporter — challenges** | `terrarium/engines/reporter/world_challenges.py` | ✅ done | F3 | World→Agent (4 challenge types) |
| **Reporter — boundaries** | `terrarium/engines/reporter/agent_boundaries.py` | ✅ done | F3 | Agent→World (5 boundary categories) |
| **Compiler — engine** | `terrarium/engines/world_compiler/engine.py` | 📦 partial | D4a | D4a done (YAML+NL compile, service resolution), D4b stubs |
| **Compiler — plan** | `terrarium/engines/world_compiler/plan.py` | ✅ done | D4a | WorldPlan + ServiceResolution models |
| **Compiler — yaml parser** | `terrarium/engines/world_compiler/yaml_parser.py` | ✅ done | D4a | 2-file YAML parsing + reality expansion |
| **Compiler — nl parser** | `terrarium/engines/world_compiler/nl_parser.py` | ✅ done | D4a | LLM Layer 1: NL → structured dicts |
| **Compiler — service resolution** | `terrarium/engines/world_compiler/service_resolution.py` | ✅ done | D4a | Full resolution chain (packs → profiles → kernel) |
| **Compiler — prompt templates** | `terrarium/engines/world_compiler/prompt_templates.py` | ✅ done | D4a | PromptTemplate framework + NL templates |
| **Compiler — schema resolver** | `terrarium/engines/world_compiler/schema_resolver.py` | 📋 stub | D4b | Service resolution |
| **Compiler — data gen** | `terrarium/engines/world_compiler/data_generator.py` | 📋 stub | D4b | Entity generation |
| **Compiler — plan review** | `terrarium/engines/world_compiler/plan_reviewer.py` | 📋 stub | D4b | Plan presentation |
| **Compiler — reality** | `terrarium/engines/world_compiler/reality_expander.py` | 📋 stub | D4b | Reality expansion |
| **Compiler — personality** | `terrarium/engines/world_compiler/personality_generator.py` | 📋 stub | D4b | Actor personalities |
| **Compiler — seeds** | `terrarium/engines/world_compiler/seed_processor.py` | 📋 stub | D4b | Seed processing |
| **Compiler — bootstrap** | `terrarium/engines/world_compiler/service_bootstrapper.py` | 📋 stub | G2 | Compile-time inference |
| **Feedback — engine** | `terrarium/engines/feedback/engine.py` | 📋 stub | G4 | FeedbackEngine |
| **Feedback — annotations** | `terrarium/engines/feedback/annotations.py` | 📋 stub | G4 | Annotation store |
| **Feedback — promotion** | `terrarium/engines/feedback/promotion.py` | 📋 stub | G4 | Tier promotion |
| **Feedback — sync** | `terrarium/engines/feedback/sync.py` | 📋 stub | G4 | External drift |

### World Building

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **Reality — presets** | `terrarium/reality/presets.py` | ✅ done | D1 | YAML preset loading (ideal/messy/hostile) |
| **Reality — dimensions** | `terrarium/reality/dimensions.py` | ✅ done | D1 | 5 dimensions, 18 attrs, frozen Pydantic |
| **Reality — labels** | `terrarium/reality/labels.py` | ✅ done | D1 | Two-level config: labels ↔ per-attribute numbers |
| **Reality — expander** | `terrarium/reality/expander.py` | ✅ done | D1 | Expand + build LLM prompt context (NO entity mutation) |
| **Reality — overlays** | `terrarium/reality/overlays.py` | ✅ done | D1 | Registry framework (concrete overlays post-MVP) |
| **Reality — seeds** | `terrarium/reality/seeds.py` | 📦 partial | D1 | Generic Seed model done, SeedProcessor stubs (D4) |
| **Actors — definition** | `terrarium/actors/definition.py` | ✅ done | D2 | Frozen model with extensible metadata + friction_profile |
| **Actors — personality** | `terrarium/actors/personality.py` | ✅ done | D2 | Trait-based Personality + FrictionProfile (replaces AdversarialProfile) |
| **Actors — registry** | `terrarium/actors/registry.py` | ✅ done | D2 | Generic multi-key registry with query(**filters) |
| **Actors — generator** | `terrarium/actors/generator.py` | ✅ done | D2 | ActorPersonalityGenerator Protocol + SimpleActorGenerator |
| **Kernel — registry** | `terrarium/kernel/registry.py` | ✅ done | D3 | SemanticRegistry (9 categories, 33 services, TOML-loaded) |
| **Kernel — categories** | `terrarium/kernel/categories.py` | ✅ done | D3 | 9 SemanticCategory models |
| **Kernel — primitives** | `terrarium/kernel/primitives.py` | ✅ done | D3 | 45 SemanticPrimitive models |
| **Kernel — surface** | `terrarium/kernel/surface.py` | ✅ done | D3 | APIOperation (MCP+HTTP+OpenAI+Anthropic) + ServiceSurface |
| **Kernel — resolver** | `terrarium/kernel/resolver.py` | ✅ done | D3 | ServiceResolver (Context Hub→OpenAPI→LLM→kernel chain) |
| **Kernel — context hub** | `terrarium/kernel/context_hub.py` | ✅ done | D3 | ContextHubProvider (chub CLI integration) |
| **Kernel — openapi** | `terrarium/kernel/openapi_provider.py` | ✅ done | D3 | OpenAPIProvider (spec parsing) |

### Packs

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **Pack base** | `terrarium/packs/base.py` | ✅ done | C2 | ServicePack + ServiceProfile ABCs + dispatch_action |
| **Pack framework** | `terrarium/packs/registry.py, runtime.py, loader.py` | ✅ done | C2 | PackRegistry, PackRuntime, PackLoader — generic plugin framework |
| **Email pack** | `terrarium/packs/verified/email/` | ✅ done | C2 | 6 tools, 3 entity schemas, state machines, handlers |
| **Chat pack** | `terrarium/packs/verified/chat/` | 📋 stub | G1 | |
| **Tickets pack** | `terrarium/packs/verified/tickets/` | 📋 stub | G1 | |
| **Payments pack** | `terrarium/packs/verified/payments/` | 📋 stub | G1 | |
| **Repos pack** | `terrarium/packs/verified/repos/` | 📋 stub | G1 | |
| **Calendar pack** | `terrarium/packs/verified/calendar/` | 📋 stub | G1 | |
| **Stripe profile** | `terrarium/packs/profiled/stripe/` | 📋 stub | G2 | |
| **Gmail profile** | `terrarium/packs/profiled/gmail/` | 📋 stub | G2 | |
| **Slack profile** | `terrarium/packs/profiled/slack/` | 📋 stub | G2 | |

### Gateway & Connectivity

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **Gateway — core** | `terrarium/gateway/gateway.py` | 📋 stub | E1 | Request handling |
| **Gateway — router** | `terrarium/gateway/router.py` | 📋 stub | E1 | Request routing |
| **Gateway — monitor** | `terrarium/gateway/monitor.py` | 📋 stub | E1 | Observability |
| **Gateway — rate limiter** | `terrarium/gateway/rate_limiter.py` | 📋 stub | E1 | Per-actor limits |
| **Gateway — auth** | `terrarium/gateway/auth.py` | 📋 stub | E1 | Authentication |

### Runs & Product

| Module | Path | Status | Phase | Notes |
|--------|------|--------|-------|-------|
| **Runs — manager** | `terrarium/runs/manager.py` | ✅ done | F4 | Run lifecycle: create/start/complete/fail, tag resolution, disk persistence |
| **Runs — snapshot** | `terrarium/runs/snapshot.py` | ✅ done | F4 | Wraps SnapshotStore, auto-snapshot by interval |
| **Runs — artifacts** | `terrarium/runs/artifacts.py` | ✅ done | F4 | Report/scorecard/event_log/config persistence as JSON files |
| **Runs — comparison** | `terrarium/runs/comparison.py` | ✅ done | F5 | Scores/events/entity state comparison + governed vs ungoverned governance metrics |
| **Runs — replay** | `terrarium/runs/replay.py` | ✅ done | F4 | Event log replay with pause/resume/seek |
| **CLI** | `terrarium/cli.py` | 📋 stub | H1 | 12 commands |
| **Dashboard** | `terrarium/dashboard/` | 📋 stub | H2 | Web UI |
| **Templates** | `terrarium/templates/` | 📋 stub | H3 | World templates |

---

## Phase Roadmap

### Phase A — Foundation Modules (standalone, no cross-deps)

| Item | Scope | Depends On | Done Criteria |
|------|-------|-----------|---------------|
| **A1: persistence/** | Database ABC, SQLite impl, migrations, snapshots | nothing | Can create tables, CRUD entities, run migrations, take/restore snapshots. All persistence tests pass. |
| **A2: config/** | TOML loader, schema validation, layered merging, env vars, secure refs | nothing | Can load terrarium.toml, merge with env overrides, validate against schema. All config tests pass. |
| **A3: bus/** | EventBus pub/sub, fanout, SQLite persistence, replay | A1 (persistence) | Can publish events, subscribers receive them, events persist to SQLite, replay works. All bus tests pass. |
| **A4: ledger/** | Ledger append, query, export | A1 (persistence) | Can append entries, query by type/time/actor, export to JSON. All ledger tests pass. |

### Phase B — Core Infrastructure (builds on A)

| Item | Scope | Depends On | Done Criteria |
|------|-------|-----------|---------------|
| **B1: validation/** | Schema, state machine, consistency, temporal, amounts validators | core types | All 5 validators work standalone with test data. Validation pipeline chains them. |
| **B2: pipeline/** | DAG execution, short-circuit, side effect queue | A3 (bus), A4 (ledger) | Mock steps flow through DAG. Short-circuit works. Side effects re-enter. Ledger records each step. |
| **B3: llm/** | Mock provider, router, tracker | A4 (ledger) | Mock provider returns deterministic responses. Router routes by engine/use-case. Tracker records usage to ledger. |
| **B4: registry/** | Engine registry, topological sort, wiring, health | core engine | Can register engines, sort by deps, wire to bus, aggregate health checks. |

### Phase C — First Vertical Wire (proves architecture)

| Item | Scope | Depends On | Done Criteria |
|------|-------|-----------|---------------|
| **C1: state engine** | Entity store, event log, causal graph | A1, B4 | Can store/query entities, append/query events, build causal chains. |
| **C2: email pack** | One complete Tier 1 pack | B1 (validation) | email_send, email_list, email_read work. State machines validated. Deterministic. |
| **C3: WIRE** | Full pipeline with real state + email + pass-through engines | A3, B2, B4, C1, C2 | One email_send action flows through all 7 pipeline steps. State committed. Event logged. Bus delivers. Tests prove E2E. |

### Phase D — World Building

| Item | Scope | Depends On | Done Criteria |
|------|-------|-----------|---------------|
| **D1: reality/** | Presets, dimensions, expander | nothing | load_preset('messy') returns correct dimension labels. Two-level config: labels AND per-attribute numbers. Expander packages dimension context for LLM prompts. WorldConditions model with 5 dimensions. |
| **D2: actors/** | Personality, registry, generator | D1 | Can generate personalities from Social Friction dimension (not just adversarial). Registry with role-based lookup. |
| **D3: kernel/** | Semantic registry, categories, primitives | nothing | "stripe" → money_transactions. Category returns correct primitives. |
| **D4: world compiler** | YAML → world plan → populated state | A1, B3, C1, D1, D2, D3 | **D4a (DONE):** WorldPlan model, YAMLParser, NLParser, CompilerServiceResolver, PromptTemplate framework, infer path (Context Hub + OpenAPI + kernel). **D4b (DONE):** WorldGenerationContext, live LLM entity generation (Gemini), batched personality generation (1 call/role), seed expansion, SchemaValidator, StateEngine population, snapshot. Compiler presets (ideal/messy/hostile). **NOT in D4:** Runtime behavior modes are G3 (Animator). Promotion gate is G4. Blueprints are H3. |

### Phase E — Connectivity

| Item | Scope | Depends On | Done Criteria |
|------|-------|-----------|---------------|
| **E1: gateway + MCP/HTTP** | Gateway (single entry point), MCP server adapter, HTTP REST adapter (FastAPI), WebSocket event streaming, tool manifest generation, capability check, real-world API paths from packs | C3 (wire) | ✅ **DONE.** Gateway discovers tools from PackRegistry. MCP server exposes tools via `mcp.Server`. HTTP REST exposes `/api/v1/tools`, `/api/v1/actions/{tool}`, real-world paths (e.g. `/email/v1/messages/send`), entity query, health. WebSocket streams live events. Capability gaps return structured response with available_tools. All requests traced via GatewayRequestEntry in Ledger. 40 new tests. 1058 total passed. |

### Phase F — Governance & Observation

| Item | Scope | Depends On | Done Criteria |
|------|-------|-----------|---------------|
| **F1: policy engine** | Safe condition evaluator (ast-based), enforcement dispatcher (BLOCK/HOLD/ESCALATE/LOG), policy loader from WorldPlan, governed/ungoverned mode | C3 | ✅ **DONE.** Policy triggers on action, conditions evaluate safely, enforcement precedence (block>hold>escalate>log), ungoverned mode logs without blocking. 16 policy tests + 35 evaluator tests. |
| **F2: permission + budget** | Permission checks (read/write/action authority), budget tracking (per-actor api_calls/llm_spend), threshold events | C3 | ✅ **DONE.** Permission denies out-of-scope access with PermissionDeniedEvent. Budget tracks per-actor, emits warning/critical/exhausted events. Ungoverned mode allows but logs. 11 permission + 11 budget tests + 5 E2E governance tests. |
| **F3: reporter** | ✅ **DONE.** Governance scorecard (8 metrics per-actor + collective), capability gap log (3-action lookahead: HALLUCINATED/ADAPTED/ESCALATED/SKIPPED), causal trace rendering, two-direction observation (World→Agent: 4 challenge types + Agent→World: 5 boundary categories), counterfactual diff, fidelity report. HTTP API: /api/v1/report, /scorecard, /gaps, /causal/{id}, /challenges. 58 new tests. Pure computation — zero LLM. | C3, F1 | All formulas implemented, HTTP endpoints active, zero stubs. |
| **F4: runs/** | Run management, snapshots, artifacts, comparison | C3, F3 | ✅ **DONE** — RunManager, ArtifactStore, SnapshotManager, RunReplayer implemented. App wired. HTTP endpoints added. 29 unit tests + 3 integration tests. |
| **F5: gov vs ungov** | Same world, two modes, diff | F1, F4 | ✅ **DONE** — RunComparator with compare_governed_ungoverned(). Extracts governance metrics from event logs. format_comparison() produces spec table. |

### Phase G — Richness

| Item | Scope | Depends On | Done Criteria |
|------|-------|-----------|---------------|
| **G1: remaining packs** | Chat, tickets, payments, repos, calendar | C2 pattern | All 6 Tier 1 packs work with validated state machines. |
| **G2: profiles + bootstrap** | Tier 2 curated profiles, Context Hub integration | B3, D3 | Tier 2 curated profiles. Context Hub deep integration. External spec (OpenAPI) transformers. Service bootstrapper uses infer chain from D4. |
| **G3: animator** | ✅ **DONE.** WorldAnimatorEngine with behavior modes (static=OFF, dynamic=FULL, reactive=RESPONSE_ONLY). AnimatorContext reuses WorldGenerationContext pattern. Level 2 per-attribute numbers (reliability.failures=20 → 20% probability) drive probabilistic events. Shared WorldScheduler module (terrarium/scheduling/) supports one-shot, recurring, trigger events — usable by any engine. OrganicGenerator uses ANIMATOR_EVENT PromptTemplate + LLM. Every event through 7-step pipeline via app.handle_action(). Creativity budget enforced. | C3, D1, D4b | 56 new tests. Static returns []. Dynamic generates scheduled + probabilistic + organic. Reactive only on recent actions. Events in ledger. |
| **G4: feedback** | Annotations, tier promotion, drift | F3 | Promotion logic: capture → compile-pack → verify → promote --submit-pr. Annotations. Drift detection. |

### Phase H — Product

| Item | Scope | Depends On | Done Criteria |
|------|-------|-----------|---------------|
| **H1: CLI** | All 12 commands working | D4, E1, F5 | Every CLI command runs and produces output. |
| **H2: dashboard** | Live view, replay, reports | F3, F4 | Dashboard serves, shows live events, replays runs. |
| **H3: templates** | 3 built-in templates | D4 | Customer support, incident response, sandbox templates generate valid worlds. |

---

## Session Log

> Append after each implementation session. Never delete entries.

### Session 2026-03-21 — A1: Persistence Module (initial implementation)
- **Implemented:** SQLiteDatabase (10 methods), MigrationRunner (6 methods), ConnectionManager (4 methods), SnapshotStore (5 methods)
- **Tests:** 28 tests across 6 test files — ALL PASSING
- **Coverage:** 98% (244 statements, 5 misses in error handling paths)
- **Decisions:**
  - WAL mode disabled for `:memory:` databases (not supported)
  - `backup()` uses aiosqlite's internal thread dispatch for sqlite3 backup API
  - Transaction context manager uses explicit BEGIN/COMMIT/ROLLBACK
- **Gotchas:** aiosqlite.Row works for dict conversion but requires `row_factory` set on connection
- **Zero stubs:** All concrete methods implemented. Only ABC abstract methods have `...` bodies (correct pattern).

### Session 2026-03-21 — A1: Persistence Review Fixes
- **Fixes applied (4):**
  - MEDIUM: Replaced all `assert self._conn` with `RuntimeError` in sqlite.py (7 occurrences) — assertions disabled with `python -O`
  - MEDIUM: Wrapped migrate_up() and migrate_down() in `transaction()` blocks — atomic migration batches, rollback on failure
  - MINOR: Added exception safety to manager.py shutdown() — collects errors per-connection, clears dict regardless
  - MINOR: Changed snapshot ID format to `snap_{run_id}_{label}_{hex8}` — more traceable than bare UUID
- **Tests added (18 new, 46 total):**
  - sqlite: closed-db RuntimeError, parameterized queries, WAL mode verified, WAL skipped for :memory:, FK enforcement, NULL handling, malformed SQL
  - migrations: out-of-order registration, down-to-zero revert, atomic failure rollback
  - manager: shutdown closes all, multiple named connections, empty health check
  - snapshot: load nonexistent (FileNotFoundError), metadata nonexistent, empty dir listing
  - config: type validation, serialization round-trip
- **Coverage:** 96% (263 stmts, 11 misses — all in error handling branches)
- **Zero stubs confirmed:** `grep "^\s*\.\.\.$"` returns nothing on concrete files
- **Next:** A2 (config module)

### Session 2026-03-21 — A2: Config Module
- **Implemented:** ConfigLoader (7 methods), TerrariumConfig (imports from 20 subsystem configs), ConfigRegistry (4 methods), TunableRegistry (5 methods), ConfigValidator (4 methods)
- **Also fixed:** Added defaults to 11 engine config files (state, policy, permission, budget, responder, animator, adapter, reporter, feedback, world_compiler, pipeline). Fixed terrarium.development.toml (mode "interactive" → "governed").
- **Key decision:** schema.py imports FROM subsystem config files — each module owns its config definition (SRP). No duplicate definitions.
- **Tests:** 45 tests across 5 test files — ALL PASSING
- **Coverage:** 99% (249 stmts, 3 misses)
- **Test breakdown:** test_loader (14), test_schema (9), test_registry (8), test_tunable (5), test_validation (9)
- **Zero stubs:** All config/ methods implemented
- **Next:** A3 (bus module)

### Session 2026-03-21 — A3: Event Bus Module
- **Implemented:** EventBus (9 methods), TopicFanout (4 methods), BusPersistence (6 methods via AppendOnlyLog), ReplayEngine (3 methods), MiddlewareChain (3 methods), LoggingMiddleware, MetricsMiddleware
- **Also created:** `persistence/append_log.py` — shared AppendOnlyLog base (5 methods) used by bus and future ledger (A4)
- **Key decisions:**
  - BusPersistence receives `Database` via DI — does NOT create SQLiteDatabase (per DESIGN_PRINCIPLES)
  - Shared AppendOnlyLog in persistence/ — avoids duplicate SQL between bus and ledger
  - BusPersistence.shutdown() is a no-op — ConnectionManager owns database lifecycle
  - Persist BEFORE fanout — log is never behind in-memory state
  - Back-pressure: drop oldest when subscriber queue full (SQLite log preserves everything for replay)
  - Per-subscriber consumer tasks (Actor-model isolation) — failures don't crash bus
  - Wildcard "*" subscriptions receive all events
- **Tests:** 61 bus tests + 11 AppendOnlyLog tests = 72 new tests — ALL PASSING
- **Coverage:** 94% across bus/ + persistence/ (604 stmts, 35 misses in edge cases)
- **Test breakdown:** test_bus (14), test_fanout (9), test_persistence (9), test_replay (6), test_middleware (8), test_integration (4), test_append_log (11)
- **DI verified:** `grep "import.*SQLiteDatabase" terrarium/bus/*.py` = 0 results
- **Zero stubs:** All bus/ concrete methods implemented. Only BusMiddleware Protocol has `...` bodies (correct Python pattern).
- **Known limitation:** Event deserialization returns base Event, not typed subtypes. Full payload preserved in JSON. Typed deserialization via registry in Phase C+.
- **A1-A3 integration verified:** ConnectionManager → Database → EventBus → publish → persist → replay — full lifecycle works.
- **Next:** A4 (ledger module)

### Session 2026-03-21 — A4: Ledger Module
- **Implemented:** Ledger (5 methods), LedgerEntry hierarchy (7 subclasses + base + registry), LedgerQueryBuilder (7 methods), LedgerExporter (3 methods)
- **Key design decisions:**
  - Receives `Database` via DI — same pattern as BusPersistence. No SQLiteDatabase imports.
  - Uses `AppendOnlyLog` from persistence/ — shared infra with bus
  - SQL-level filtering: actor_id and engine_name stored as separate indexed columns (not just in JSON payload) for O(log n) queries
  - Typed deserialization via `ENTRY_REGISTRY` — query returns correct subclass (PipelineStepEntry, LLMCallEntry, etc.), NOT base LedgerEntry. Solves the deserialization problem that bus punted on.
  - `shutdown()` is a no-op — ConnectionManager owns DB lifecycle
  - Entry type filtering: disabled types return -1, not written to DB
- **Tests:** 46 tests across 5 test files — ALL PASSING
- **Coverage:** 99% (217 stmts, 2 misses)
- **Test breakdown:** test_entries (12), test_ledger (13), test_query (9), test_export (8), test_integration (4)
- **Integration verified:** Ledger + Bus coexist on same ConnectionManager with separate databases. Full A1-A4 smoke test passes.
- **Zero stubs:** All ledger/ methods implemented
- **Phase A COMPLETE:** All 4 foundation modules done (persistence, config, bus, ledger). 513 tests, 0 failures. Ready for Phase B.

### Session 2026-03-21 — B1: Validation Framework
- **Implemented:** SchemaValidator (type/enum/min/max checks), StateMachineValidator (transition + valid transitions), ConsistencyValidator (async ref validation via entity schemas), TemporalValidator (timestamp + ordering), AmountValidator (refund/budget/non-negative), ValidationPipeline (orchestrator with LLM retry)
- **Also created:** ValidationType enum in core/types.py (SCHEMA/STATE_MACHINE/CONSISTENCY/TEMPORAL/AMOUNT). ValidationConfig in validation/config.py (strict_mode, max_retries, max_reference_depth). Added to TerrariumConfig.
- **Key design decisions:**
  - All schemas/state machines/entity schemas passed as DATA parameters, never hardcoded
  - ConsistencyValidator reads reference fields from entity SCHEMAS (e.g., `"ref:charge"`), not magic strings in field values
  - ValidationResult includes validation_type enum for structured reporting to ledger/reporter
  - ValidationPipeline uses config.max_retries (not hardcoded retry count)
  - ValidationResult.merge() returns NEW frozen instance (immutable)
- **Tests:** 50 tests across 6 test files — ALL PASSING
- **Coverage:** 98% (205 stmts, 5 misses)
- **Test breakdown:** test_schema (10), test_state_machine (8), test_consistency (8), test_temporal (6), test_amounts (8), test_pipeline (10)
- **Zero stubs:** All validation/ methods implemented
- **Next:** B2 (pipeline module)

### Session 2026-03-21 — B2: Pipeline DAG
- **Implemented:** PipelineDAG (5 methods: execute, step_names, _record_result, _record_to_ledger, _publish_event), BasePipelineStep (ABC + _make_result), build_pipeline_from_config, SideEffectProcessor (5 methods: enqueue, process_all, start_background, stop, _side_effect_to_context)
- **Critical fix:** StepResult.is_terminal property implemented in core/context.py (was `...` stub). DENY/HOLD/ESCALATE/ERROR → terminal, ALLOW → not terminal.
- **Key design decisions:**
  - Pipeline is PURE DAG mechanics — no engine logic. Mock steps for all testing.
  - builder takes `dict[str, PipelineStep]` not EngineRegistry — decoupled from B4
  - Bus and ledger optional (DI) — pipeline works without either
  - SideEffects re-enter full pipeline at depth+1, bounded by max_depth
  - Exception in step → auto-generated ERROR StepResult
  - Duration tracked via time.monotonic()
- **Tests:** 39 tests across 5 files — ALL PASSING
- **Coverage:** 85% (background async loop not exercised in sync tests — acceptable)
- **Test breakdown:** test_dag (16), test_step (5), test_builder (5), test_side_effects (8), test_integration (5)
- **Zero stubs:** All pipeline/ methods implemented (only ABC abstractmethod has `...`)
- **Next:** B3 (LLM module)

### Session 2026-03-21 — B3: LLM Module (initial implementation)
- **Implemented:** 6 provider types (AnthropicProvider, OpenAICompatibleProvider, GoogleNativeProvider, ACPClientProvider, CLISubprocessProvider, MockLLMProvider), SecretResolver (EnvVar + File + Chain), ProviderRegistry (factory for all 6 types), LLMRouter (config-driven routing by engine/use-case), UsageTracker (ledger + in-memory aggregates)
- **New files created:** secrets.py, providers/acp_client.py, providers/cli_subprocess.py
- **Key design decisions:**
  - SecretResolver protocol: extensible (env vars → file → vault). ChainResolver tries in order.
  - Router routing key: `{engine_name}_{use_case}` with fallback to `{engine_name}` then defaults.
  - All provider SDKs are real: anthropic (AsyncAnthropic), openai (AsyncOpenAI), google (genai).
  - Cost estimation per model in AnthropicProvider (Sonnet/Opus/Haiku rates).
- **Tests:** 67 tests across 11 test files — 65 PASSED, 2 SKIPPED (require API keys)
- **Zero stubs:** All LLM/ methods implemented

### Session 2026-03-21 — B3: ACP Rewrite + CLI + Conversation + Real Testing
- **Major rewrite: ACP provider** — Complete rewrite from HTTP-based (acp-sdk) to stdio JSON-RPC based on symphony-go reference implementation. ACP protocol is NOT HTTP — it's bidirectional JSON-RPC 2.0 over stdin/stdout of a spawned subprocess.
- **ACP protocol flow:** initialize → authenticate → session/new → session/set_mode → session/prompt → read streaming session/update notifications → extract text from agent_message_chunk content blocks
- **ACP bidirectional handling:** Agent sends requests BACK to host during generation:
  - `session/request_permission` — auto-approved (first "allow" option)
  - `fs/read_text_file` — reads file from disk, responds with content
  - `fs/write_text_file` — writes file to disk
  - `terminal/*` — acknowledged (no-op for now)
- **CLI subprocess rewrite:** Changed from stdin piping to command-line argument passing. Each CLI has different invocation pattern: `claude -p "prompt"`, `codex exec "prompt"`, `gemini "prompt"`. stdin=DEVNULL (not PIPE). Default timeout 120s.
- **ConversationManager** (NEW: `llm/conversation.py`) — Provider-aware multi-turn context:
  - Anthropic path: sends full history (prompt caching optimizes repeated prefix)
  - OpenAI path: sends full history (implicit caching)
  - Fallback path: prepends "[Previous conversation]" text to prompt
  - Sessions: create_session(), generate(), end_session(), get_history(), clear_history()
- **OpenAI fix:** newer models (gpt-5.x) require `max_completion_tokens` instead of `max_tokens`. Implemented try/except fallback.
- **Real API test results (all gated by TERRARIUM_RUN_REAL_API_TESTS=1):**
  - API providers: Anthropic ✅, OpenAI ✅, Google ✅ (single-turn + multi-turn context retention)
  - CLI subprocess: claude ✅, codex ✅, gemini ✅ (single-turn + claude multi-turn via ConversationManager)
  - ACP stdio: codex-acp ✅, gemini --experimental-acp ✅
  - claude-agent-acp ❌ (adapter bug — see Known Issues)
- **Key fixes during testing:**
  - ACP text chunks joined with `""` not `"\n"` (streaming chunks are partial words)
  - `agent_message_chunk` content is a dict `{"type":"text","text":"..."}`, not a string
  - Gemini ACP uses `--experimental-acp` flag (not `--acp`)
  - ACP process spawned via `bash -lc` to inherit login shell PATH
- **Tests:** 673 tests total (15 skipped for API keys/servers), 0 failures
- **Zero stubs:** All LLM/ methods implemented
- **Next:** E2E review completed (see session below). Ready for B4 (registry module)

### Session 2026-03-21 — Full E2E Review & Bug Bounty (A1-B3)
- **Scope:** Principal engineer review of ALL implemented modules (A1-A4, B1-B3) covering design principles compliance, security audit, correctness bugs, cross-module integration
- **Review method:** 5 parallel review streams: design principles (34 findings), foundation bug bounty (19), pipeline+validation bug bounty (18), LLM bug bounty (21), cross-module integration (11)
- **Total findings:** 77 unique issues after dedup (6 CRITICAL, 20 HIGH, 37 MEDIUM, 14 LOW)
- **Fixed:** 75 issues. **Deferred:** 2 (ISS-028 SnapshotStore DI, ISS-051 snapshot connection lifecycle → B4)
- **Master list:** See `/MASTER_ISSUES.md` for full tracked list with fix status
- **Security fixes (CRITICAL):**
  - SQL injection in AppendOnlyLog — name validation via regex
  - ACP command injection in _spawn and terminal — removed `bash -lc`, use `create_subprocess_exec` directly
  - ACP unrestricted file access — path sandboxing to `_cwd`
  - FileResolver path traversal — `is_relative_to()` validation
  - TOML-Config field name mismatch (runtime break) — aligned field names
- **Design principle compliance fixes:**
  - 12 config models frozen (`model_config = ConfigDict(frozen=True)`)
  - 4 async I/O wrappers (snapshot, export, manager, secrets)
  - Silent exception swallowing → logging in bus._consumer, middleware, persistence
  - EventBusProtocol added to core/protocols.py
  - ConnectionManager DI factory pattern (no longer hardwired to SQLiteDatabase)
  - Hardcoded values moved to config or class constants (queue size, model names, pricing)
- **Correctness fixes:**
  - Race condition in ConnectionManager (asyncio.Lock)
  - Non-reentrant transaction flag → depth counter
  - Broken replay_range logic → SQL-level sequence filtering
  - Temporal validator naive/aware datetime crash → try/except TypeError
  - Fanout back-pressure drops now counted
  - Validation retry hard cap (10) + callback exception handling
  - Side effect exponential blowup → max_total cap (1000)
  - Side effect deque → asyncio.Queue
  - CLI/ACP process killed on timeout (no more zombies)
  - Registry shutdown_all now calls provider.close()
- **LLM module fixes:**
  - OpenAI silent retry narrowed to BadRequestError only
  - API key leakage sanitized in error messages
  - API key removed from instance variables after SDK init
  - ConversationManager history capped at 50 turns
  - ACP generate() serialized via asyncio.Lock
  - ACP JSON-RPC protocol compliance (proper error responses)
  - ACP token usage extraction priority fix
- **Tests:** 673 passed, 15 skipped, 0 failures (unchanged count — fixes were backward compatible)

### Session 2026-03-21 — B4: Registry Module
- **Implemented:** EngineRegistry (8 methods incl. Kahn's topo sort), HealthAggregator (4 methods), wire_engines + shutdown_engines + inject_dependencies, create_default_registry (composition root), BaseEngine lifecycle (12 methods), error constructors (4 classes)
- **Also implemented:** All core/ test stubs (types, events, context, protocols, engine, errors) — 48 core tests
- **Key decisions:**
  - Kahn's algorithm with sorted queues for deterministic topo ordering
  - shutdown_engines stops in reverse topo order (dependents first)
  - Composition root uses lazy imports inside function body
  - _dependencies dict set on engine by inject_dependencies (not constructor injection)
  - HealthAggregator.is_healthy() is sync (reads cache from last check_all)
  - ConnectionManager DI factory pattern (from E2E review ISS-027)
- **Tests:** 85 new tests across 10 test files (48 core + 37 registry). Total: 702 passed, 15 skipped, 0 failures.
- **Verification:** Zero stubs in registry/ and core/ (only abstractmethod `...`). Composition root isolation verified. Integration smoke test passed.
- **Phase B COMPLETE.** All 4 foundation (A1-A4) + 4 infrastructure (B1-B4) modules done.
- **Next:** C1 (state engine — first vertical slice)

### Session 2026-03-21 — C1: State Engine (first vertical slice)
- **Implemented:** EntityStore (6 CRUD methods), EventLog (5 methods), CausalGraph (6 methods + BFS), StateEngine (14 methods), state migrations (12 versioned DDL via MigrationRunner)
- **Key architectural decisions:**
  - **Schema ownership centralized:** Tables defined in `engines/state/migrations.py` as `Migration[]`, applied by `MigrationRunner` during `_on_initialize()`. NO scattered `CREATE TABLE` in component files. Establishes the pattern for all future engines.
  - **Retractability:** `update()` and `delete()` return pre-mutation state (previous_fields). Enables compensating events for undo.
  - **Bus integration:** `execute()` publishes WorldEvent to bus after commit → other engines react.
  - **Ledger integration:** `execute()` records `StateMutationEntry` to ledger for audit trail.
  - **Event sourcing:** EventLog stores complete serialized events as JSON payload. `rebuild_from_events()` can reconstruct state from the append-only log.
  - **Transactional atomicity:** `execute()` wraps all deltas + event + causal edges in `db.transaction()`.
  - **No cross-engine imports:** state/ imports only core/ and persistence/.
  - **DI for components:** Store, EventLog, CausalGraph receive `Database` ABC (not SQLiteDatabase).
  - **Split migrations:** Each SQL statement is a separate migration (aiosqlite's `execute()` handles single statements only).
- **Tests:** 52 new tests across 5 files (store: 12, event_log: 10, causal_graph: 10, engine: 14, integration: 6). Total: 761 passed, 15 skipped, 0 failures.
- **Verification:** Zero stubs. CREATE TABLE only in migrations.py. Zero cross-engine imports.
- **Review fixes (principal engineer review):**
  - CRITICAL: Updated `StateEngineProtocol` in `core/protocols.py` to match engine signatures (6 method mismatches fixed: get_entity needs entity_type, propose_mutation takes list, commit_event returns EventId, snapshot takes label, diff returns flexible type, get_timeline accepts entity_id)
  - HIGH: Wrapped `commit_event()` in `db.transaction()` for atomicity
  - HIGH: Added failure cleanup in `_on_initialize()` — closes DB on error
  - HIGH: Added warning log to `EventLog._deserialize()` fallback (was silent except)
  - MEDIUM: Now uses `StateConfig` model instead of raw dict.get() with hardcoded defaults
  - MEDIUM: Updated `get_timeline()` to match protocol (accepts entity_id, optional start/end)
  - MEDIUM: Fixed stale `tests/engines/test_state.py` (6 dead stub tests replaced with redirect)
  - MEDIUM: Corrected IMPLEMENTATION_STATUS.md — removed "replay+retract support" claim (not yet implemented)
- **Tests:** 755 passed (6 dead stubs removed), 15 skipped, 0 failures. Protocol compliance verified: isinstance(StateEngine, StateEngineProtocol) = True.
- **Next:** C2 (email pack — first complete Tier 1 service pack)

### Session 2026-03-21 — C2: Extensible Pack Framework + Email Pack
- **Implemented:** PackRegistry (multi-index: pack_name, tool_name, category), PackRuntime (generic validate→dispatch→validate pipeline), PackLoader (importlib-based filesystem discovery), EmailPack (6 tools, 3 entity schemas, state machines, data-driven handler dispatch), Tier1Dispatcher wired to PackRuntime
- **Key architectural decisions:**
  - **Pack as plugin:** Framework contains ZERO pack-specific logic. New pack = drop a directory with pack.py implementing ServicePack ABC. `PackLoader.discover()` finds it via importlib.
  - **Framework enforcement:** PackRuntime validates input, output entity schemas, state transitions, and tags FidelityMetadata. Calling `pack.handle_action()` directly bypasses all validation — the tests prove this.
  - **Data-driven dispatch:** Packs populate `_handlers: ClassVar[dict]` mapping tool names to handler functions. `dispatch_action()` on the ABC does the lookup. Zero if/else in any handler.
  - **Ownership boundaries:** Packs import ONLY from `core/` (types, context). NEVER from persistence/, engines/, or bus/. Packs produce `StateDelta` objects — `StateEngine` persists them.
  - **Update validation is partial:** Runtime validates full schema only on `create` operations. `update` operations are partial — only type-check the provided fields, not required fields.
  - **Stub-resilient discovery:** PackLoader and PackRegistry gracefully handle stub packs (get_tools returning None) by logging warnings and skipping tool indexing.
- **New error types:** PackError, PackNotFoundError, PackLoadError, DuplicatePackError
- **Tests:** 64 new tests across 5 files (registry: 11, runtime: 12, loader: 7, email_pack: 12, integration: 8 + framework enforcement). Total: 803 passed, 15 skipped, 0 failures.
- **Verification:** Framework is pack-agnostic (grep confirms zero EmailPack references in framework code). Email pack imports only core/. Zero stubs.
- **Next:** C3 WIRE (full pipeline E2E — first action flowing through all 7 steps)

### Session 2026-03-22 — C3: WIRE (Full Pipeline E2E)
- **Implemented:** TerrariumApp (reusable bootstrap framework), WorldResponderEngine (Tier1 pack dispatch + state building), ValidationStep (PipelineStep wrapper), 4 pass-through engines (permission/policy/budget/adapter)
- **TerrariumApp is the standard boot path:** start() → handle_action() → stop(). Every test, CLI command, and future integration uses this. NOT one-off code.
- **Pass-through engines explicitly marked:** Docstrings say "PASS-THROUGH (Phase F)" with exact replacement instructions. StepResult.message="pass-through" enables drift-detection tests.
- **WorldResponderEngine integrates:** PackRegistry.discover() → PackRuntime → Tier1Dispatcher → EmailPack → ResponseProposal → ctx.response_proposal. State built from StateEngine via query_entities().
- **Manual E2E verified:** email_send through 7 steps → entity in store, 7 ledger entries (all ALLOW), bus delivers, clean shutdown.
- **Test harness: 4 categories (21 tests):**
  - Category A (Agent Simulation): 5 tests — send, read, reply, list, full conversation
  - Category B (Wire Integrity): 7 tests — 7 steps in ledger, state committed, event in log/bus, ledger mutations, fidelity
  - Category C (Replay/Audit): 4 tests — bus replay, ledger query by actor, state timeline, causal chain
  - Category D (Drift Prevention): 5 tests — pass-through markers, unknown action, short-circuit, lifecycle, concurrency
- **Tests:** 824 passed, 15 skipped, 0 failures
- **Phase C COMPLETE.** First vertical slice proven end-to-end.
- **Next:** D1 (reality/ — presets, dimensions, expander)

### Session 2026-03-22 — Phase D Prerequisite: Spec Sync
- **Updated:** terrarium-full-spec.md, DESIGN_PRINCIPLES.md, IMPLEMENTATION_STATUS.md, 25 source/test files
- **Preset renames:** pristine→ideal, realistic→messy, harsh→hostile
- **Dimension renames:** 5 old names → Information Quality, Reliability, Social Friction, Complexity, Boundaries
- **New enums:** BehaviorMode (STATIC/REACTIVE/DYNAMIC)
- **Roadmap realignment:** Infer moved from G2 to D4. G2 = profiles + Context Hub only.
- **Key clarification:** Dimensions are personality traits (LLM-interpreted), not code-applied percentages. Two-level config: labels for simple users, per-attribute numbers for advanced.

### Session 2026-03-22 — D1: Reality Module Review Fixes
- **13 findings fixed** from D1 Reality Module review (FIX-01 through FIX-13)
- **CRITICAL:** Spec doc preset name "clean" → "ideal" (aligned to user choice), Literal validation on sophistication field, overlay stubs return safe defaults instead of `...`
- **HIGH:** `_DIMENSION_DEFAULTS` → `DIMENSION_DEFAULTS` (public API), YAML error wrapping in `load_from_yaml()`, `SeedProcessor` stubs return type-safe defaults, overlay `compose()` raises on unknown names
- **MEDIUM:** Lazy import in `presets.py` moved to top-level, `RealityConfig` made frozen (`ConfigDict(frozen=True)`), stale docstrings fixed in animator/generator.py and personality_generator.py, overlay registry rejects duplicates, `SeedConfig` unified with `Seed` (re-export alias)
- **Files modified:** 9 source files, 1 spec doc, 1 status doc

### Session 2026-03-22 — D2: Actors Module (Generic Actor Framework)
- **Implemented:** Personality (trait-based with extensible `traits: dict`), FrictionProfile (replaces AdversarialProfile — full spectrum: uncooperative/deceptive/hostile), ActorDefinition (frozen with metadata/friction_profile/personality_hint), ActorPersonalityGenerator Protocol, SimpleActorGenerator (heuristic with seeded RNG), ActorRegistry (generic multi-key with query(**filters))
- **Key framework decisions:**
  - Actors are DATA, not code — no per-role subclasses, all driven by YAML
  - `query(**filters)` replaces `get_adversarial()/get_agents()/get_humans()` — zero role-specific logic
  - Generator is a Protocol — D2 provides heuristic, D4 plugs in LLM
  - Friction distribution: intensity values used as approximate percentages, seeded for reproducibility
  - AdversarialProfile kept as deprecated alias → FrictionProfile(category="hostile")
  - All models frozen Pydantic with extensible traits/metadata dicts
- **Tests:** 45 new tests across 4 files. Total: 879 passed, 15 skipped, 0 failures.
- **Next:** D3 (kernel — service resolution framework)

### Session 2026-03-22 — D3: Service Resolution Framework (Kernel + Context Hub)
- **Implemented:** SemanticRegistry (9 categories, 33 services from TOML), APIOperation (multi-protocol: MCP + HTTP + OpenAI + Anthropic views), ServiceSurface (operations + entity schemas + state machines + validate_surface()), ContextHubProvider (chub CLI integration), OpenAPIProvider (spec parsing), ServiceResolver (resolution chain: providers → LLM callback → kernel fallback), ExternalSpecProvider Protocol
- **Key framework decisions:**
  - APIOperation captures abstract operations, derives protocol-specific views via to_mcp_tool()/to_http_route()/to_openai_function()/to_anthropic_tool()
  - ServiceSurface is the universal output: same model whether spec came from pack, Context Hub, OpenAPI, or LLM inference
  - Resolution chain ordered by confidence: pack (1.0) → profile → Context Hub (0.7) → OpenAPI (0.5) → LLM (D4) → kernel (0.2)
  - validate_surface() enforces quality for pack promotion: catches missing operations, missing response schemas, missing entity schemas
  - Context Hub accessed via chub CLI subprocess (same pattern as ACP/CLI providers)
  - SemanticRegistry uses tomllib (Python 3.11+ built-in) for TOML loading
- **Multi-protocol support:** Every APIOperation can be exposed as MCP tool, HTTP route, OpenAI function, or Anthropic tool — all from one definition
- **Tests:** 60 new tests across 8 files. Total: 928 passed, 15 skipped, 0 failures.
- **Next:** D4 (world compiler — uses kernel + resolver + D1 reality + D2 actors)

### Session 2026-03-22 — D4a: World Compiler Planning Phase
- **Implemented:** WorldPlan (frozen model — D4a/D4b contract), YAMLParser (2-file format: world def + compiler settings), NLParser (LLM Layer 1: NL→structured YAML via PromptTemplate), CompilerServiceResolver (pack→profile→external→LLM→kernel chain), PromptTemplate framework (reusable, data-driven prompts)
- **Key decisions:**
  - TWO LLM layers clearly separated: Layer 1 = NL→YAML translation (D4a), Layer 2 = entity generation (D4b)
  - PromptTemplate framework: prompts are DATA, not inline strings. New use cases add templates, not code.
  - D4a is behavior-agnostic: static/reactive/dynamic stored in plan but doesn't affect compilation
  - WorldPlan carries everything D4b needs: resolved services, conditions, actor specs, policies, seeds
  - CompilerServiceResolver bridges PackRegistry (Tier 1/2) with D3 ServiceResolver (external specs + kernel)
  - NLParser gracefully falls back to defaults if compiler settings LLM call fails
- **YAML fixtures:** acme_support.yaml, acme_compiler.yaml, minimal_world.yaml
- **D4b stubs:** data_generator, personality_generator, plan_reviewer, reality_expander, schema_resolver, seed_processor, service_bootstrapper — all correctly marked with NotImplementedError
- **Tests:** 42 new tests across 5 files. Total: 970 passed, 15 skipped, 0 failures.
- **Next:** D4b (entity generation + validation + seed injection + StateEngine population)

### Session 2026-03-22 — D4b: World Compiler Generation Phase
- **Implemented:**
  - **WorldGenerationContext** — single source of truth for ALL LLM prompts. Assembles reality narrative + behavior mode + domain + policies + actors + mission ONCE, shared by all generators.
  - **WorldDataGenerator** — LLM-only entity generation (NO heuristic fallback). 1 LLM call per entity type. Reads ServiceSurface.entity_schemas.
  - **CompilerPersonalityGenerator** — batched per-role (1 LLM call per role, not per actor). For acme_support: 3 calls instead of 53. SimpleActorGenerator for STRUCTURE only (count expansion, friction distribution).
  - **CompilerSeedProcessor** — LLM seed expansion with full world context. Handles both "fields" and "properties" keys from Gemini.
  - **PlanReviewer** — format, YAML export, validate, generate_report.
  - **StateEngine.populate_entities()** — bulk entity creation for world generation.
  - **App LLM wiring** — TerrariumApp._initialize_llm() creates ProviderRegistry + LLMRouter from terrarium.toml. _inject_cross_engine_deps() injects into all engines.
  - **Compiler presets** — ideal.yaml, messy.yaml, hostile.yaml as full compiler configs (reality + behavior + fidelity + mode + animator).
  - **Prompt templates** — ENTITY_GENERATION (with full world context: reality narrative, behavior mode, policies, actors, mission), PERSONALITY_BATCH (per-role), SEED_EXPANSION (full context).
- **Config:** Default LLM switched to Gemini 3 Flash (`gemini-3-flash-preview`) via native Google provider. Env var: `GOOGLE_API_KEY`. All 5 routing entries point to gemini.
- **Dead code removed:** reality_expander.py, schema_resolver.py (pure delegation wrappers).
- **Design principles enforced:**
  - NO heuristics — `_generate_fallback()` deleted, no `randint()`, no hardcoded data
  - NO fallbacks — `CompilerError` raised if LLM unavailable
  - NO silent failures — errors propagate
  - LLM call count: 9 for YAML blueprint (3 entity types + 3 roles + 3 seeds), 11 for NL flow (+2 NL interpretation)
- **Live E2E verified:** `tests/live/test_yaml_blueprint.py` passes with real Gemini — generates narratively coherent entities shaped by reality dimensions and behavior mode (Margaret Chen VIP with frustration_level=critical, SLA breach threads, pending refund approvals).
- **Architecture clarification:** Behavior mode (static/dynamic/reactive) shapes entity generation as a HINT (LLM generates "settled" vs "in-flight" states). The REAL behavioral difference is at RUNTIME via the Animator (Phase G3 — NOT BUILT). D4b compiles the initial world; G3 makes it live.
- **Infer path (G2→D4) verified:** Full chain works: Pack → Profile → Context Hub (chub CLI) → OpenAPI (full 3.x parser) → LLM callback → Kernel classification. 22 real tests. Only promotion gate (capture_surface/compile_to_pack) is Phase G4.
- **Tests:** 1033 passed, 24 skipped, 0 failures. Live tests under `tests/live/` (require GOOGLE_API_KEY).
- **Next:** Principal engineer review of D4b, then E1 (Gateway + MCP/HTTP) or G3 (Animator) based on priority.

### Session 2026-03-22 — E1: Gateway + MCP/HTTP
- **Implemented:**
  - **Gateway** (`terrarium/gateway/gateway.py`) — single entry/exit point for all agent communication. PURE protocol translation, ZERO business logic. Discovers tools from PackRegistry (same source as WorldResponderEngine). Routes all requests through `app.handle_action()` → 7-step pipeline. Records every request to Ledger (`GatewayRequestEntry`).
  - **MCP Server Adapter** (`engines/adapter/protocols/mcp_server.py`) — real `mcp.Server` with `list_tools()` and `call_tool()` handlers. Tools auto-discovered from packs via `ServiceSurface.get_mcp_tools()`. Supports stdio transport for local agents.
  - **HTTP REST Adapter** (`engines/adapter/protocols/http_rest.py`) — FastAPI server with routes: `GET /api/v1/tools`, `POST /api/v1/actions/{tool}`, `GET /api/v1/health`, `GET /api/v1/entities/{type}`. Auto-mounts real-world API paths from pack `http_path` definitions (e.g., `POST /email/v1/messages/send`). WebSocket `/api/v1/events/stream` for live event streaming from EventBus.
  - **Tool Manifest Generator** (`engines/adapter/tool_manifest.py`) — generates protocol-specific tool manifests from PackRegistry. Supports MCP, HTTP, OpenAI, Anthropic formats.
  - **Capability Check** (`engines/adapter/engine.py`) — real `has_tool()` check replaces pass-through. Returns `CapabilityGapEvent` with `available_tools` for unknown tools.
  - **Email Pack HTTP Paths** — all 6 email tools now have real-world `http_path` and `http_method` (e.g., `email_send` → `POST /email/v1/messages/send`).
- **Key design decisions:**
  - Gateway discovers tools from the SAME PackRegistry the Responder uses — single source of truth
  - When a new pack is added, its tools are AUTOMATICALLY available via MCP and HTTP — zero gateway changes
  - Three access layers: tool discovery (`/api/v1/tools`), MCP (tool names), HTTP (real-world paths) — all resolve to same pipeline
  - Pack owns its HTTP paths (`APIOperation.http_path`) — gateway just mounts them
  - EventBus subscriber pattern for WebSocket streaming
- **Wiring:** Gateway initialized in `app.py` after pipeline. Pack registry injected into adapter engine for capability checks.
- **Tests:** 40 new tests across 5 files (gateway core, adapter engine, MCP server, HTTP REST, tool manifest). Total: 1058 passed, 24 skipped, 0 failures.
- **NOT in E1:** OpenAI/Anthropic/ACP adapters (E2), auth/rate-limiting/middleware (E2), observation delivery (E2), remote/hosted (E3).

### Session 2026-03-22 — F1-F2: Real Governance (Policy + Permission + Budget)
- **Implemented:**
  - **Permission Engine** (`engines/permission/engine.py`) — real permission checks: write access to service, action-specific constraints (e.g., `max_amount: 5000`), read access. Unknown actors allowed. Ungoverned mode: denials logged but allowed.
  - **Authority Checker** (`engines/permission/authority.py`) — standalone `check_read()`, `check_write()`, `check_action()` for use outside pipeline.
  - **Policy Engine** (`engines/policy/engine.py`) — real policy evaluation from user YAML. Matches triggers (string keywords or dict with action+condition). Evaluates conditions via safe expression evaluator. Applies enforcement precedence (BLOCK > HOLD > ESCALATE > LOG). Ungoverned mode: all become LOG.
  - **Condition Evaluator** (`engines/policy/evaluator.py`) — safe expression evaluation using Python `ast` module. Supports dot access (`input.amount`), comparisons, logical operators, containment. Rejects unsafe nodes (calls, imports, lambdas, comprehensions). Malformed = False.
  - **Enforcement Handler** (`engines/policy/enforcement.py`) — dispatches to BLOCK (DENY + PolicyBlockEvent), HOLD (HOLD + PolicyHoldEvent), ESCALATE (ESCALATE + PolicyEscalateEvent), LOG (ALLOW + PolicyFlagEvent).
  - **Budget Engine** (`engines/budget/engine.py`) — real per-actor budget tracking. Tracks api_calls and llm_spend remaining. Emits BudgetDeductionEvent on every action. Warning at 80%, critical at 95%, exhausted at 100%. Ungoverned: logs exhaustion but allows.
  - **Budget Tracker** (`engines/budget/tracker.py`) — stateful per-actor budget management with threshold deduplication.
- **Key design decisions:**
  - Governance is USER-CONFIGURED from YAML — no hardcoded conditions
  - `type: external` = user's AI agent under test; `type: internal` = simulated NPCs
  - EVERY governance decision is an EVENT published to EventBus via StepResult.events
  - Governed mode enforces; ungoverned mode logs same events but doesn't block
  - Uses EXISTING event types (PolicyBlockEvent, PermissionDeniedEvent, BudgetExhaustedEvent etc.)
  - Uses EXISTING types (StepVerdict, EnforcementMode, ActionCost, BudgetState)
- **Wiring:** `app.configure_governance(plan)` injects policies + world_mode into all 3 engines. Actor registry shared across all governance engines.
- **Tests:** 78 new tests: 35 evaluator + 16 policy + 11 permission + 11 budget + 5 E2E governance. Total: 1140 passed, 24 skipped, 0 failures.
- **Zero pass-throughs remain** in policy/permission/budget engines.

### Session 2026-03-22 — G3: World Animator + Shared Scheduler
- **Implemented:**
  - **WorldScheduler** (`terrarium/scheduling/scheduler.py`) — shared scheduling framework as a separate reusable module. Supports one-shot, recurring, and trigger-based events. Any engine can register events. Uses `ConditionEvaluator` from policy engine for trigger evaluation.
  - **AnimatorContext** (`engines/animator/context.py`) — runtime context that REUSES `WorldGenerationContext` pattern from D4b. Provides `get_probability(dimension, attribute)` for Level 2 per-attribute numbers (e.g., `reliability.failures=20` → 0.20). No context duplication.
  - **WorldAnimatorEngine** (`engines/animator/engine.py`) — full implementation with:
    - `configure(plan, scheduler)` — sets behavior mode, registers YAML scheduled events, creates organic generator
    - `tick(world_time)` — Layer 1a (scheduler), Layer 1b (probabilistic from Level 2 numbers), Layer 2 (LLM organic)
    - `_execute_event()` — routes through `app.handle_action()` (7-step pipeline), publishes AnimatorEvent
    - `_generate_probabilistic_events()` — uses Level 2 per-attribute numbers as probabilities
    - `_handle_event()` — tracks recent agent actions for reactive mode
  - **OrganicGenerator** (`engines/animator/generator.py`) — LLM-driven event generation using AnimatorContext + ANIMATOR_EVENT PromptTemplate. Respects creativity budget.
  - **AnimatorConfig** (`engines/animator/config.py`) — expanded to full YAML: creativity, event_frequency, contextual_targeting, escalation_on_inaction, creativity_budget_per_tick, tick_interval_seconds, scheduled_events.
  - **ANIMATOR_EVENT template** (`prompt_templates.py`) — added to PromptTemplate framework.
- **Key design decisions:**
  - Scheduler is a SEPARATE shared module (`terrarium/scheduling/`) — not inside animator
  - AnimatorContext REUSES WorldGenerationContext — no context assembly duplication
  - Level 2 per-attribute numbers (staleness=30, failures=20) are RUNTIME parameters: LLM receives them as narrative context, scheduler uses them as probabilities
  - Compiler presets (ideal/messy/hostile) → WorldConditions → ongoing creative direction to Animator's LLM
  - Static = OFF, Dynamic = scheduled + organic, Reactive = response to agent actions only
  - All events through 7-step pipeline (permission → policy → budget → capability → responder → validation → commit)
- **Tests:** 56 new tests: 12 scheduler + 18 engine + 6 generator + 12 context + 4 integration + 4 smoke. Total: 1201 passed, 24 skipped, 0 failures.
- **Zero stubs** in animator or scheduling modules.

### Session 2026-03-23 — F4-F5: Run Management + Governed vs Ungoverned Diff
- **Implemented:**
  - **RunManager** (`runs/manager.py`) — full lifecycle: create → start → complete/fail. Tag resolution ("gov" → run_id), "last" keyword. Disk persistence with `_load_existing_runs()` for restart resilience.
  - **ArtifactStore** (`runs/artifacts.py`) — JSON file persistence for report, scorecard, event_log, config. Save returns file path. List returns metadata dicts with type/path/size_bytes.
  - **SnapshotManager** (`runs/snapshot.py`) — wraps existing SnapshotStore from persistence layer. Auto-snapshot by tick interval. Delegates to `SnapshotStore.save_snapshot()`.
  - **RunComparator** (`runs/comparison.py`) — ALL 6 API methods implemented: compare(), compare_scores(), compare_events(), compare_entity_states(), format_comparison(), compare_governed_ungoverned(). Governance-specific metrics extracted from event logs (blocked, approvals, budget_exceeded, unauthorized, policy_hits).
  - **RunReplayer** (`runs/replay.py`) — event log replay with start/pause/resume/seek/stop. Lazy ArtifactStore loading.
  - **App wiring** (`app.py`) — create_run(), end_run(), diff_runs(), diff_governed_ungoverned(). Run management initialized in start(). Properties for run_manager and artifact_store.
  - **HTTP endpoints** (`http_rest.py`) — POST /api/v1/runs, GET /api/v1/runs, GET /api/v1/runs/{id}, POST /api/v1/runs/{id}/complete, GET /api/v1/runs/{id}/artifacts, GET /api/v1/runs/{id}/artifacts/{type}, GET /api/v1/diff, GET /api/v1/diff/governed.
- **Key design decisions:**
  - All stubs preserved existing constructor signatures (DI pattern: `config: RunConfig, persistence: ConnectionManager`)
  - RunComparator reads from ArtifactStore (post-hoc comparison) — does NOT recompute metrics
  - Governed vs ungoverned comparison extracts governance metrics from serialized event logs using event_type patterns
  - Artifacts are JSON files in `data/runs/{run_id}/` — portable and inspectable
  - Auto-snapshot on run completion (configurable via RunConfig.snapshot_on_complete)
- **Tests:** 29 unit tests (9 manager + 6 artifacts + 4 snapshot + 6 comparison + 4 replay) + 3 integration tests. Total: 1330 passed, 25 skipped, 10 xfailed, 0 failures.
- **Zero stubs** in runs/ module.

---

## Known Issues / Tech Debt

### Fixed in A2 Review
- **CRITICAL: Schema-TOML field name mismatch** — `schema.py` had `run: RunConfig` but `terrarium.toml` has `[runs]`. The `[runs]` section was silently ignored during loading. Fixed by renaming to `runs: RunConfig`.
- **REGRESSION: test_types.py 4 broken stubs** — `TestFidelityAndRealityEnums` methods added during rewiring had missing `self` param and `...` bodies. Implemented with real assertions.

### Fixed in A3 Review
- **CRITICAL: LedgerProtocol type mismatch** — Protocol had `append(event: Event)` but ledger uses `LedgerEntry` objects (completely different hierarchy). Fixed: protocol now takes `Any` to avoid circular imports, with `append(entry) -> int`, `query(filters) -> list`, `get_count()`. Removed `export()` from protocol (utility, not core interface).
- **HIGH: Metrics never incremented** — `events_delivered` and `events_dropped` always 0. Fixed: `_consumer` changed from `@staticmethod` to instance method, increments `_events_delivered` after each successful callback. `fanout()` now returns drop count, bus increments `_events_dropped`.
- **HIGH: Back-pressure drops uncounted** — fanout silently dropped events with no tracking. Fixed: `fanout()` returns `int` (number of drops), bus.publish() captures and increments counter.
- **MEDIUM: publish() after shutdown()** — no guard. Fixed: raises `RuntimeError` if bus not initialized.
- **MEDIUM: Missing DB indexes** — event_log had no indexes for event_type or created_at. Fixed: indexes created in BusPersistence.initialize().
- **MEDIUM: replay_timerange() untested** — added test_replay_timerange test.

### Fixed in A4 Review
- **WARNING: datetime.utcnow() deprecated** — `ledger/entries.py:41` used `datetime.utcnow()` which is deprecated in Python 3.12. Fixed: `datetime.now(timezone.utc)`.
- **MEDIUM: aggregate() was a stub** — `LedgerQueryBuilder.aggregate()` accepted params but didn't store them. Fixed: stores `LedgerAggregation` in builder state.
- **MEDIUM: Time-range filtering was Python post-filtering** — Ledger query filtered time in Python after fetching all rows. Fixed: extended `AppendOnlyLog.query()` with `range_filters` parameter (supports `>=`, `<=`, `>`, `<` operators) and `offset` parameter. Ledger now pushes start_time/end_time to SQL WHERE clause. Also added SQL OFFSET support. 6 new tests added for range filters + offset.

### Fixed in B2 Review
- **HIGH: StepResult.events type was `list[EventId]` but pipeline published as `Event`** — EventId is a string NewType. Pipeline's isinstance guard silently skipped all events. Fixed: changed type to `list[Any]`, removed isinstance guard, events now publish directly to bus.
- **MEDIUM: SideEffectProcessor missing temporal fields** — _side_effect_to_context didn't copy world_time, wall_time, tick, run_id, world_mode, reality_preset from parent context. Side effects lost temporal lineage. Fixed: all temporal and simulation fields now copied.
- **MEDIUM: SideEffectProcessor.process_all() no error handling** — one failing SE crashed all processing. Fixed: try/except around pipeline.execute(), skip on error, continue processing remaining SEs.

### Fixed in B3 Review (complete rewrite + real testing)
- **CRITICAL: ACP provider complete rewrite** — was HTTP-based (acp-sdk), rewrote to stdio JSON-RPC based on symphony-go reference. ACP protocol is bidirectional JSON-RPC 2.0 over spawned subprocess stdin/stdout. Handles agent requests (permission, file read/write, terminal) back to host.
- **CRITICAL: CLI subprocess rewrite** — changed from stdin piping to command-line argument passing. Each CLI has different invocation: `claude -p`, `codex exec`, `gemini` (positional). stdin=DEVNULL.
- **HIGH: Added `error` field to LLMResponse** — explicit error tracking instead of embedding errors in `content` field. All providers use `error=str(e)`.
- **HIGH: Tracker success detection** — changed from brittle `content.startswith("Error:")` to `response.error is None`.
- **HIGH: OpenAI max_completion_tokens** — newer models (gpt-5.x) require `max_completion_tokens` instead of `max_tokens`. Try/except fallback.
- **MEDIUM: CLI timeout configurable** — was hardcoded 60s, now 120s default with constructor override.
- **MEDIUM: Registry error message** — now includes list of valid provider types.
- **NEW: ConversationManager** — provider-aware multi-turn: Anthropic (prompt caching), OpenAI (implicit caching), fallback (prepend history). Sessions with create/generate/end/clear.
- **Real API integration tests** — all 3 paths tested live: API (Anthropic/OpenAI/Google ✅), CLI (claude/codex/gemini ✅), ACP (codex-acp/gemini-acp ✅). All gated by `TERRARIUM_RUN_REAL_API_TESTS=1`.
- **ACP text extraction fixes** — chunks joined with `""` not `"\n"` (partial words), content dict handling for agent_message_chunk.

### Open (Phase C+)
- **Event deserialization returns base Event** — `Event.model_validate_json()` deserializes to base `Event`, not typed subtypes (WorldEvent, PolicyBlockEvent, etc.). Full payload is preserved in JSON, no data lost. Typed deserialization via event type registry to be added in Phase C+ when engines start producing typed events.
- **Structured output not yet implemented** — `LLMRequest.output_schema` and `LLMResponse.structured_output` fields exist but no provider parses structured output. Will implement when Tier 2 responder needs it (Phase C3).
- **Cost estimation only in Anthropic** — other providers return `cost_usd=0.0`. Will add cost tables for OpenAI/Google when needed.
- **claude-agent-acp adapter bug** — `claude-agent-acp` (https://github.com/anthropics/claude-agent-acp) fails on `session/new` with "Internal error: Query closed before response received". This is a bug in the adapter itself, not in our ACP client implementation. Our ACP client works correctly with `codex-acp` and `gemini --experimental-acp`. Workaround: use `claude -p` via CLI subprocess provider, or Anthropic API provider. Monitor upstream for fix.
- **ACP clarification questions** — ACP protocol has no explicit "ask clarification" method. Agent streams text and the turn completes. For interactive back-and-forth, use multi-turn sessions (send another `session/prompt`). This is by-design in ACP, not a limitation of our implementation.

---

## Architecture Decisions Made During Implementation

> Record decisions that deviate from or clarify the original design.

### A3: LedgerProtocol redesign
- **Decision:** LedgerProtocol accepts `Any` (not `Event`) because ledger entries (`LedgerEntry` subclasses) are a completely separate type hierarchy from bus events (`Event` subclasses). Using `Any` avoids circular imports between `core/protocols.py` and `ledger/entries.py`. The runtime Ledger implementation will use typed `LedgerEntry` objects.
- **Rationale:** Bus carries domain events (WorldEvent, PolicyBlockEvent). Ledger records operational audit entries (PipelineStepEntry, LLMCallEntry). These are fundamentally different concerns despite both being append-only logs.

### A3: EventBus._consumer as instance method
- **Decision:** Changed `_consumer` from `@staticmethod` to instance method to access `self._events_delivered` counter.
- **Rationale:** Metrics tracking requires the consumer to increment delivery counters. An instance method is cleaner than passing callback functions.
