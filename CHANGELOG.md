# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-04-24

Volnix's first stable library release — installable as
`pip install volnix==0.2.0`. New embedding guide at
[`docs/embedding_volnix.md`](docs/embedding_volnix.md) documents the
library contract for downstream consumers.

### Added — Session-scoped memory (cross-session isolation)

- **`MemoryRecord.session_id: SessionId | None`** — memory writes and
  recalls now scope to a platform `Session`. Two sessions against the
  same world cannot observe each other's memory; resumed sessions
  automatically recall their own earlier records. Session-less callers
  (tests, background consolidation, pre-0.2.0 code paths) see only
  `session_id IS NULL` rows — disjoint from any session's slice.
- **`MemoryEngineProtocol.remember` / `recall`** accept a
  `session_id: SessionId | None = None` kwarg; default `None` preserves
  pre-0.2.0 behavior.
- **Store surface** — `MemoryStoreProtocol.list_by_owner`,
  `.fts_search`, and `.prune_oldest_episodic` all accept `session_id`
  with NULL-safe predicates; ring-buffer caps enforced per
  `(owner_id, session_id)` slice.
- **Agency plumbing** — `_memory_hooks` helpers, `NPCActivator`
  forwarders, and `AgencyEngine._activate_with_tool_loop` all thread
  `session_id` end-to-end; when no session context exists, the flow
  is byte-identical to pre-0.2.0.
- **Ledger** — `MemoryWriteEntry` and `MemoryRecallEntry` carry
  `session_id`, populated through the ledger's existing session_id
  column.

### Added — Animator concurrency + event-volume controls

- **`AnimatorEngine.tick()` is serialized** by an internal
  `asyncio.Lock`. In dynamic mode the animator is driven from
  multiple concurrent sources (bus subscriber, background tick loop,
  SimulationRunner); prior to this release, concurrent ticks raced
  the state engine's commit transaction and produced
  `sqlite3.OperationalError: cannot start a transaction within a
  transaction`. Static mode keeps its lock-free early-return.
- **Activity-gated `_dynamic_tick_loop`** — the background tick
  fires only when a consumer event has landed since the last fired
  tick. Eliminates "zombie" events that previously fired for
  minutes after agents went quiet. Zero new config knobs.
- Combined with the `creativity_budget_per_tick` default flip, the
  measured organic-event rate drops ~6× (from ~502 to ~82 events per
  representative run).

### Added — Library-consumer documentation

- **[`docs/embedding_volnix.md`](docs/embedding_volnix.md)** — single
  canonical document for library consumers. Covers installation,
  stable API surface, session lifecycle, memory contract, animator
  dynamic-mode changes, and the "what's in flux" matrix.

### Changed — Schema migration (automatic, in-place)

- **Memory store schema v1 → v2** — `SQLiteMemoryStore.initialize()`
  detects v1 DBs and migrates in place: adds `session_id TEXT`
  column, replaces the two v1 owner-leading indexes with
  session-leading ones, bumps `memory_schema_version.version` to 2.
  Single transaction — a crash mid-migration leaves the DB at v1,
  retryable. Existing rows retain `session_id = NULL` and remain
  queryable via the session-less path.
- **`MemoryConfig.schema_version`** default 1 → 2. Validator accepts
  {1, 2} (regardless of `enabled`); any other value is rejected at
  config-load time.
- **`AnimatorConfig.creativity_budget_per_tick`** default 3 → 1.
  Worlds that want higher ambient event volume set the value
  explicitly in `animator_settings`.

### Changed — Record-ID generation (breaking)

- **`MemoryEngine._next_record_id()` now uses `uuid.uuid4()`.** The
  0.1.x seeded-RNG contract (D7-5: same seed + same remember
  sequence ⇒ same IDs) was incompatible with persistent memory under
  `reset_on_world_start=False`: re-serving the same world at the
  same seed reproduced the UUID sequence and collided against
  persisted rows. Live-validation finding, folded pre-release.
  Content hashes remain content-derived (unchanged).

### Deprecated

- **`MemoryConfig.reset_on_world_start`** — default flipped
  `True → False`. When explicitly `True`, only `session_id IS NULL`
  rows are truncated (session-scoped rows are never touched). A
  one-shot deprecation warning fires at engine init. **Removed in
  0.3.0.** Migrate by deleting the line from your `volnix.toml` (or
  setting it to `false`).

### Fixed

- **State engine transaction race** (pre-existing on main):
  concurrent `AnimatorEngine.tick()` invocations in dynamic mode
  flushed organic events through the pipeline in parallel, racing
  the state engine's commit transaction. Resolved by serializing
  `tick()` (see "Added — Animator concurrency" above).

### Verification

- 4,682 tests pass across 16 suites (full regression plus the 30+
  new tests added across this release — session scoping, uuid4
  record IDs, animator tick serialization, activity gate, creativity
  budget default).
