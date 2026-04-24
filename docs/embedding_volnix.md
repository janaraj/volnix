# Embedding Volnix

**Audience:** Python library authors who want to bundle Volnix into a downstream product. This document is the contract the 0.2.0 release makes with you.

**This doc does NOT cover:**

- End-user onboarding / running the CLI: see [getting-started.md](getting-started.md).
- External-agent integration (MCP / OpenAI-compatible / ACP / raw HTTP): see [agent-integration.md](agent-integration.md).
- World authoring (blueprints, reality dimensions, behavior modes): see [creating-worlds.md](creating-worlds.md) and [blueprints-reference.md](blueprints-reference.md).

---

## Installation

```bash
pip install volnix==0.2.0
```

**Required:** Python 3.12 or newer.

**Optional extras:**

```bash
pip install "volnix[embeddings]==0.2.0"   # sentence-transformers for dense memory recall
```

The default install is zero-dep for memory (FTS5 BM25 via SQLite) and picks provider SDKs at import time — you only pay for what you use.

---

## Quickstart — embed Volnix in 30 lines

```python
import asyncio

from volnix import VolnixApp, VolnixConfig, SessionType


async def main() -> None:
    config = VolnixConfig()  # uses volnix.toml + environment defaults
    app = VolnixApp(config=config)
    await app.start()

    try:
        # Start a session against a compiled or blueprint-loaded world.
        # ``world_id`` comes from your world-compilation step; for a
        # minimal embed-only use-case, point this at an existing
        # compiled world under ``~/.volnix/data/worlds/``.
        session = await app._session_manager.start(
            world_id="world_abc123",
            session_type=SessionType.BOUNDED,
            seed=42,
            world_seed=42,
        )
        print(f"session started: {session.session_id}")

        # ... your orchestration: session.start_world_run, agent
        # activations, ledger queries, scorecards, etc. All of that
        # flows through the APIs documented in the "Stable surface"
        # section below.

        await app._session_manager.end(session.session_id)
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
```

**What this runs**, end-to-end:

1. `VolnixConfig()` resolves your `volnix.toml` + `volnix.{env}.toml` overlays + env vars.
2. `VolnixApp.start()` boots the 11 engines (state, policy, permission, budget, responder, animator, agency, adapter, reporter, feedback, memory) plus the session manager and gateway.
3. `SessionManager.start(...)` allocates a fresh `session_id` and wires its seed.
4. `SessionManager.end(...)` cleanly closes the session; memory records remain in the store, keyed on this `session_id`.
5. `VolnixApp.stop()` drains pending work and closes every database.

> **Note on `_session_manager`:** the leading underscore reflects that the attribute is an implementation detail today; a public accessor is likely to land in 0.3.0. For 0.2.0 it's the supported handle.

---

## Stable API surface (0.2.0)

Everything in this section is exported from `volnix/__init__.py` and is covered by the 0.2.x stability contract: signatures do not break across minor releases; new methods may be added.

### Entry points

| Symbol | Intent |
|---|---|
| `VolnixApp` | The composition root. Construct with a `VolnixConfig`; `await .start()` to boot, `await .stop()` to tear down. |
| `VolnixConfig` | Pydantic model covering simulation, persistence, LLM, memory, privacy, agency, reporter, pack search, session, and dashboard settings. |
| `ConfigBuilder` | Fluent builder if you want to override specific config sections programmatically rather than via `volnix.toml`. |
| `PackSearchPath` | Register additional service-pack directories beyond the bundled ones. |

```python
from volnix import VolnixApp, VolnixConfig, ConfigBuilder

# Direct construction
app = VolnixApp(config=VolnixConfig())

# Via builder
config = ConfigBuilder().with_memory_enabled(True).build()
app = VolnixApp(config=config)
```

### Sessions

| Symbol | Intent |
|---|---|
| `SessionManager` | Lifecycle API: `start`, `resume`, `pause`, `end`, `checkpoint`, `get_session`, `pin_slot`. |
| `Session` | Frozen Pydantic model; what `start()` returns and `get_session()` reads. |
| `SessionId` | `NewType("SessionId", str)`. Opaque handle. |
| `SessionType` | `BOUNDED` (one-shot) / `OPEN` (long-running) / `RESUMABLE` (cross-process revival). |
| `SessionStatus` | `ACTIVE` / `PAUSED` / `ENDED`. |
| `SessionStartedEvent`, `SessionPausedEvent`, `SessionResumedEvent`, `SessionEndedEvent` | Bus events published on each transition. |

