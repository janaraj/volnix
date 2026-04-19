"""End-to-end integration tests for the memory stack (PMF Plan Phase 4B Step 12).

Pure test additions — no production-code changes. Proves that the
full memory stack (engine + store + consolidator + recall) holds
under concurrent load, is engine-level deterministic, scales to
many actors, and that consolidation's LLM call flows through the
standard ledger pipeline (G10).

Real ``MemoryEngine`` + real ``SQLiteMemoryStore`` + real seeded
RNG. No mocks on the path under test. Timing bounds are coarse
wall-clock checks — tight enough to catch pathological regressions
(lock leaks, accidental sync sleep), loose enough for flaky CI.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any, ClassVar

from volnix.core.memory_types import (
    HybridQuery,
    MemoryRecall,
    MemoryWrite,
)
from volnix.core.types import ActorId
from volnix.engines.memory.config import MemoryConfig
from volnix.engines.memory.consolidation import Consolidator
from volnix.engines.memory.embedder import FTS5Embedder
from volnix.engines.memory.engine import MemoryEngine
from volnix.engines.memory.recall import Recall
from volnix.engines.memory.store import SQLiteMemoryStore
from volnix.llm.config import LLMConfig, LLMProviderEntry
from volnix.llm.provider import LLMProvider
from volnix.llm.registry import ProviderRegistry
from volnix.llm.router import LLMRouter
from volnix.llm.tracker import UsageTracker
from volnix.llm.types import LLMRequest, LLMResponse, LLMUsage
from volnix.persistence.manager import create_database

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubLLMProvider(LLMProvider):
    """Canned-response LLM provider. Returns fixed usage so the
    budget-flow test can assert exact token counts downstream."""

    provider_name: ClassVar[str] = "stub"

    def __init__(self, *, content: str) -> None:
        self._content = content

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content=self._content,
            usage=LLMUsage(prompt_tokens=42, completion_tokens=17, cost_usd=0.0001),
            model="stub-model",
            provider=self.provider_name,
        )


def _make_router(provider: LLMProvider, tracker: UsageTracker | None = None) -> LLMRouter:
    config = LLMConfig(
        defaults=LLMProviderEntry(type="stub", default_model="stub-model"),
        providers={"stub": LLMProviderEntry(type="stub")},
        routing={},
        max_retries=0,
    )
    registry = ProviderRegistry()
    registry.register("stub", provider)
    return LLMRouter(config=config, registry=registry, tracker=tracker)


class _InMemLedger:
    """Real-ish ledger stand-in that captures appended entries. The
    Ledger protocol only requires ``append(entry) -> int``."""

    def __init__(self) -> None:
        self.entries: list[Any] = []

    async def append(self, entry: Any) -> int:
        self.entries.append(entry)
        return len(self.entries)


async def _make_engine(
    *,
    seed: int = 42,
    llm_router: LLMRouter | None = None,
    ledger: _InMemLedger | None = None,
    memory_config: MemoryConfig | None = None,
) -> tuple[MemoryEngine, SQLiteMemoryStore, Any]:
    """Build a fresh MemoryEngine with real in-memory store. Returns
    (engine, store, db) so the caller can close the db on teardown."""
    db = await create_database(":memory:", wal_mode=False)
    store = SQLiteMemoryStore(db)
    await store.initialize()
    embedder = FTS5Embedder()
    recall = Recall(store=store, embedder=embedder)
    # A Consolidator is required by MemoryEngine.__init__ even if we
    # don't call consolidate() in a given test — plumb a trivial stub
    # router when one isn't provided.
    if llm_router is None:
        llm_router = _make_router(_StubLLMProvider(content='{"facts": []}'))
    consolidator = Consolidator(
        store=store,
        llm_router=llm_router,
        use_case="memory_distill",
        episodic_window=50,
        prune_after_consolidation=True,
    )
    cfg = memory_config or MemoryConfig(enabled=True)
    engine = MemoryEngine(
        memory_config=cfg,
        store=store,
        embedder=embedder,
        recall=recall,
        consolidator=consolidator,
        seed=seed,
    )
    if ledger is not None:
        engine._ledger = ledger
    return engine, store, db


def _write(actor_id: str, content: str, tick: int = 0) -> dict:
    """Build kwargs for ``MemoryEngine.remember``. Actor is self-scope."""
    return {
        "caller": ActorId(actor_id),
        "target_scope": "actor",
        "target_owner": actor_id,
        "write": MemoryWrite(
            content=content,
            kind="episodic",
            importance=0.5,
            tags=[],
            source="explicit",
        ),
        "tick": tick,
    }


# ---------------------------------------------------------------------------
# 1. Concurrency — 50 concurrent writes (G13)
# ---------------------------------------------------------------------------


class TestEngineConcurrentWrites:
    """G13 — 50 concurrent ``remember`` calls must all land, produce
    distinct record IDs, and complete under a coarse wall-clock bound.
    """

    async def test_negative_fifty_concurrent_writes_no_loss(self) -> None:
        engine, store, db = await _make_engine()
        try:
            coros = [
                engine.remember(**_write(f"actor-{i % 10}", f"content-{i}")) for i in range(50)
            ]
            record_ids = await asyncio.gather(*coros)
            # No exceptions → no deadlock.
            assert len(record_ids) == 50
            # Every write landed: per-actor row counts sum to 50.
            total = 0
            for a in range(10):
                rows = await store.list_by_owner(f"actor-{a}", kind="episodic")
                total += len(rows)
            assert total == 50
        finally:
            await db.close()

    async def test_negative_fifty_concurrent_writes_distinct_record_ids(self) -> None:
        """D7-5 — seeded RNG under concurrent access must still produce
        distinct record_ids (asyncio + GIL serialize the getrandbits
        call; this test locks that guarantee)."""
        engine, store, db = await _make_engine()
        try:
            coros = [
                engine.remember(**_write(f"actor-{i % 10}", f"content-{i}")) for i in range(50)
            ]
            record_ids = await asyncio.gather(*coros)
            assert len(set(str(rid) for rid in record_ids)) == 50
        finally:
            await db.close()

    async def test_negative_fifty_concurrent_writes_completes_under_5s(self) -> None:
        """Coarse wall-clock guard against pathological regressions
        (lock leak, accidental sync sleep, unbounded retry)."""
        engine, _store, db = await _make_engine()
        try:
            start = time.monotonic()
            coros = [
                engine.remember(**_write(f"actor-{i % 10}", f"content-{i}")) for i in range(50)
            ]
            await asyncio.gather(*coros)
            duration = time.monotonic() - start
            assert duration < 5.0, f"50 concurrent writes took {duration:.2f}s"
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# 2. Interleaved reads + writes
# ---------------------------------------------------------------------------


class TestEngineInterleavedReadsWrites:
    """Recall must tolerate concurrent writes — no partial reads,
    no crashes, writes all land."""

    async def test_negative_recall_tolerates_concurrent_writes(self) -> None:
        engine, store, db = await _make_engine()
        try:
            # Seed: one record per actor so recall has something to return.
            for a in range(5):
                await engine.remember(**_write(f"actor-{a}", f"seed content {a}"))

            write_coros = [
                engine.remember(**_write(f"actor-{i % 5}", f"live-{i}")) for i in range(30)
            ]
            recall_coros = [
                engine.recall(
                    caller=ActorId(f"actor-{i % 5}"),
                    target_scope="actor",
                    target_owner=f"actor-{i % 5}",
                    query=HybridQuery(semantic_text="seed live", top_k=5),
                    tick=0,
                )
                for i in range(20)
            ]

            results = await asyncio.gather(*write_coros, *recall_coros)
            writes, recalls = results[:30], results[30:]
            # All writes landed.
            assert len(writes) == 30
            # All recalls returned MemoryRecall shape (no exceptions).
            for r in recalls:
                assert isinstance(r, MemoryRecall)
            # Total rows: 5 seed + 30 live = 35.
            total = 0
            for a in range(5):
                rows = await store.list_by_owner(f"actor-{a}", kind="episodic")
                total += len(rows)
            assert total == 35
        finally:
            await db.close()

    async def test_negative_interleaved_no_record_loss(self) -> None:
        """Fire 20 writes + 20 recalls simultaneously with no seed data;
        verify all 20 writes still land despite the recalls racing the
        writes on a partially-empty store."""
        engine, store, db = await _make_engine()
        try:
            write_coros = [engine.remember(**_write("actor-solo", f"msg-{i}")) for i in range(20)]
            recall_coros = [
                engine.recall(
                    caller=ActorId("actor-solo"),
                    target_scope="actor",
                    target_owner="actor-solo",
                    query=HybridQuery(semantic_text="msg", top_k=5),
                    tick=0,
                )
                for _ in range(20)
            ]
            await asyncio.gather(*write_coros, *recall_coros)
            rows = await store.list_by_owner("actor-solo", kind="episodic")
            assert len(rows) == 20
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# 3. Engine-level determinism (D7-5)
# ---------------------------------------------------------------------------


class TestEngineDeterminism:
    """Two fresh engines, same seed, identical ``remember`` sequence
    → identical record_ids + content_hashes. Engine-level guarantee
    beyond Step 3's store-metadata ordering lock."""

    async def _run_sequence(self, seed: int) -> list[tuple[str, str]]:
        engine, store, db = await _make_engine(seed=seed)
        try:
            rids = []
            for i in range(10):
                rid = await engine.remember(**_write(f"actor-{i % 3}", f"c-{i}", tick=i))
                rids.append(str(rid))
            # Also collect content hashes by listing back.
            pairs: list[tuple[str, str]] = []
            for rid in rids:
                for a in range(3):
                    rows = await store.list_by_owner(f"actor-{a}", kind="episodic")
                    for r in rows:
                        if str(r.record_id) == rid:
                            pairs.append((rid, r.content_hash))
            return pairs
        finally:
            await db.close()

    async def test_positive_two_runs_same_seed_identical_record_ids(self) -> None:
        a = await self._run_sequence(seed=42)
        b = await self._run_sequence(seed=42)
        assert [p[0] for p in a] == [p[0] for p in b]

    async def test_positive_two_runs_same_seed_identical_content_hashes(self) -> None:
        a = await self._run_sequence(seed=42)
        b = await self._run_sequence(seed=42)
        assert [p[1] for p in a] == [p[1] for p in b]

    async def test_negative_different_seeds_different_record_ids(self) -> None:
        """Different seed → different record_ids (seeded RNG is doing
        something, not returning a constant)."""
        a = await self._run_sequence(seed=42)
        b = await self._run_sequence(seed=9999)
        assert [p[0] for p in a] != [p[0] for p in b]