- Three adversarial reviews (one per shipped commit) completed
  pre-release; every finding including Lows folded.
- Live validation against the `demo_support_escalation` world under
  `--behavior dynamic` with memory enabled: zero transaction errors,
  zero UNIQUE-constraint collisions, ~6× reduction in organic event
  volume, session-scoped rows survive `reset_on_world_start=True`
  while session-less rows are truncated.
- Phase 0 regression oracle byte-identical when memory is disabled.

### Breaking changes summary

| Change | Migration |
|---|---|
| `reset_on_world_start` default flipped to `False`; only truncates NULL-session rows when `True`; deprecated. | Delete the line from `volnix.toml` (or set `false`). Memory now isolates per-session; the flag's original purpose is obsolete. |
| `MemoryEngine._next_record_id()` uses `uuid.uuid4()` — no cross-run determinism by seed. | If you rely on deterministic record IDs, switch the anchor to `(session_id, content_hash)` — session seed + content hash are stable, record IDs are not. |
| `MemoryConfig.schema_version` default `1 → 2`; v1 DBs auto-migrate in place. | No action. Upgrade picks up migration on first `MemoryEngine._on_initialize`. |
| `AnimatorConfig.creativity_budget_per_tick` default `3 → 1`. | If you want legacy volume, set `animator_settings.creativity_budget_per_tick = 3` in your world YAML. |

## [0.1.9] - 2026-04-19

### Added — Phase 4B: Actor Memory Engine (11th Volnix engine)

- **MemoryEngine** — episodic + semantic records keyed by actor scope, gated by an in-engine permission check, backed by SQLite + FTS5. Opt-in via `memory.enabled=true`; disabled by default keeps every existing blueprint byte-identical (Phase 0 regression oracle passes 3×).
- **Protocol surface** (`MemoryEngineProtocol` in `volnix/core/protocols.py`): `remember`, `recall`, `consolidate`, `evict`, `hydrate`. Runtime-checkable.
- **Retrieval modes**: six query variants (`structured`, `temporal`, `semantic`, `importance`, `hybrid`, `graph`) dispatched via `MemoryQuery` tagged union. `graph` raises `NotImplementedError` pending Phase 4D.
- **Embedders**: `FTS5Embedder` (default, zero-dep, deterministic) + `SentenceTransformersEmbedder` (opt-in via `volnix[embeddings]` extras — `sentence-transformers>=2.2,<4.0`). Dense recall path implements cosine similarity with on-miss embedding-cache population.
- **Consolidation**: `Consolidator` drives episodic → semantic distillation via `LLMRouter.route` (budget + ledger integration automatic). Dedicated `asyncio.Semaphore` caps concurrent distill calls via `MemoryConfig.max_concurrent_distill`.
- **Tier-1 fixtures**: `load_tier1_fixtures` loads pack-authored YAML beliefs when `tier_mode="mixed"` + `tier1_fixtures_path` is set. Records immune from runtime trimming.
- **NPCActivator integration**: pre-activation recall injects `MemoryRecall` into the prompt (`## Memories you recall` section); post-activation implicit write persists a raw episodic record on every termination path. Wrapped in try/except — memory failures never block activation.
- **Cohort rotation seam**: `MemoryEngine.subscriptions = ["cohort.rotated"]` subscribes to Phase 4A's rotation bus event; demoted actors get `evict()` (real store trim to half the episodic cap) + optional `consolidate()` (`consolidation_triggers=["on_eviction"]`); promoted actors optionally get `hydrate()` (pre-warm embedding cache).
- **Ring-buffer enforcement**: `max_episodic_per_actor` / `max_semantic_per_actor` enforced synchronously in `SQLiteMemoryStore.insert` — tier-2 overflow drops oldest episodic or lowest-importance semantic. Tier-1 records exempt.
- **Determinism**: same seed + same event sequence → byte-identical record IDs + content hashes. Proven under concurrent writes via the seeded `random.Random` + asyncio/GIL serialization.
- **SimulationRunner integration**: runner now calls `agency.rotate_cohort(tick)` on `cohort.rotation_interval_ticks` cadence. Pre-4B, `rotate_cohort` had no production driver; this release makes the 4A × 4B seam live in `volnix serve` runs.
- **`try_promote` publishes CohortRotationEvent**: preempt-demote path now also notifies memory subscribers, not just scheduled rotations.
- **Six new ledger entry types**: `MemoryWriteEntry`, `MemoryRecallEntry`, `MemoryConsolidationEntry`, `MemoryEvictionEntry`, `MemoryHydrationEntry`, `MemoryAccessDeniedEntry`.
- **`volnix.toml` `[memory]` section**: 19 knobs, each with a documented consumer site — no dead fields.

### Changed