See [Session lifecycle](#session-lifecycle) below for the contract details.

### Memory

| Symbol | Intent |
|---|---|
| `MemoryEngineProtocol` | The protocol you type-hint against. `remember`, `recall`, `consolidate`, `evict`, `hydrate`. All accept an optional `session_id` kwarg; see the [memory contract](#memory-contract). |
| `MemoryRecord` | Frozen record. Carries `session_id: SessionId \| None` — the 0.2.0 isolation key. |
| `MemoryWrite` | Input to `remember(...)`; does NOT carry `session_id` (it's a kwarg on the engine call). |
| `MemoryQuery` | Tagged union of query variants: `StructuredQuery`, `TemporalQuery`, `SemanticQuery`, `ImportanceQuery`, `HybridQuery`, `GraphQuery`. |
| `MemoryRecall` | What `recall(...)` returns. |
| `MemoryScope` | `"actor"` \| `"team"`. Team scope is plumbed but not exercised end-to-end in 0.2.0. |
| `MemoryRecordId` | Record-id newtype. |

### Actors and world state

| Symbol | Intent |
|---|---|
| `ActorDefinition` | What you register via `VolnixApp.register_actor`. |
| `ActorState` | Mutable per-actor snapshot. |
| `ActionEnvelope` | The envelope agents produce; all agent actions flow through this type. |
| `WorldEvent` | Committed events; carry `session_id` automatically when committed inside a session. |

### Observability

| Symbol | Intent |
|---|---|
| `LedgerEntry`, `LedgerQuery` | Query the append-only audit ledger. Every pipeline step, memory op, LLM call, and state mutation lands here. |
| `UnifiedTimeline`, `TimelineEvent`, `ObservationQuery` | Phase 4C observation surface — cross-engine event timeline. |
| `BehavioralSignature`, `ActorBehaviorTraits` | Extracted per-actor behavioral summary. |
| `TrajectoryPoint` | One point in a state-field's historical trajectory. |
| `intent_behavior_gap`, `load_bearing_personas`, `variant_delta` | Pre-built observation helpers. |

### Packs and characters

| Symbol | Intent |
|---|---|
| `ServicePack`, `ServiceProfile` | Subclass these to author a new pack; register via `PackRegistry`. |
| `PackRegistry`, `PackManifest` | Construct / register packs at composition time. |
| `CharacterDefinition`, `CharacterLoader` | Catalog-driven character library. |
| `resolve_extractor_hook` | Helper for plugging in a custom behavioral-trait extractor. |

### Privacy

| Symbol | Intent |
|---|---|
| `PrivacyConfig` | Nested under `VolnixConfig.privacy`. Controls ephemeral mode and ledger redaction. |
| `identity_redactor`, `resolve_ledger_redactor`, `LedgerRedactorError` | Hook surface for custom redaction. |

### Simulation runner

| Symbol | Intent |
|---|---|
| `SimulationRunner`, `SimulationRunnerConfig` | Full-fidelity runner; consumed by the CLI's `volnix serve` path. Embed it directly for headless batch runs. |
| `SimulationType`, `StopReason` | Enums describing the runner's shape and termination cause. |

### Errors

Public error hierarchy rooted at `VolnixError`:

`DuplicatePackError`, `IncompatiblePackError`, `PackManifestLoadError`, `PackManifestMismatchError`, `PackNotFoundError`, `ReplayJournalMismatch`, `ReplayProviderNotFound`, `SessionNotFoundError`, `TrajectoryFieldNotFound`.

Catch `VolnixError` at the boundary to be safe across subclass additions in minor releases.

### What's NOT exported

- `volnix.llm.providers.replay.ReplayLLMProvider` — auto-registered when both ledger and LLM router are wired; reach for the submodule import only if you're building a custom composition.
- Everything under `volnix._internal.*`.
- Concrete engine classes (`AgencyEngine`, `StateEngine`, `MemoryEngine`, etc.). Type-hint against the protocols; construct only via the composition root.

---

## Session lifecycle

Sessions are the unit of isolation in 0.2.0. A session is created against a `world_id`, carries its own seed, and scopes all memory writes and recalls.

```python
from volnix import SessionManager, SessionType

# Start
session = await session_manager.start(
    world_id=world_id,
    session_type=SessionType.RESUMABLE,   # or BOUNDED / OPEN
    seed=42,
    world_seed=42,
)

# Later — same session, same world, in a new process
resumed = await session_manager.resume(session.session_id, tick=100)

# Pause / checkpoint / end
await session_manager.pause(session.session_id, tick=50, note="overnight break")
await session_manager.checkpoint(session.session_id, tick=60)
await session_manager.end(session.session_id)
```

**Guarantees:**

- Every session_id is globally unique (`f"sess-{uuid.uuid4().hex[:12]}"`).
- The session's seed is persisted; resuming replays with the same seed.
- Two sessions against the same world CANNOT observe each other's memory. Memory rows carry `session_id` and the store filters NULL-safely on that column.
- Session-less callers (tests, background consolidation) see only `session_id IS NULL` rows — disjoint from any session's slice.

---

## Memory contract

### Isolation

```python
# Inside a session — isolated reads and writes
await memory_engine.remember(
    caller=actor_id,
    target_scope="actor",
    target_owner=str(actor_id),
    write=MemoryWrite(
        content="user asked about refunds",
        kind="episodic",
        importance=0.6,
        source="explicit",
    ),
    tick=current_tick,
    session_id=session.session_id,
)

recall = await memory_engine.recall(
    caller=actor_id,
    target_scope="actor",
    target_owner=str(actor_id),
    query=HybridQuery(semantic_text="refund policy", top_k=5),
    tick=current_tick,
    session_id=session.session_id,
)
```

**Pass `session_id=None`** (or omit the kwarg entirely) to hit the session-less slice — same behavior as pre-0.2.0. Mixing is not supported: a session caller sees only its session's rows, a session-less caller sees only NULL-session rows.

### Schema migration

Memory DBs at schema v1 (Volnix 0.1.x) auto-migrate to v2 on `MemoryEngine._on_initialize`. The migration is:

- `ALTER TABLE memory_records ADD COLUMN session_id TEXT` (metadata-only, no row rewrite).
- Drop v1 indexes, create session-leading v2 indexes.
- Bump `memory_schema_version.version` to 2.

All wrapped in a single transaction — a crash mid-migration leaves the DB at v1, retryable. Existing rows retain `session_id = NULL` and remain queryable via the session-less path.

### `reset_on_world_start` is deprecated

In 0.1.x, `MemoryConfig.reset_on_world_start=True` (the default) wiped the DB on every engine init. In 0.2.0:

- Default is now `False`.
- When explicitly `True`, only `session_id IS NULL` rows are truncated. Session-scoped rows are never touched by this flag.
- A one-shot deprecation warning fires at engine init.
- The field is **removed in 0.3.0**. Migrate by deleting the line from your `volnix.toml` (or setting it to `false`).

### Record IDs are `uuid.uuid4()`

Record IDs no longer derive from the engine's seed. The 0.1.x "same seed → same record IDs" contract (D7-5) was incompatible with persistent memory — re-running the same world produced collisions. 0.2.0 switches `_next_record_id()` to `uuid.uuid4()`, matching the Consolidator's existing approach. Same content across runs still produces the same `content_hash` (content-derived, unchanged).

---

## Animator in dynamic mode

Dynamic behavior runs the animator alongside your agents. 0.2.0 ships three changes that materially cut event volume and token spend:

### 1. `creativity_budget_per_tick` default = 1 (down from 3)

Live validation measured 3:1 amplification per tick was too noisy; most ticks produced three near-duplicate events. Default is now 1. Worlds that want higher ambient-event volume set it explicitly:

```yaml
# blueprints/my_world.yaml
animator_settings:
  creativity_budget_per_tick: 3   # opt back into legacy behavior
```

### 2. Activity-gated `_dynamic_tick_loop`

The background 60s tick loop now fires `tick()` only when a consumer (non-animator, non-system) committed event has landed since the last fired tick. If agents go quiet, the loop sleeps silently. Previously the loop fired indefinitely, producing "zombie" events for minutes after agents stopped.

No config to tune — the gate is zero-knob, activity-driven.

### 3. `AnimatorEngine.tick()` serialized

Concurrent callers (bus subscriber + background loop + SimulationRunner) would race and hit `sqlite3.OperationalError: cannot start a transaction within a transaction`. 0.2.0 wraps `tick()` in an internal `asyncio.Lock` so at most one tick runs at a time. Static mode keeps its lock-free early-return.

**Combined impact** in the measured support-escalation scenario: ~502 → ~82 organic events per run (~6× reduction).

---

## What's in flux (not guaranteed stable across 0.2.x)

| Surface | Status | When we'll revisit |
|---|---|---|
| LLM `use_case` attribution | `LLMCallEntry.use_case` lands empty for every call today; the field exists and the router has the kwarg, but the tracker doesn't populate it yet. | Small follow-up TNL; likely 0.2.1. |
| Organic-generator content diversity | Live validation showed the generator concentrating ~95% of output on three action types. | Prompt-engineering TNL; timing TBD. |
| Cohort-rotation session-scope threading | `MemoryEngine.consolidate` / `_on_cohort_rotated` operate on the `session_id IS NULL` slice only. Session-scoped episodic records accumulate indefinitely across cohort demotes. | When a consumer exercises cohort rotation with sessions. |
| Animator generator prompt + similarity scoring | Internal; will change as diversity work lands. | Same as above. |
| `VolnixApp._session_manager` underscore | The attribute is the supported handle today; public accessor likely in 0.3.0. | 0.3.0. |

These are listed not as warnings against use, but so library consumers know which parts to instrument carefully and which are safe to build directly on.

---

## Version compatibility

- **0.1.x → 0.2.0 (this release)**: breaking changes — `reset_on_world_start` default flip, `_next_record_id` no longer deterministic-by-seed, schema v1 → v2 auto-migration. If you were relying on deterministic record IDs across runs, the replacement is the session's seed + the `session_id` column — replay determinism is now session-scoped, not world-scoped.
- **0.2.0 → 0.2.x (patch releases)**: bug fixes only. No signature changes.
- **0.2.0 → 0.3.0 (next minor)**: `reset_on_world_start` field removed. `VolnixApp._session_manager` likely becomes a public property.