# ---------------------------------------------------------------------------
# 4. Scale — 50 actors × 20 writes × 5 recalls
# ---------------------------------------------------------------------------


class TestEngineScale:
    """D12-7: CI-fast scale run. 1,250 writes + 250 recalls in under
    10 seconds with no silent loss."""

    async def test_negative_50_actors_20_writes_5_recalls_no_loss(self) -> None:
        engine, store, db = await _make_engine()
        try:
            # 50 actors × 20 writes = 1000 writes.
            rng = random.Random(123)
            write_coros = []
            for a in range(50):
                for i in range(20):
                    write_coros.append(engine.remember(**_write(f"actor-{a}", f"c-{a}-{i}")))
            # Shuffle deterministically so writes don't all go for
            # the same actor in a row — better stress.
            rng.shuffle(write_coros)
            await asyncio.gather(*write_coros)

            # 50 actors × 5 recalls = 250 recalls.
            recall_coros = []
            for a in range(50):
                for _ in range(5):
                    recall_coros.append(
                        engine.recall(
                            caller=ActorId(f"actor-{a}"),
                            target_scope="actor",
                            target_owner=f"actor-{a}",
                            query=HybridQuery(semantic_text="c", top_k=5),
                            tick=0,
                        )
                    )
            results = await asyncio.gather(*recall_coros)
            assert all(isinstance(r, MemoryRecall) for r in results)
            # No loss — every actor has exactly 20 episodes.
            for a in range(50):
                rows = await store.list_by_owner(f"actor-{a}", kind="episodic")
                assert len(rows) == 20, f"actor-{a} has {len(rows)} (expected 20)"
        finally:
            await db.close()

    async def test_negative_scale_completes_under_10s(self) -> None:
        """Coarse guard on pathological slowdown. 10s is generous —
        real bug would be orders of magnitude over."""
        engine, _store, db = await _make_engine()
        try:
            start = time.monotonic()
            write_coros = [
                engine.remember(**_write(f"actor-{a}", f"c-{a}-{i}"))
                for a in range(50)
                for i in range(20)
            ]
            await asyncio.gather(*write_coros)
            duration = time.monotonic() - start
            assert duration < 10.0, f"scale writes took {duration:.2f}s"
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# 5. Consolidator LLM → ledger budget-flow (G10)
# ---------------------------------------------------------------------------


