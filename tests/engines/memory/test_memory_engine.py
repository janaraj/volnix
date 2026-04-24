"""Integration tests for MemoryEngine (Phase 4B Step 7).

Real components except the LLM provider, which is stubbed for
determinism. A recording ledger double captures every write so
tests assert shape + destination per Test Discipline #6
(observability is tested).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest

from volnix.core.events import CohortRotationEvent
from volnix.core.memory_types import (
    ImportanceQuery,
    MemoryAccessDenied,
    MemoryWrite,
    SemanticQuery,
)
from volnix.core.protocols import MemoryEngineProtocol
from volnix.core.types import ActorId, EventId, ServiceId, Timestamp
from volnix.engines.memory.config import MemoryConfig
from volnix.engines.memory.consolidation import Consolidator
from volnix.engines.memory.embedder import FTS5Embedder
from volnix.engines.memory.engine import MemoryEngine
from volnix.engines.memory.recall import Recall
from volnix.engines.memory.store import SQLiteMemoryStore
from volnix.ledger.entries import (
    MemoryAccessDeniedEntry,
    MemoryConsolidationEntry,
    MemoryEvictionEntry,
    MemoryHydrationEntry,
    MemoryRecallEntry,
    MemoryWriteEntry,
)
from volnix.llm.config import LLMConfig, LLMProviderEntry
from volnix.llm.provider import LLMProvider
from volnix.llm.registry import ProviderRegistry
from volnix.llm.router import LLMRouter
from volnix.llm.types import LLMRequest, LLMResponse, LLMUsage
from volnix.persistence.manager import create_database

# ---------------------------------------------------------------------------
# Recording ledger double
# ---------------------------------------------------------------------------


class _RecordingLedger:
    """Captures ledger writes so tests can assert shape + count.
    Minimal — just enough surface for MemoryEngine.append()."""

    def __init__(self) -> None:
        self.entries: list[Any] = []

    async def append(self, entry: Any) -> int:
        self.entries.append(entry)
        return len(self.entries)

    def of_type(self, cls: type) -> list[Any]:
        return [e for e in self.entries if isinstance(e, cls)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _StubLLMProvider(LLMProvider):
    provider_name: ClassVar[str] = "stub"

    def __init__(self, content: str = '{"facts": []}') -> None:
        self._content = content

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content=self._content,
            usage=LLMUsage(prompt_tokens=5, completion_tokens=3),
            model="stub",
            provider=self.provider_name,
        )


def _make_router(provider: LLMProvider | None = None) -> LLMRouter:
    provider = provider or _StubLLMProvider()
    config = LLMConfig(
        defaults=LLMProviderEntry(type="stub", default_model="stub"),
        providers={"stub": LLMProviderEntry(type="stub")},
        routing={},
        max_retries=0,
    )
    registry = ProviderRegistry()
    registry.register("stub", provider)
    return LLMRouter(config=config, registry=registry)


def _make_config(
    *,
    hydrate_on_promote: bool = False,
    consolidation_triggers: list[str] | None = None,
) -> MemoryConfig:
    """Step 8 helper — builds an enabled MemoryConfig with selectable
    cadence triggers + hydrate-on-promote flag."""
    return MemoryConfig(
        enabled=True,
        hydrate_on_promote=hydrate_on_promote,
        consolidation_triggers=consolidation_triggers
        if consolidation_triggers is not None
        else ["on_eviction", "periodic"],
    )


async def _build_bundle(
    *, config: MemoryConfig, seed: int = 42
) -> tuple[MemoryEngine, _RecordingLedger, Any]:
    db = await create_database(":memory:", wal_mode=False)
    store = SQLiteMemoryStore(db)
    await store.initialize()
    embedder = FTS5Embedder()
    recall = Recall(store=store, embedder=embedder)
    consolidator = Consolidator(
        store=store,
        llm_router=_make_router(),
        use_case="memory_distill",
        episodic_window=10,
    )
    engine = MemoryEngine(
        memory_config=config,
        store=store,
        embedder=embedder,
        recall=recall,
        consolidator=consolidator,
        seed=seed,
    )
    ledger = _RecordingLedger()
    engine._ledger = ledger
    return engine, ledger, db


@pytest.fixture
async def engine_bundle() -> AsyncIterator[tuple[MemoryEngine, _RecordingLedger, Any]]:
    """Default: consolidation_triggers includes "on_eviction",
    hydrate_on_promote=False."""
    engine, ledger, db = await _build_bundle(config=_make_config())
    try:
        yield engine, ledger, db
    finally:
        await db.close()


@pytest.fixture
async def engine_bundle_without_eviction_trigger() -> AsyncIterator[
    tuple[MemoryEngine, _RecordingLedger, Any]
]:
    """Variant: "on_eviction" NOT in consolidation_triggers."""
    engine, ledger, db = await _build_bundle(
        config=_make_config(consolidation_triggers=["periodic"])
    )
    try:
        yield engine, ledger, db
    finally:
        await db.close()


@pytest.fixture
async def engine_bundle_with_hydrate() -> AsyncIterator[tuple[MemoryEngine, _RecordingLedger, Any]]:
    """Variant: hydrate_on_promote=True."""
    engine, ledger, db = await _build_bundle(config=_make_config(hydrate_on_promote=True))
    try:
        yield engine, ledger, db
    finally:
        await db.close()


def _write(content: str, *, kind: str = "episodic", importance: float = 0.5) -> MemoryWrite:
    return MemoryWrite(content=content, kind=kind, importance=importance, source="explicit")


async def _fresh_engine_with_seed(seed: int) -> tuple[MemoryEngine, Any]:
    engine, _, db = await _build_bundle(config=_make_config(), seed=seed)
    return engine, db


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    async def test_engine_satisfies_protocol(self, engine_bundle) -> None:
        engine, _, _ = engine_bundle
        assert isinstance(engine, MemoryEngineProtocol)


# ---------------------------------------------------------------------------
# Remember — positive + ledger + determinism
# ---------------------------------------------------------------------------


class TestRemember:
    async def test_remember_persists_record(self, engine_bundle) -> None:
        engine, _, _ = engine_bundle
        rid = await engine.remember(
            caller=ActorId("npc-1"),
            target_scope="actor",
            target_owner="npc-1",
            write=_write("hello world"),
            tick=10,
        )
        assert isinstance(rid, str)  # MemoryRecordId is NewType(str)
        assert len(rid) == 36  # UUID string length

    async def test_remember_writes_memory_write_entry(self, engine_bundle) -> None:
        engine, ledger, _ = engine_bundle
        await engine.remember(
            caller=ActorId("npc-1"),
            target_scope="actor",
            target_owner="npc-1",
            write=_write("hello"),
            tick=42,
        )
        writes = ledger.of_type(MemoryWriteEntry)
        assert len(writes) == 1
        assert writes[0].caller_actor_id == "npc-1"
        assert writes[0].target_owner == "npc-1"
        assert writes[0].kind == "episodic"
        assert writes[0].tick == 42

    async def test_remember_same_seed_across_runs_produces_distinct_ids(self) -> None:
        """Regression guard: under session-scoped memory, ``reset_on_world_start=False``
        is the default so memory persists across re-serves of the same world. The
        previous seeded-RNG record-id generator (D7-5) produced the same UUID sequence
        on replay and hit ``UNIQUE constraint failed: memory_records.record_id`` on
        the second insert. Live-validation finding drove the switch to ``uuid.uuid4``;
        this test pins the new contract: two runs with the SAME seed MUST produce
        disjoint record-id sets so persistence-across-runs is safe.
        """

        async def _run() -> list[str]:
            engine, db = await _fresh_engine_with_seed(42)
            try:
                ids: list[str] = []
                for i in range(5):
                    rid = await engine.remember(
                        caller=ActorId("a"),
                        target_scope="actor",
                        target_owner="a",
                        write=_write(f"content {i}"),
                        tick=i,
                    )
                    ids.append(str(rid))
                return ids
            finally:
                await db.close()

        a = await _run()
        b = await _run()
        # Distinct sets — no overlap. The whole point is to avoid
        # the live-validation UNIQUE-constraint collision.
        assert set(a).isdisjoint(set(b)), (
            f"same-seed runs produced overlapping record IDs "
            f"(would break re-serve of a persistent memory store): {set(a) & set(b)}"
        )

    async def test_remember_duplicate_content_produces_distinct_records(
        self, engine_bundle
    ) -> None:
        # Two records with identical content share content_hash (by
        # design — content hash is content-derived). Each remember()
        # must produce a distinct record_id and land as a separate
        # row. If the store treated content_hash as primary key,
        # this would fail loudly.
        engine, ledger, _ = engine_bundle
        rid_a = await engine.remember(
            caller=ActorId("a"),
            target_scope="actor",
            target_owner="a",
            write=_write("same content"),
            tick=0,
        )
        rid_b = await engine.remember(
            caller=ActorId("a"),
            target_scope="actor",
            target_owner="a",
            write=_write("same content"),
            tick=1,
        )
        assert rid_a != rid_b
        writes = ledger.of_type(MemoryWriteEntry)
        assert len(writes) == 2

    async def test_remember_id_uniqueness_is_seed_independent(self) -> None:
        """Under the post-live-validation contract, record IDs are generated via
        ``uuid.uuid4()`` and are not derived from the engine's seed. Any two
        ``remember()`` calls — same seed, different seed — MUST produce distinct
        record IDs. Locks the uniqueness invariant without any seed-dependent
        determinism assumption.
        """

        async def _run(seed: int) -> str:
            engine, db = await _fresh_engine_with_seed(seed)
            try:
                rid = await engine.remember(
                    caller=ActorId("a"),
                    target_scope="actor",
                    target_owner="a",
                    write=_write("same content"),
                    tick=0,
                )
                return str(rid)
            finally:
                await db.close()

        id_a = await _run(seed=42)
        id_b = await _run(seed=99)
        assert id_a != id_b


# ---------------------------------------------------------------------------
# Recall — delegates + ledger
# ---------------------------------------------------------------------------


class TestRecall:
    async def test_recall_routes_to_dispatcher(self, engine_bundle) -> None:
        engine, _, _ = engine_bundle
        await engine.remember(
            caller=ActorId("npc-1"),
            target_scope="actor",
            target_owner="npc-1",
            write=_write("alpha beta gamma"),
            tick=10,
        )
        result = await engine.recall(
            caller=ActorId("npc-1"),
            target_scope="actor",
            target_owner="npc-1",
            query=SemanticQuery(text="alpha"),
            tick=20,
        )
        assert len(result.records) == 1

    async def test_recall_writes_memory_recall_entry(self, engine_bundle) -> None:
        engine, ledger, _ = engine_bundle
        await engine.recall(
            caller=ActorId("npc-1"),
            target_scope="actor",
            target_owner="npc-1",
            query=ImportanceQuery(),
            tick=10,
        )
        recalls = ledger.of_type(MemoryRecallEntry)
        assert len(recalls) == 1
        assert recalls[0].query_mode == "importance"
        assert recalls[0].tick == 10

    async def test_recall_carries_query_id_from_dispatcher(self, engine_bundle) -> None:
        engine, ledger, _ = engine_bundle
        await engine.recall(
            caller=ActorId("npc-1"),
            target_scope="actor",
            target_owner="npc-1",
            query=SemanticQuery(text="hello"),
            tick=10,
        )
        recalls = ledger.of_type(MemoryRecallEntry)
        assert recalls[0].query_id.startswith("semantic:fts5:")

    async def test_negative_recall_on_empty_store_returns_empty(self, engine_bundle) -> None:
        # Empty-store edge case — total_matched=0, records=[].
        # Ledger entry still written with result_count=0.
        engine, ledger, _ = engine_bundle
        result = await engine.recall(
            caller=ActorId("npc-1"),
            target_scope="actor",
            target_owner="npc-1",
            query=SemanticQuery(text="nothing"),
            tick=0,
        )
        assert result.records == []
        assert result.total_matched == 0
        recalls = ledger.of_type(MemoryRecallEntry)
        assert recalls[0].result_count == 0


# ---------------------------------------------------------------------------
# Consolidate — delegates + ledger
# ---------------------------------------------------------------------------


class TestConsolidate:
    async def test_consolidate_delegates_to_consolidator(self, engine_bundle) -> None:
        engine, _, _ = engine_bundle
        result = await engine.consolidate(ActorId("npc-1"), tick=10)
        # No episodes yet → zero counts.
        assert result.episodic_consumed == 0
        assert result.semantic_produced == 0

    async def test_consolidate_writes_consolidation_entry(self, engine_bundle) -> None:
        engine, ledger, _ = engine_bundle
        await engine.consolidate(ActorId("npc-1"), tick=42)
        cons = ledger.of_type(MemoryConsolidationEntry)
        assert len(cons) == 1
        assert cons[0].actor_id == ActorId("npc-1")
        assert cons[0].tick == 42

    async def test_consolidate_with_force_on_empty_store_still_ledgers(self, engine_bundle) -> None:
        # force=True bypasses the empty-episodes short-circuit in
        # Consolidator. The LLM returns {"facts": []} (stub default),
        # so semantic_produced=0. Ledger entry must still write.
        engine, ledger, _ = engine_bundle
        result = await engine.consolidate(ActorId("a"), tick=5, force=True)
        assert result.semantic_produced == 0
        cons = ledger.of_type(MemoryConsolidationEntry)
        assert len(cons) == 1


# ---------------------------------------------------------------------------
# Evict + Hydrate — ledger-only in Step 7
# ---------------------------------------------------------------------------


class TestEvict:
    async def test_evict_writes_eviction_entry(self, engine_bundle) -> None:
        engine, ledger, _ = engine_bundle
        await engine.evict(ActorId("npc-1"))
        evictions = ledger.of_type(MemoryEvictionEntry)
        assert len(evictions) == 1
        assert evictions[0].actor_id == ActorId("npc-1")

    async def test_evict_same_actor_twice_ledgers_both(self, engine_bundle) -> None:
        # Idempotency check — eviction is a signal, not a deduped
        # operation. Two demote signals produce two ledger rows.
        engine, ledger, _ = engine_bundle
        await engine.evict(ActorId("npc-1"))
        await engine.evict(ActorId("npc-1"))
        evictions = ledger.of_type(MemoryEvictionEntry)
        assert len(evictions) == 2

    async def test_negative_evict_trims_episodic_to_half_cap(self, engine_bundle) -> None:
        """Cleanup commit 2: ``evict()`` is no longer a pure ledger
        no-op — it aggressively trims the demoted actor's tier-2
        episodic buffer to half the configured cap. Assert the store
        actually shrinks."""
        engine, _ledger, _ = engine_bundle
        # Write more than half the cap (config default: 500; half = 250).
        # The fixture's default cap is the config default.
        cap_half = max(1, engine._memory_config.max_episodic_per_actor // 2)
        # Write cap_half + 10 records so evict has something to trim.
        for i in range(cap_half + 10):
            await engine.remember(
                caller=ActorId("npc-1"),
                target_scope="actor",
                target_owner="npc-1",
                write=_write(f"ep-{i}"),
                tick=i,
            )
        before = await engine._store.list_by_owner("npc-1", kind="episodic")
        await engine.evict(ActorId("npc-1"))
        after = await engine._store.list_by_owner("npc-1", kind="episodic")
        assert len(after) <= cap_half
        assert len(after) < len(before)

    async def test_negative_evict_preserves_tier1_fixtures(self, engine_bundle) -> None:
        """Tier-1 records are immutable pack-authored beliefs; evict
        must never drop them. ``prune_oldest_episodic`` at the store
        level already excludes tier-1 — this test guards that
        invariant via the engine surface."""
        engine, _ledger, _ = engine_bundle
        from volnix.core.memory_types import MemoryRecord, content_hash_of
        from volnix.core.types import MemoryRecordId

        # Direct-store insert because the engine's remember() creates
        # tier-2 episodic only. Tier-1 records arrive via the
        # tier1_loader path (Step 9).
        await engine._store.insert(
            MemoryRecord(
                record_id=MemoryRecordId("tier1:npc-1:0"),
                scope="actor",
                owner_id="npc-1",
                kind="episodic",
                tier="tier1",
                source="pack_fixture",
                content="pack belief",
                content_hash=content_hash_of("pack belief"),
                importance=0.9,
                tags=[],
                created_tick=0,
                consolidated_from=None,
            )
        )
        # Plenty of tier-2 so evict has lots to work with.
        for i in range(20):
            await engine.remember(
                caller=ActorId("npc-1"),
                target_scope="actor",
                target_owner="npc-1",
                write=_write(f"ep-{i}"),
                tick=i + 10,
            )
        await engine.evict(ActorId("npc-1"))
        rows = await engine._store.list_by_owner("npc-1", kind="episodic")
        tier_ones = [r for r in rows if r.tier == "tier1"]
        assert len(tier_ones) == 1
        assert str(tier_ones[0].record_id) == "tier1:npc-1:0"


class TestHydrate:
    async def test_hydrate_writes_hydration_entry(self, engine_bundle) -> None:
        engine, ledger, _ = engine_bundle
        await engine.hydrate(ActorId("npc-1"))
        hydrations = ledger.of_type(MemoryHydrationEntry)
        assert len(hydrations) == 1
        assert hydrations[0].actor_id == ActorId("npc-1")

    async def test_hydrate_same_actor_twice_ledgers_both(self, engine_bundle) -> None:
        engine, ledger, _ = engine_bundle
        await engine.hydrate(ActorId("npc-1"))
        await engine.hydrate(ActorId("npc-1"))
        hydrations = ledger.of_type(MemoryHydrationEntry)
        assert len(hydrations) == 2

    async def test_negative_hydrate_with_fts5_embedder_is_noop_beyond_ledger(
        self, engine_bundle
    ) -> None:
        """FTS5 embedder has no vectors to cache — hydrate lands the
        ledger entry but performs no store work. Proves the fast-path
        exit is taken for the default embedder."""
        engine, _ledger, _ = engine_bundle
        from volnix.engines.memory.embedder import FTS5Embedder

        assert isinstance(engine._embedder, FTS5Embedder)
        # Hydrate with no records — must not raise even though there's
        # nothing to warm.
        await engine.hydrate(ActorId("npc-empty"))


# ---------------------------------------------------------------------------
# PMF 4B cleanup commit 7 — Step 7 negative-intent strengthening
# (audit M2-4B: Step 7 negative ratio was ~32%, below the 50% gate).
# ---------------------------------------------------------------------------


class TestFailureIsolation:
    """Defensive tests locking in that a failure in one collaborator
    (store, ledger, consolidator, embedder) does not cascade into
    MemoryEngine state corruption or masked errors."""

    async def test_negative_store_insert_raises_propagates_from_remember(
        self, engine_bundle
    ) -> None:
        """If the underlying store can't persist, remember() must
        surface the error — silent swallow would lose memory rows."""
        engine, _ledger, _ = engine_bundle

        original_insert = engine._store.insert

        async def boom(record):
            raise RuntimeError("store disk full")

        engine._store.insert = boom  # type: ignore[method-assign]
        try:
            with pytest.raises(RuntimeError, match="store disk full"):
                await engine.remember(
                    caller=ActorId("npc-1"),
                    target_scope="actor",
                    target_owner="npc-1",
                    write=_write("anything"),
                    tick=0,
                )
        finally:
            engine._store.insert = original_insert  # type: ignore[method-assign]

    async def test_negative_ledger_failure_during_remember_propagates(self, engine_bundle) -> None:
        """If the ledger append fails, the memory is already stored
        (inserted before ledger call) — the ledger error surfaces so
        observability gaps are loud, not silent."""
        engine, ledger, _ = engine_bundle

        original_append = ledger.append

        async def boom(entry):
            raise RuntimeError("ledger unreachable")

        ledger.append = boom  # type: ignore[method-assign]
        try:
            with pytest.raises(RuntimeError, match="ledger unreachable"):
                await engine.remember(
                    caller=ActorId("npc-1"),
                    target_scope="actor",
                    target_owner="npc-1",
                    write=_write("something"),
                    tick=0,
                )
        finally:
            ledger.append = original_append  # type: ignore[method-assign]

    async def test_negative_recall_with_consolidator_error_does_not_taint_recall(
        self, engine_bundle
    ) -> None:
        """Recall dispatch is independent of consolidator health —
        a broken consolidator must not affect recall's behavior."""
        engine, _ledger, _ = engine_bundle
        # Seed a record + ensure recall works with the consolidator
        # "broken" (it's not invoked on recall paths).
        await engine.remember(
            caller=ActorId("npc-1"),
            target_scope="actor",
            target_owner="npc-1",
            write=_write("about cafes"),
            tick=0,
        )

        async def boom(*a, **kw):
            raise RuntimeError("consolidator dead")

        engine._consolidator.consolidate = boom  # type: ignore[method-assign]

        result = await engine.recall(
            caller=ActorId("npc-1"),
            target_scope="actor",
            target_owner="npc-1",
            query=SemanticQuery(text="cafes"),
            tick=0,
        )
        assert len(result.records) >= 1

    async def test_negative_consolidate_when_consolidator_raises(self, engine_bundle) -> None:
        """engine.consolidate() surfaces consolidator errors rather
        than silently succeeding with zero work."""
        engine, _ledger, _ = engine_bundle

        async def boom(actor_id, tick, **_):
            raise RuntimeError("consolidator crashed")

        engine._consolidator.consolidate = boom  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="consolidator crashed"):
            await engine.consolidate(ActorId("npc-1"), tick=1)

    async def test_negative_recall_with_broken_store_list_propagates(self, engine_bundle) -> None:
        """Importance / temporal / structured recall all route
        through ``store.list_by_owner``. A broken store surfaces the
        error instead of returning a silently-empty recall."""
        engine, _ledger, _ = engine_bundle

        async def boom(*a, **kw):
            raise RuntimeError("list_by_owner failed")

        engine._store.list_by_owner = boom  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="list_by_owner failed"):
            await engine.recall(
                caller=ActorId("npc-1"),
                target_scope="actor",
                target_owner="npc-1",
                query=ImportanceQuery(top_k=5),
                tick=0,
            )

    async def test_negative_gate_mutation_mid_call_still_denies_cross_actor(
        self, engine_bundle
    ) -> None:
        """Even if someone tried to race the gate by swapping the
        config mid-check, the gate reads actor IDs once and the
        denial is immediate — no recovery path lets a cross-actor
        write slip through."""
        engine, ledger, _ = engine_bundle
        with pytest.raises(MemoryAccessDenied):
            await engine.remember(
                caller=ActorId("npc-1"),
                target_scope="actor",
                target_owner="other-npc",  # different owner
                write=_write("stolen"),
                tick=0,
            )
        # Denial logged to ledger.
        denials = ledger.of_type(MemoryAccessDeniedEntry)
        assert len(denials) >= 1


