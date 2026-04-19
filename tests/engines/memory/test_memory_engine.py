"""Integration tests for MemoryEngine (Phase 4B Step 7).

Real components except the LLM provider, which is stubbed for
determinism. A recording ledger double captures every write so
tests assert shape + destination per Test Discipline #6
(observability is tested).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, ClassVar

import pytest

from volnix.core.memory_types import (
    ImportanceQuery,
    MemoryAccessDenied,
    MemoryWrite,
    SemanticQuery,
)
from volnix.core.protocols import MemoryEngineProtocol
from volnix.core.types import ActorId
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


@pytest.fixture
async def engine_bundle() -> AsyncIterator[tuple[MemoryEngine, _RecordingLedger, Any]]:
    """Real store + FTS5 embedder + Recall + Consolidator + stub LLM.
    Returns (engine, ledger_double, db) for teardown."""
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
        store=store,
        embedder=embedder,
        recall=recall,
        consolidator=consolidator,
        seed=42,
    )
    ledger = _RecordingLedger()
    engine._ledger = ledger
    try:
        yield engine, ledger, db
    finally:
        await db.close()


def _write(content: str, *, kind: str = "episodic", importance: float = 0.5) -> MemoryWrite:
    return MemoryWrite(content=content, kind=kind, importance=importance, source="explicit")


async def _fresh_engine_with_seed(seed: int) -> tuple[MemoryEngine, Any]:
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
        store=store,
        embedder=embedder,
        recall=recall,
        consolidator=consolidator,
        seed=seed,
    )
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

    async def test_remember_record_id_is_deterministic_for_seed(self) -> None:
        # D7-5: same seed + same call sequence → same IDs.
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
        assert a == b, f"non-deterministic IDs: {a} vs {b}"

    async def test_remember_different_seeds_produce_different_ids(self) -> None:
        # Control: change the seed → different IDs.
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


class TestHydrate:
    async def test_hydrate_writes_hydration_entry(self, engine_bundle) -> None:
        engine, ledger, _ = engine_bundle
        await engine.hydrate(ActorId("npc-1"))
        hydrations = ledger.of_type(MemoryHydrationEntry)
        assert len(hydrations) == 1
        assert hydrations[0].actor_id == ActorId("npc-1")


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

    async def test_on_start_noop_for_fts5(self, engine_bundle) -> None:
        # FTS5 embedder skips the warmup path.
        engine, _, _ = engine_bundle
        await engine._on_start()  # must not raise