class TestConsolidatorLLMBudgetFlow:
    """G10 — Consolidation-driven LLM calls flow through the standard
    UsageTracker → Ledger pipeline. Both an ``LLMCallEntry`` (budget
    observability) and a ``MemoryConsolidationEntry`` (memory
    observability) land on the same ledger. Test uses the REAL
    LLMRouter + real UsageTracker; only the provider is stubbed."""

    async def test_positive_consolidation_writes_llm_call_entry_to_ledger(
        self,
    ) -> None:
        ledger = _InMemLedger()
        tracker = UsageTracker(ledger=ledger)
        provider = _StubLLMProvider(content=json.dumps({"facts": []}))
        router = _make_router(provider, tracker=tracker)

        engine, store, db = await _make_engine(llm_router=router, ledger=ledger)
        try:
            # Seed one episode so consolidate has something to read.
            await engine.remember(**_write("actor-X", "yesterday I bought coffee"))
            await engine.consolidate(ActorId("actor-X"), force=True, tick=1)
            # Assert LLMCallEntry present.
            llm_entries = [e for e in ledger.entries if type(e).__name__ == "LLMCallEntry"]
            assert len(llm_entries) >= 1
            assert llm_entries[0].provider == "stub"
            assert llm_entries[0].engine_name == "memory"
        finally:
            await db.close()

    async def test_positive_consolidation_writes_memory_consolidation_entry(
        self,
    ) -> None:
        ledger = _InMemLedger()
        tracker = UsageTracker(ledger=ledger)
        provider = _StubLLMProvider(content=json.dumps({"facts": []}))
        router = _make_router(provider, tracker=tracker)

        engine, _store, db = await _make_engine(llm_router=router, ledger=ledger)
        try:
            await engine.remember(**_write("actor-Y", "some episode"))
            await engine.consolidate(ActorId("actor-Y"), force=True, tick=1)
            mc_entries = [
                e for e in ledger.entries if type(e).__name__ == "MemoryConsolidationEntry"
            ]
            assert len(mc_entries) == 1
            assert str(mc_entries[0].actor_id) == "actor-Y"
        finally:
            await db.close()