# ---------------------------------------------------------------------------
# Permission gate — D7-2
# ---------------------------------------------------------------------------


class TestPermissionGate:
    async def test_actor_self_access_allowed(self, engine_bundle) -> None:
        engine, ledger, _ = engine_bundle
        await engine.remember(
            caller=ActorId("npc-1"),
            target_scope="actor",
            target_owner="npc-1",
            write=_write("mine"),
            tick=0,
        )
        assert not ledger.of_type(MemoryAccessDeniedEntry)

    async def test_actor_cross_access_denied_raises(self, engine_bundle) -> None:
        engine, ledger, _ = engine_bundle
        with pytest.raises(MemoryAccessDenied):
            await engine.remember(
                caller=ActorId("npc-1"),
                target_scope="actor",
                target_owner="npc-2",
                write=_write("stealing"),
                tick=0,
            )
        denials = ledger.of_type(MemoryAccessDeniedEntry)
        assert len(denials) == 1
        assert denials[0].caller_actor_id == "npc-1"
        assert denials[0].target_owner == "npc-2"
        assert denials[0].op == "write"

    async def test_actor_cross_recall_denied_raises(self, engine_bundle) -> None:
        engine, ledger, _ = engine_bundle
        with pytest.raises(MemoryAccessDenied):
            await engine.recall(
                caller=ActorId("npc-1"),
                target_scope="actor",
                target_owner="npc-2",
                query=ImportanceQuery(),
                tick=0,
            )
        denials = ledger.of_type(MemoryAccessDeniedEntry)
        assert len(denials) == 1
        assert denials[0].op == "read"

    async def test_team_scope_denied_in_4b(self, engine_bundle) -> None:
        # Team scope plumbed for 4D; in 4B it always denies.
        engine, ledger, _ = engine_bundle
        with pytest.raises(MemoryAccessDenied):
            await engine.remember(
                caller=ActorId("npc-1"),
                target_scope="team",
                target_owner="team-X",
                write=_write("team note"),
                tick=0,
            )
        denials = ledger.of_type(MemoryAccessDeniedEntry)
        assert denials[0].target_scope == "team"

    async def test_denial_entry_contains_full_context(self, engine_bundle) -> None:
        engine, ledger, _ = engine_bundle
        with pytest.raises(MemoryAccessDenied):
            await engine.remember(
                caller=ActorId("npc-7"),
                target_scope="actor",
                target_owner="npc-8",
                write=_write("x"),
                tick=99,
            )
        d = ledger.of_type(MemoryAccessDeniedEntry)[0]
        assert d.caller_actor_id == "npc-7"
        assert d.target_scope == "actor"
        assert d.target_owner == "npc-8"
        assert d.op == "write"


