# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What is Terrarium

Terrarium is a **world engine for AI agents**. It creates stateful, causal, observable realities where agents exist as participants — not as isolated prompt loops calling tools, but as actors inside a world that has places, institutions, other agents, budgets, policies, communication systems, and real consequences.

Users describe a world in natural language or YAML. Terrarium compiles it into a deep, reproducible simulation. Agents interact with the world through standard protocols (MCP, ACP, OpenAI function calling, Anthropic tool use, raw HTTP). Everything that happens is recorded, scored, and diffable.

## Spec Documents

For deep understanding of the system, read these internal docs in order:

- `internal_docs/terrarium-full-spec.md` — Complete specification: all 10 engines, the runtime pipeline, fidelity tiers, validation framework, governed vs. ungoverned, multi-agent, world packs, CLI, and roadmap.
- `internal_docs/terrarium-world-definition-and-compiler.md` — World definition YAML schema, reality dimensions (labels + per-attribute numbers), behavior modes, fidelity tiers, compiler settings, blueprints, reproducibility model, and the five user-facing concepts.
- `internal_docs/terrarium-architecture.md` — The two-half architecture (deterministic engine vs. generative layer), three generation phases, fidelity tiers, world conditions, the self-improving loop, and the end-to-end flow diagram.
- `DESIGN_PRINCIPLES.md` — Architectural principles, design rules (DOs/DON'Ts), patterns (event bus, ledger, pipeline, gateway, composition root), async flow, and enforcement mechanisms.

## Commands

```bash
# Install (uses uv with hatchling build backend)
uv sync --all-extras

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/path/to/test_file.py

# Run a single test
uv run pytest tests/path/to/test_file.py::test_function_name -v

# Run tests with coverage
uv run pytest --cov=terrarium --cov-report=term-missing

# Lint
uv run ruff check terrarium/ tests/
uv run ruff format --check terrarium/ tests/

# Type check
uv run mypy terrarium/

# CLI entry point (typer-based, entry point: terrarium/cli.py)
uv run terrarium --help
```

## Architecture

### The Two Halves

**World Law (Deterministic Engine):** Owns state, events, causal graph, permissions, policy enforcement, budget accounting, time, visibility, mutation validation, replay/fork/diff, governance scoring. The engine never guesses, never generates text, never decides what a service "would probably do." It enforces structure.

**World Content (Generative Layer):** Creates realistic data, service behavior, actor responses, scenario complications. But it operates inside constraints set by the engine. The generative layer proposes; the engine disposes. A generated response that violates state consistency is rejected. A generated mutation that exceeds budget is denied.

### Two-Phase Model

- **Phase A (World Compilation):** The compiler transforms user intent into a runnable world. LLM generates all world data — entities, actors, service state — seeded for reproducibility and shaped by reality dimensions. Dimensions determine what IS in the world at compile time. The compiler executes a 7-step pipeline: Parse → Classify → Resolve → Generate → Validate → Inject seeds → Snapshot.
- **Phase B (Runtime):** The 7-step governance pipeline processes every agent action. Services return data as it exists in state. No LLM decides runtime reality — it was baked in during compilation.

### The 10 Engines

Every engine inherits from `BaseEngine` (`core/engine.py`), which provides lifecycle hooks (`_on_initialize`, `_on_start`, `_on_stop`) and event bus integration. Engines override `_handle_event` for their core logic.

| Engine | Package | Responsibility |
|--------|---------|---------------|
| **World Compiler** | `engines/world_compiler/` | Transforms NL/YAML descriptions into runnable worlds. Schema resolution, data generation, plan review. |
| **State Engine** | `engines/state/` | Single source of truth. Entity storage, event log, causal graph, snapshot/fork/diff. All state mutations go through its commit interface. |
| **Policy Engine** | `engines/policy/` | Evaluates governance rules. YAML condition language. Enforcement modes: hold, block, escalate, log. Precedence: block > hold > escalate > log. |
| **Permission Engine** | `engines/permission/` | RBAC + visibility scoping. Determines what each actor can see and do. Filters query results by actor scope. |
| **Budget Engine** | `engines/budget/` | Tracks resource consumption per actor (api_calls, llm_spend_usd, world_actions, time). Emits warning/critical/exhausted events. |
| **World Responder** | `engines/responder/` | Generates responses. Tier 1: deterministic pack logic, no LLM. Tier 2: profile-constrained LLM, seeded. |
| **World Animator** | `engines/animator/` | Generates events between agent turns. Controlled by behavior mode (static=off, reactive=cause-effect, dynamic=fully alive). Two layers: deterministic schedule + generative content with creativity budget. |
| **Agent Adapter** | `engines/adapter/` | Translates between external protocols (MCP, ACP, OpenAI, Anthropic, HTTP) and internal world actions. Handles capability gap detection. |
| **Report Generator** | `engines/reporter/` | Produces governance scorecards, capability gap logs, causal traces, counterfactual diffs. Scores are derived from events, not LLM judgment. Two-direction observation: world→agent challenges + agent→world behavior. |
| **Feedback Engine** | `engines/feedback/` | Manages the self-improving loop: annotations, tier promotion (bootstrapped→curated→verified), external source sync. |

### 7-Step Governance Pipeline

Every action flows through: **permission → policy → budget → capability → responder → validation → commit**. This pipeline IS the law of the world. Nothing bypasses it. Agent actions, animator events, side effects, and approval responses all flow through the same seven steps. Steps are configured in `terrarium.toml` under `[pipeline]`. Steps can short-circuit (e.g., policy blocks before reaching responder).

### Semantic Kernel (`kernel/`)

Maps services to semantic categories (communication, work-management, money, authority, identity, storage, code, scheduling, monitoring) via `SemanticCategory` and `SemanticPrimitive`. This is a static registry — no LLMs. When the compiler encounters a service name (e.g., "Stripe"), it classifies it to a category, inherits core primitives, then specializes. This means bootstrapped services start from category semantics, not from zero. Services are resolved through `ServiceResolver` and exposed via `ServiceSurface` with `APIOperation` definitions.

### Fidelity Tiers (Two Tiers at Runtime)

- **Tier 1 (Verified Pack):** Hand-built deterministic simulation. No LLM at runtime. Fully reproducible. Benchmark-grade. Built along mission-critical paths of flagship templates.
- **Tier 2 (Profile-Backed):** Curated prompt profile with schemas, state machines, response templates, behavioral annotations. LLM generates content within constraints. Seeded. Includes bootstrapped services (compile-time inferred, labeled as `fidelity_source: "bootstrapped"`).
- **There is no Tier 3 at runtime.** Bootstrapping happens at compile time and produces a Tier 2 profile.

### Service Resolution Priority Chain (Compiler)

When the compiler encounters a service name:
1. **Semantic classification** — map to category, inherit primitives
2. **Verified Pack?** — if found → Tier 1, done
3. **Curated Profile?** — if found → Tier 2, done
4. **External spec?** — Context Hub (`chub get`), OpenAPI spec, MCP Registry → generate draft profile → Tier 2
5. **LLM Inference** — bootstrap from category primitives + general knowledge → Tier 2 (labeled "bootstrapped")

### Reality Dimensions — The World's Personality

Five dimensions that are personality traits, not engineering parameters. The LLM interprets them holistically — "somewhat neglected information" means the LLM creates a world where data management has been neglected, contextually and narratively coherent.

| Dimension | What it answers | Sub-attributes |
|-----------|----------------|----------------|
| **Information Quality** | How well-maintained is the data? | staleness, incompleteness, inconsistency, noise |
| **Reliability** | Do the tools work? | failures, timeouts, degradation |
| **Social Friction** | How difficult are the people? | uncooperative, deceptive, hostile, sophistication |
| **Complexity** | How messy are the situations? | ambiguity, edge_cases, contradictions, urgency, volatility |
| **Boundaries** | What limits exist? | access_limits, rule_clarity, boundary_gaps |

Three presets: `ideal` / `messy` (default) / `hostile`. Two-level config: labels for simple users, per-attribute numbers (0-100) for advanced. Mix freely.

### Behavior Modes

| Mode | Animator | Reproducibility |
|------|----------|----------------|
| **static** | Off. World frozen after compilation. | Fully deterministic. Same seed = same world. |
| **reactive** | Responds only to agent actions/inaction. | Same agent actions = same reactions. |
| **dynamic** | Fully active. Generates contextual events. | Seeds provide similar character. Use snapshots for exact replay. |

### Five User-Facing Concepts (the stable API)

| Concept | What it answers | Flag |
|---------|----------------|------|
| **Description** | What is this world? | NL or YAML |
| **Reality** | What kind of world? | `--reality ideal/messy/hostile` |
| **Behavior** | Is the world alive? | `--behavior static/reactive/dynamic` |
| **Fidelity** | How accurate are services? | `--fidelity auto/strict/exploratory` |
| **Mode** | Are rules enforced? | `--mode governed/ungoverned` |

### Composition Root

`registry/composition.py` is the **only** place that imports concrete engine classes. All other code depends on `typing.Protocol` interfaces from `core/protocols.py`. This is strictly enforced — no cross-engine imports.

### Event Bus & Ledger (separate concerns)

- **Bus** (`bus/`): Inter-engine communication via typed events. Events are immutable Pydantic models persisted to SQLite before delivery. Per-engine `asyncio.Queue` instances.
- **Ledger** (`ledger/`): Audit log for observability. Records pipeline steps, state mutations, LLM calls, gateway requests. Not for inter-engine communication.

### Config System

- `terrarium.toml` — base config
- `terrarium.{env}.toml` — environment overrides (e.g., `terrarium.development.toml` uses `:memory:` DBs)
- `terrarium.local.toml` — git-ignored local overrides
- Root config schema: `config/schema.py` → `TerrariumConfig`. Each subsystem owns its own config model (SRP).

### LLM Router

All LLM calls go through the router (`llm/router.py`), which handles provider selection, retry, budget tracking, and fallback. Never call provider SDKs directly. Task-specific routing is configured in `[llm.routing.*]` sections of `terrarium.toml`. Supports: Google (native), Anthropic (native), OpenAI-compatible (OpenAI, Gemini, Ollama, vLLM), CLI providers (Codex, codex, gemini), ACP providers (bidirectional JSON-RPC).

## Key Conventions

- **All I/O is async.** Use `aiosqlite`, `httpx`, async SDK methods. Wrap sync libs with `asyncio.to_thread()`. A single blocking call degrades the entire event loop.
- **All value objects and events are frozen Pydantic models** (`model_config = ConfigDict(frozen=True)`).
- **Inter-module contracts use `typing.Protocol`** (runtime_checkable, structural). ABC is used only for `BaseEngine`.
- **Typed IDs everywhere** — `EntityId`, `ActorId`, `ServiceId`, `EventId`, `WorldId`, `RunId`, `PolicyId`, `ToolName`, `SnapshotId`, `ProfileVersion` are `NewType` wrappers in `core/types.py`. Never pass raw strings for domain identifiers.
- **No hardcoded values in engine code.** Thresholds, timeouts, limits, provider names come from TOML config.
- **No cross-engine imports.** `engines/policy/` must never import from `engines/state/`. Communication is through the bus and protocols only.
- **All state changes go through the State Engine's commit interface.** Direct mutation creates inconsistencies.
- **All external requests go through the Gateway.** MCP calls, HTTP requests, webhook deliveries — everything.
- **All LLM calls go through the LLM router.** Never call provider SDKs directly. The router handles provider selection, retry, budget tracking, and fallback.
- **Record everything in the ledger.** If it didn't produce a ledger entry, it didn't happen.
- **Use the persistence module for all database operations.** Never create standalone SQLite connections.
- **Tests use `pytest-asyncio` with `asyncio_mode = "auto"`** — no `@pytest.mark.asyncio` decorators needed.
- **Coverage threshold: 80%** (95% for critical paths: pipeline, bus, state engine).
- Shared test fixtures in `tests/conftest.py`: `mock_event_bus`, `mock_ledger`, `stub_state_engine`, `mock_llm_provider`, `make_action_context`, `make_world_event`.
- **Ruff** for linting/formatting: Python 3.12 target, 100-char line length, rules: E, F, I, N, W, UP.
- **Mypy** with strict mode enabled.