- `AgencyEngine.set_memory_engine(engine)` — new setter; idempotent replacement: stops the prior engine before overwriting so long-lived processes don't leak bus subscriptions.
- `AgencyEngine.rotate_cohort` — `await self.publish(...)` now wrapped in narrow `try/except (OSError, RuntimeError, ValueError)`; symmetric with the existing ledger-append guard.
- `NPCPromptBuilder.build` — new `recalled_memories` keyword; template adds `## Memories you recall` section (hidden when `None` or empty, preserving Phase 0 byte-identity).

### Verification

- 3,552 tests pass across 15 suites (actors, core, integration, blueprints, architecture, engines, packs, registry, ledger, bus, config, pipeline, validation, llm, simulation). Zero regressions against pre-4B.
- Phase 0 oracle byte-identical 3×.
- Ruff check + format clean.
- Two adversarial principal-engineer audits (4B-only + 4A × 4B integration) completed pre-release; 20+ findings all addressed across 7 follow-up cleanup commits before tagging.

## [0.1.8] - 2026-04-13

### Added

- **LLM cache observability**: `LLMUsage.cached_tokens` + `LLMCallEntry.cached_tokens` record per-provider prompt-cache hits across all three providers (Gemini `cached_content_token_count`, OpenAI `prompt_tokens_details.cached_tokens`, Anthropic `cache_read_input_tokens`).
- **Tool-result compaction** for long multi-turn activations: `volnix/llm/_history_compaction.py` elides older tool-result content while preserving `tool_call_id` pairing, keeping prompt size flat across iterations.
- `AgencyConfig.max_verbatim_tool_results` (default 3) and `AgencyConfig.max_tool_result_chars` (default 800).
- Per-agent LLM provider routing in game blueprints (cross-provider head-to-head, e.g. Claude vs. Gemini in the same contest).

### Changed

- **Game engine rewritten event-driven**: round-based `GameRunner` / `TurnManager` replaced by `GameOrchestrator` + `GameActivePolicy` + scorer strategy package (`BehavioralScorer`, `CompetitiveScorer`). No rounds, no turns — the orchestrator subscribes to committed game-tool events, scores each, and re-activates the next player. Blueprint `flow.type: event_driven` with `max_events` / `stalemate_timeout_seconds` / `max_wall_clock_seconds` / `all_budgets_exhausted` failsafes. Legacy `rounds` / `turn_protocol` / `between_rounds` keys are rejected at compile time.
- Agency multi-turn loop keeps the last N tool results verbatim and elides older ones — flat prompt growth across iterations.
- Dashboard decision-trace tab hardened (null safety, type fixes); richer post-mortem narrative.
- `supply_chain_disruption` and `negotiation_competition` blueprints rewritten against the event-driven schema.

### Fixed

- Multi-turn tool-loop dropped tool calls on certain provider message shapes — cross-provider pairing repair centralized in `volnix/llm/_tool_pairing.py`.
- `LLMUsage` accepts `None` for token fields (Gemini intermittently returns null counts) via pydantic `field_validator(mode="before")`.
- Pre-existing real-API test guarded behind `VOLNIX_RUN_REAL_API_TESTS`.
- Hollow decision trace when no mutations committed in a turn.

## [0.1.0] - 2026-04-03

### Added

- 10-engine architecture: State, Policy, Permission, Budget, World Responder, World Animator, Agency, Agent Adapter, Report Generator, Feedback
- World Compiler: natural language and YAML world definitions compiled into runnable simulations
- 7-step governance pipeline: permission, policy, budget, capability, responder, validation, commit
- CLI with 28 commands: create, run, serve, mcp, dashboard, blueprints, report, check, config, attach, detach, inspect, diff, and more
- REST API with 39 endpoints + WebSocket live event streaming
- MCP server for agent integration (stdio and HTTP transports)
- React dashboard for run observation, scorecards, deliverables, and comparison
- 10 verified service packs: Gmail, Slack, Zendesk, Stripe, GitHub, Google Calendar, Twitter, Reddit, Alpaca, Browser
- 15 official blueprints: customer support, incident response, open sandbox, market prediction, campaign brainstorm, climate research, feature prioritization, security assessment, support ticket triage, governance test, and 5 internal agent team templates
- Multi-provider LLM routing: Anthropic, OpenAI, Google Gemini, Ollama, CLI-based, ACP-based
- Reality dimensions: information quality, reliability, social friction, complexity, boundaries (with ideal/messy/hostile presets)
- Behavior modes: static, reactive, dynamic
- Internal agent simulation with collaborative communication, subscriptions, and deliverable synthesis
- Python SDK client for programmatic access
- Agent config integration: one-command attach for Claude Desktop, Cursor, Windsurf
- Config export for OpenAI, Anthropic, LangGraph, CrewAI, AutoGen formats
- Layered TOML configuration system with environment and local overrides
- SQLite async persistence with WAL mode
- Event bus for inter-engine communication
- Ledger for audit logging and observability
- Seeded reproducibility: same seed produces same world state