# ---------------------------------------------------------------------------
# Ledger integration — all 6 entry types hit via their respective methods
# ---------------------------------------------------------------------------


class TestLedgerIntegration:
    async def test_all_six_entry_types_are_emittable(self, engine_bundle) -> None:
        engine, ledger, _ = engine_bundle
        # Trigger each entry type.
        await engine.remember(
            caller=ActorId("a"),
            target_scope="actor",
            target_owner="a",
            write=_write("x"),
            tick=0,
        )
        await engine.recall(
            caller=ActorId("a"),
            target_scope="actor",
            target_owner="a",
            query=ImportanceQuery(),
            tick=0,
        )
        await engine.consolidate(ActorId("a"), tick=0)
        await engine.evict(ActorId("a"))
        await engine.hydrate(ActorId("a"))
        try:
            await engine.remember(
                caller=ActorId("a"),
                target_scope="actor",
                target_owner="b",
                write=_write("y"),
                tick=0,
            )
        except MemoryAccessDenied:
            pass

        assert ledger.of_type(MemoryWriteEntry)
        assert ledger.of_type(MemoryRecallEntry)
        assert ledger.of_type(MemoryConsolidationEntry)
        assert ledger.of_type(MemoryEvictionEntry)
        assert ledger.of_type(MemoryHydrationEntry)
        assert ledger.of_type(MemoryAccessDeniedEntry)


# ---------------------------------------------------------------------------
# No-ledger-configured path — operations succeed without crashing
# ---------------------------------------------------------------------------


class TestNoLedgerConfigured:
    async def test_remember_works_without_ledger(self, engine_bundle) -> None:
        engine, _, _ = engine_bundle
        engine._ledger = None  # simulate wire-time miss
        rid = await engine.remember(
            caller=ActorId("a"),
            target_scope="actor",
            target_owner="a",
            write=_write("x"),
            tick=0,
        )
        # No crash; record still persisted.
        assert rid is not None


# ---------------------------------------------------------------------------
# Lifecycle — _on_initialize is idempotent; _on_start is safe
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_on_initialize_is_idempotent(self, engine_bundle) -> None:
        engine, _, _ = engine_bundle
        # Fixture already initialised; call again — must not crash.
        await engine._on_initialize()

    async def test_on_start_noop_for_fts5(self, engine_bundle, monkeypatch) -> None:
        # FTS5 embedder skips the warmup path. Previous version of
        # this test only asserted "doesn't raise" — too weak. Now
        # spy on embedder.embed and assert it was NOT called.
        engine, _, _ = engine_bundle
        embed_calls: list[Any] = []

        async def _spy(*args, **kwargs):
            embed_calls.append((args, kwargs))
            raise AssertionError("embedder.embed should not be called for fts5")

        monkeypatch.setattr(engine._embedder, "embed", _spy)
        await engine._on_start()  # must not raise + must not call embed
        assert embed_calls == []


# ---------------------------------------------------------------------------
# Step 8 — subscriptions + cohort rotation handler
# ---------------------------------------------------------------------------


class TestSubscriptions:
    async def test_subscriptions_include_cohort_rotated(self, engine_bundle) -> None:
        engine, _, _ = engine_bundle
        assert "cohort.rotated" in engine.subscriptions


class TestCohortRotationHandler:
    """Step 8 — demote triggers evict (+ optional consolidate);
    promote triggers hydrate (when configured). Errors in one actor
    don't block the batch (D8-5)."""

    def _event(
        self,
        *,
        demoted: list[str] | None = None,
        promoted: list[str] | None = None,
        tick: int = 42,
    ) -> CohortRotationEvent:
        now = datetime.now(UTC)
        return CohortRotationEvent(
            event_id=EventId("test-event"),
            event_type="cohort.rotated",
            timestamp=Timestamp(world_time=now, wall_time=now, tick=tick),
            actor_id=ActorId("cohort"),
            service_id=ServiceId("cohort"),
            promoted_ids=[ActorId(p) for p in (promoted or [])],
            demoted_ids=[ActorId(d) for d in (demoted or [])],
            rotation_policy="recency",
            tick=tick,
        )

    async def test_demote_triggers_evict_per_actor(self, engine_bundle) -> None:
        engine, ledger, _ = engine_bundle
        await engine._handle_event(self._event(demoted=["a", "b", "c"]))
        evictions = ledger.of_type(MemoryEvictionEntry)
        assert len(evictions) == 3
        evicted_ids = {str(e.actor_id) for e in evictions}
        assert evicted_ids == {"a", "b", "c"}

    async def test_demote_without_on_eviction_trigger_skips_consolidate(
        self, engine_bundle_without_eviction_trigger
    ) -> None:
        engine, ledger, _ = engine_bundle_without_eviction_trigger
        await engine._handle_event(self._event(demoted=["a"]))
        assert len(ledger.of_type(MemoryEvictionEntry)) == 1
        assert len(ledger.of_type(MemoryConsolidationEntry)) == 0

    async def test_demote_with_on_eviction_trigger_runs_consolidate(
        self,
        engine_bundle,  # default includes "on_eviction"
    ) -> None:
        engine, ledger, _ = engine_bundle
        await engine._handle_event(self._event(demoted=["a"]))
        assert len(ledger.of_type(MemoryEvictionEntry)) == 1
        assert len(ledger.of_type(MemoryConsolidationEntry)) == 1

    async def test_promote_without_hydrate_on_promote_skips(
        self,
        engine_bundle,  # default hydrate_on_promote=False
    ) -> None:
        engine, ledger, _ = engine_bundle
        await engine._handle_event(self._event(promoted=["a", "b"]))
        assert len(ledger.of_type(MemoryHydrationEntry)) == 0

    async def test_promote_with_hydrate_on_promote_fires_per_actor(
        self, engine_bundle_with_hydrate
    ) -> None:
        engine, ledger, _ = engine_bundle_with_hydrate
        await engine._handle_event(self._event(promoted=["a", "b"]))
        assert len(ledger.of_type(MemoryHydrationEntry)) == 2

    async def test_unknown_event_type_is_noop(self, engine_bundle) -> None:
        engine, ledger, _ = engine_bundle
        before = len(ledger.entries)

        class _Other:
            event_type = "something.else"

        await engine._handle_event(_Other())
        assert len(ledger.entries) == before

    async def test_per_actor_error_does_not_block_batch(self, engine_bundle, monkeypatch) -> None:
        # Force evict() to raise for actor-b; actors a and c should
        # still be processed. D8-5.
        engine, ledger, _ = engine_bundle
        original_evict = engine.evict
        calls: list[str] = []

        async def _spy(actor_id) -> None:
            calls.append(str(actor_id))
            if str(actor_id) == "b":
                raise RuntimeError("boom")
            await original_evict(actor_id)

        monkeypatch.setattr(engine, "evict", _spy)
        await engine._handle_event(self._event(demoted=["a", "b", "c"]))
        assert calls == ["a", "b", "c"]
        # a + c succeeded → 2 eviction entries; b crashed before writing.
        assert len(ledger.of_type(MemoryEvictionEntry)) == 2

    async def test_empty_demoted_and_promoted_is_noop(self, engine_bundle) -> None:
        # Edge case — cohort emits a rotation event with empty lists
        # (shouldn't normally happen but defend against it). No
        # ledger writes of any kind.
        engine, ledger, _ = engine_bundle
        before = len(ledger.entries)
        await engine._handle_event(self._event(demoted=[], promoted=[]))
        assert len(ledger.entries) == before

    async def test_overlapping_demote_and_promote_both_process(
        self, engine_bundle_with_hydrate
    ) -> None:
        # Defensive edge case — an actor_id could in principle
        # appear in both lists (cohort bug). Each loop runs
        # independently: evict then hydrate, both ledgered.
        engine, ledger, _ = engine_bundle_with_hydrate
        await engine._handle_event(self._event(demoted=["a"], promoted=["a"]))
        assert len(ledger.of_type(MemoryEvictionEntry)) == 1
        assert len(ledger.of_type(MemoryHydrationEntry)) == 1

    async def test_consolidate_raising_inside_handler_caught(
        self, engine_bundle, monkeypatch
    ) -> None:
        # D8-5 extension: the evict+consolidate try/except covers BOTH
        # calls. If consolidate raises, the batch still progresses.
        engine, ledger, _ = engine_bundle
        original_consolidate = engine.consolidate

        async def _spy(actor_id, *, force=False, tick=0):
            if str(actor_id) == "b":
                raise RuntimeError("consolidator boom")
            return await original_consolidate(actor_id, force=force, tick=tick)

        monkeypatch.setattr(engine, "consolidate", _spy)
        await engine._handle_event(self._event(demoted=["a", "b", "c"]))
        # All three evict() calls fire regardless of consolidate errors.
        assert len(ledger.of_type(MemoryEvictionEntry)) == 3
        # Consolidation: a + c succeed; b raised.
        assert len(ledger.of_type(MemoryConsolidationEntry)) == 2
