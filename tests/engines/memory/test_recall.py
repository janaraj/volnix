"""Unit tests for the Recall dispatcher (Phase 4B Step 5).

Uses real SQLiteMemoryStore + FTS5Embedder — no mocks on the path
under test (Test Discipline #3). Negative-case first per mode.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from volnix.core.memory_types import (
    GraphQuery,
    HybridQuery,
    ImportanceQuery,
    MemoryRecord,
    SemanticQuery,
    StructuredQuery,
    TemporalQuery,
    content_hash_of,
)
from volnix.core.types import MemoryRecordId
from volnix.engines.memory.embedder import FTS5Embedder
from volnix.engines.memory.recall import Recall
from volnix.engines.memory.store import SQLiteMemoryStore
from volnix.persistence.manager import create_database


def _rec(
    record_id: str,
    content: str,
    *,
    owner_id: str = "A",
    kind: str = "episodic",
    source: str = "explicit",
    tier: str = "tier2",
    importance: float = 0.5,
    tags: list[str] | None = None,
    created_tick: int = 0,
    consolidated_from: list[MemoryRecordId] | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        record_id=MemoryRecordId(record_id),
        scope="actor",
        owner_id=owner_id,
        kind=kind,  # type: ignore[arg-type]
        tier=tier,  # type: ignore[arg-type]
        source=source,  # type: ignore[arg-type]
        content=content,
        content_hash=content_hash_of(content),
        importance=importance,
        tags=tags or [],
        created_tick=created_tick,
        consolidated_from=consolidated_from,
    )


@pytest.fixture
async def recall() -> AsyncIterator[tuple[Recall, SQLiteMemoryStore]]:
    # N1 of the bug-bounty review: fixture used to yield ``db`` but
    # no test read it. Cleanup keeps the fixture signature minimal.
    db = await create_database(":memory:", wal_mode=False)
    store = SQLiteMemoryStore(db)
    await store.initialize()
    r = Recall(store=store, embedder=FTS5Embedder())
    try:
        yield r, store
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Dispatch entry point
# ---------------------------------------------------------------------------


class TestDispatchRouting:
    async def test_negative_unknown_mode_raises_value_error(self, recall) -> None:
        r, _ = recall

        class _FakeQuery:
            mode = "not_a_real_mode"

        with pytest.raises(ValueError, match="unknown MemoryQuery.mode"):
            await r.dispatch("A", _FakeQuery())  # type: ignore[arg-type]

    async def test_dispatches_structured(self, recall) -> None:
        r, store = recall
        sem = _rec(
            "s1",
            "pref evening",
            kind="semantic",
            source="consolidated",
            tags=["preference", "time"],
            consolidated_from=[MemoryRecordId("e1")],
        )
        await store.insert(sem)
        out = await r.dispatch("A", StructuredQuery(keys=["preference"]))
        assert [str(x.record_id) for x in out.records] == ["s1"]


# ---------------------------------------------------------------------------
# Structured
# ---------------------------------------------------------------------------


class TestStructured:
    async def test_empty_store_returns_empty(self, recall) -> None:
        r, _ = recall
        out = await r.dispatch("A", StructuredQuery(keys=["x"]))
        assert out.records == []
        assert out.total_matched == 0
        assert out.truncated is False

    async def test_only_semantic_records_returned(self, recall) -> None:
        r, store = recall
        # Episodic with matching tag must be IGNORED — structured
        # only sees semantic records.
        await store.insert(_rec("e1", "episodic event", tags=["preference"]))
        await store.insert(
            _rec(
                "s1",
                "semantic fact",
                kind="semantic",
                source="consolidated",
                tags=["preference"],
                consolidated_from=[MemoryRecordId("e1")],
            )
        )
        out = await r.dispatch("A", StructuredQuery(keys=["preference"]))
        assert [str(x.record_id) for x in out.records] == ["s1"]

    async def test_multi_key_and_semantics(self, recall) -> None:
        r, store = recall
        await store.insert(
            _rec(
                "s1",
                "food preference",
                kind="semantic",
                source="consolidated",
                tags=["preference", "food"],
            )
        )
        await store.insert(
            _rec(
                "s2",
                "time preference",
                kind="semantic",
                source="consolidated",
                tags=["preference", "time"],
            )
        )
        out = await r.dispatch("A", StructuredQuery(keys=["preference", "food"]))
        assert [str(x.record_id) for x in out.records] == ["s1"]

    async def test_sorted_by_importance_desc_with_record_id_tie_break(self, recall) -> None:
        r, store = recall
        # Same importance for z and a — record_id ASC breaks tie.
        await store.insert(
            _rec(
                "z",
                "same imp z",
                kind="semantic",
                source="consolidated",
                tags=["pref"],
                importance=0.5,
            )
        )
        await store.insert(
            _rec(
                "a",
                "same imp a",
                kind="semantic",
                source="consolidated",
                tags=["pref"],
                importance=0.5,
            )
        )
        await store.insert(
            _rec(
                "m",
                "higher imp",
                kind="semantic",
                source="consolidated",
                tags=["pref"],
                importance=0.9,
            )
        )
        out = await r.dispatch("A", StructuredQuery(keys=["pref"]))
        assert [str(x.record_id) for x in out.records] == ["m", "a", "z"]


# ---------------------------------------------------------------------------
# Temporal
# ---------------------------------------------------------------------------


class TestTemporal:
    async def test_empty_window_returns_empty(self, recall) -> None:
        r, store = recall
        await store.insert(_rec("r1", "content", created_tick=10))
        out = await r.dispatch("A", TemporalQuery(tick_start=100, tick_end=200))
        assert out.records == []

    async def test_open_ended_tick_end(self, recall) -> None:
        r, store = recall
        for i in range(5):
            await store.insert(_rec(f"r{i}", f"c{i}", created_tick=i))
        out = await r.dispatch("A", TemporalQuery(tick_start=2, tick_end=None))
        ids = [str(x.record_id) for x in out.records]
        assert ids == ["r4", "r3", "r2"]

    async def test_newest_first_with_record_id_tie_break(self, recall) -> None:
        r, store = recall
        # Same tick, expect record_id ASC as tie-break.
        await store.insert(_rec("z", "z", created_tick=10))
        await store.insert(_rec("a", "a", created_tick=10))
        await store.insert(_rec("m", "m", created_tick=20))
        out = await r.dispatch("A", TemporalQuery(tick_start=0))
        assert [str(x.record_id) for x in out.records] == ["m", "a", "z"]

    async def test_truncation_flag_and_total_matched(self, recall) -> None:
        r, store = recall
        for i in range(10):
            await store.insert(_rec(f"r{i}", f"c{i}", created_tick=i))
        out = await r.dispatch("A", TemporalQuery(tick_start=0, limit=3))
        assert len(out.records) == 3
        assert out.total_matched == 10
        assert out.truncated is True


# ---------------------------------------------------------------------------
# Semantic (FTS5 path)
# ---------------------------------------------------------------------------


class TestSemanticFts5:
    async def test_no_match_returns_empty(self, recall) -> None:
        r, store = recall
        await store.insert(_rec("r1", "alpha beta"))
        out = await r.dispatch("A", SemanticQuery(text="nonexistent"))
        assert out.records == []

    async def test_single_match(self, recall) -> None:
        r, store = recall
        await store.insert(_rec("r1", "alpha beta gamma"))
        out = await r.dispatch("A", SemanticQuery(text="alpha"))
        assert [str(x.record_id) for x in out.records] == ["r1"]

    async def test_top_k_truncation(self, recall) -> None:
        r, store = recall
        for i in range(5):
            await store.insert(_rec(f"r{i}", "shared term"))
        out = await r.dispatch("A", SemanticQuery(text="shared", top_k=2))
        assert len(out.records) == 2

    async def test_query_id_carries_content_hash_prefix(self, recall) -> None:
        r, store = recall
        await store.insert(_rec("r1", "hello world"))
        out = await r.dispatch("A", SemanticQuery(text="hello"))
        # query_id is deterministic for the same text (matches Recall
        # impl: f"semantic:fts5:{content_hash_of(q.text)[:8]}").
        assert out.query_id.startswith("semantic:fts5:")
        assert out.query_id == f"semantic:fts5:{content_hash_of('hello')[:8]}"

    async def test_negative_min_score_on_fts5_raises(self, recall) -> None:
        # C1 of the bug-bounty review: min_score on FTS5 was silently
        # ignored. Now it raises so callers surface the contract
        # mismatch instead of getting no-op behaviour.
        r, store = recall
        await store.insert(_rec("r1", "hello world"))
        with pytest.raises(ValueError, match="min_score"):
            await r.dispatch("A", SemanticQuery(text="hello", min_score=0.5))

    async def test_positive_min_score_zero_is_accepted(self, recall) -> None:
        # min_score = 0.0 (the default) must still work — only
        # non-zero values trigger the C1 guard.
        r, store = recall
        await store.insert(_rec("r1", "hello world"))
        out = await r.dispatch("A", SemanticQuery(text="hello", min_score=0.0))
        assert len(out.records) == 1


# ---------------------------------------------------------------------------
# Importance
# ---------------------------------------------------------------------------


class TestImportance:
    async def test_empty_store_returns_empty(self, recall) -> None:
        r, _ = recall
        out = await r.dispatch("A", ImportanceQuery(min_importance=0.5))
        assert out.records == []

    async def test_threshold_filter(self, recall) -> None:
        r, store = recall
        await store.insert(_rec("low", "low imp", importance=0.1))
        await store.insert(_rec("mid", "mid imp", importance=0.5))
        await store.insert(_rec("hi", "hi imp", importance=0.9))
        out = await r.dispatch("A", ImportanceQuery(min_importance=0.5, top_k=10))
        ids = [str(x.record_id) for x in out.records]
        assert ids == ["hi", "mid"]

    async def test_top_k_truncation_and_total_matched(self, recall) -> None:
        r, store = recall
        for i in range(5):
            await store.insert(_rec(f"r{i}", f"c{i}", importance=0.9))
        out = await r.dispatch("A", ImportanceQuery(top_k=2))
        assert len(out.records) == 2
        assert out.total_matched == 5
        assert out.truncated is True

    async def test_sort_importance_desc_record_id_tie_break(self, recall) -> None:
        r, store = recall
        await store.insert(_rec("z", "z", importance=0.5))
        await store.insert(_rec("a", "a", importance=0.5))
        await store.insert(_rec("m", "m", importance=0.9))
        out = await r.dispatch("A", ImportanceQuery(top_k=10))
        assert [str(x.record_id) for x in out.records] == ["m", "a", "z"]

    async def test_importance_exactly_zero_matches_min_zero(self, recall) -> None:
        # M2 of the Steps 1-5 bug-bounty review: boundary at 0.0.
        # ``Recall._importance`` uses ``>=``; a record with
        # ``importance=0.0`` must match a query with
        # ``min_importance=0.0``. Untested before; a regression to
        # ``>`` would pass CI silently without this guard.
        r, store = recall
        await store.insert(_rec("zero", "content", importance=0.0))
        await store.insert(_rec("pos", "content", importance=0.1))
        out = await r.dispatch("A", ImportanceQuery(min_importance=0.0, top_k=10))
        ids = [str(x.record_id) for x in out.records]
        assert "zero" in ids
        assert "pos" in ids


# ---------------------------------------------------------------------------
# Hybrid
# ---------------------------------------------------------------------------


class TestHybrid:
    async def test_empty_store_returns_empty(self, recall) -> None:
        r, _ = recall
        out = await r.dispatch("A", HybridQuery(semantic_text="anything"))
        assert out.records == []

    async def test_recency_dominates_when_weight_is_one(self, recall) -> None:
        # With recency_weight = 1.0 and others = 0, the newer record
        # with matching text must rank first.
        r, store = recall
        await store.insert(_rec("old", "matching text", created_tick=1))
        await store.insert(_rec("new", "matching text", created_tick=100))
        out = await r.dispatch(
            "A",
            HybridQuery(
                semantic_text="matching",
                semantic_weight=0.0,
                recency_weight=1.0,
                importance_weight=0.0,
                top_k=2,
            ),
            tick=100,
        )
        ids = [str(x.record_id) for x in out.records]
        assert ids[0] == "new"

    async def test_importance_dominates_when_weight_is_one(self, recall) -> None:
        r, store = recall
        await store.insert(_rec("lo", "matching text", importance=0.1))
        await store.insert(_rec("hi", "matching text", importance=0.9))
        out = await r.dispatch(
            "A",
            HybridQuery(
                semantic_text="matching",
                semantic_weight=0.0,
                recency_weight=0.0,
                importance_weight=1.0,
                top_k=2,
            ),
        )
        ids = [str(x.record_id) for x in out.records]
        assert ids[0] == "hi"

    async def test_sem_norm_handles_min_equals_max(self, recall) -> None:
        # When all FTS hits have the same bm25 score, the min==max
        # branch in _sem_norm must not divide by zero.
        r, store = recall
        for i in range(3):
            await store.insert(_rec(f"r{i}", "identical text", importance=i * 0.3))
        # Without crash, should return importance-dominated order.
        out = await r.dispatch(
            "A",
            HybridQuery(
                semantic_text="identical",
                semantic_weight=0.1,
                recency_weight=0.1,
                importance_weight=0.8,
                top_k=3,
            ),
        )
        ids = [str(x.record_id) for x in out.records]
        assert ids[0] == "r2"  # highest importance

    async def test_deterministic_tie_break_on_record_id(self, recall) -> None:
        # All signals identical — ties resolve on record_id ASC.
        r, store = recall
        await store.insert(_rec("z", "same text", importance=0.5, created_tick=5))
        await store.insert(_rec("a", "same text", importance=0.5, created_tick=5))
        out = await r.dispatch(
            "A",
            HybridQuery(semantic_text="same", top_k=2),
            tick=5,
        )
        ids = [str(x.record_id) for x in out.records]
        assert ids == sorted(ids)

    async def test_candidate_k_clamped_to_max_top_k(self, recall, monkeypatch) -> None:
        # C2 of the bug-bounty review: at upper ``top_k=1000``, naive
        # ``3 * top_k`` would ask the store for 3000 candidates,
        # bypassing the structural ``_MAX_TOP_K`` cap. The clamp
        # ensures the request never exceeds the cap. We observe the
        # clamp by capturing the ``top_k`` argument passed to
        # ``store.fts_search``.
        from volnix.core.memory_types import _MAX_TOP_K

        r, store = recall
        await store.insert(_rec("r1", "hello world"))
        captured: dict[str, int] = {}
        original = store.fts_search

        async def _spy(owner_id: str, query: str, top_k: int):
            captured["top_k"] = top_k
            return await original(owner_id, query, top_k)

        monkeypatch.setattr(store, "fts_search", _spy)
        await r.dispatch(
            "A",
            HybridQuery(semantic_text="hello", top_k=_MAX_TOP_K),
            tick=0,
        )
        assert captured["top_k"] == _MAX_TOP_K, (
            f"hybrid asked store for top_k={captured['top_k']}, "
            f"expected clamp at _MAX_TOP_K={_MAX_TOP_K}"
        )


# ---------------------------------------------------------------------------
# Graph (NotImplementedError)
# ---------------------------------------------------------------------------


class TestGraphRaises:
    async def test_raises_not_implemented_with_context(self, recall) -> None:
        r, _ = recall
        with pytest.raises(NotImplementedError, match="Phase 4D"):
            await r.dispatch("A", GraphQuery(entity="actor-42", depth=2))

    async def test_error_message_includes_entity_and_depth(self, recall) -> None:
        r, _ = recall
        try:
            await r.dispatch("A", GraphQuery(entity="my-entity", depth=3))
        except NotImplementedError as e:
            msg = str(e)
            assert "my-entity" in msg
            assert "3" in msg
            return
        raise AssertionError("expected NotImplementedError")


# ---------------------------------------------------------------------------
# Non-FTS5 embedder — Step-13 deferred paths
# ---------------------------------------------------------------------------


class _DenseStubEmbedder:
    """Stub with a non-fts5 provider_id — exercises the Step-13
    deferred code paths in semantic + hybrid."""

    @property
    def provider_id(self) -> str:
        return "sentence-transformers:stub"

    @property
    def dimensions(self) -> int:
        return 8

    async def embed(self, request: Any) -> Any:  # pragma: no cover — unused
        raise AssertionError("stub embedder.embed should not be called")


class TestDenseEmbedderDeferred:
    async def test_semantic_raises_with_step_13_message(self) -> None:
        db = await create_database(":memory:", wal_mode=False)
        store = SQLiteMemoryStore(db)
        await store.initialize()
        r = Recall(store=store, embedder=_DenseStubEmbedder())
        try:
            with pytest.raises(NotImplementedError, match="Step 13"):
                await r.dispatch("A", SemanticQuery(text="foo"))
        finally:
            await db.close()

    async def test_hybrid_raises_with_step_13_message(self) -> None:
        db = await create_database(":memory:", wal_mode=False)
        store = SQLiteMemoryStore(db)
        await store.initialize()
        r = Recall(store=store, embedder=_DenseStubEmbedder())
        try:
            with pytest.raises(NotImplementedError, match="Step 13"):
                await r.dispatch("A", HybridQuery(semantic_text="foo"))
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# Determinism across runs
# ---------------------------------------------------------------------------


class TestRecallDeterminism:
    async def test_two_runs_same_input_same_output(self) -> None:
        async def _run() -> list[str]:
            db = await create_database(":memory:", wal_mode=False)
            store = SQLiteMemoryStore(db)
            await store.initialize()
            r = Recall(store=store, embedder=FTS5Embedder())
            try:
                for i in range(5):
                    await store.insert(_rec(f"r{i}", f"alpha {i}", created_tick=i))
                out = await r.dispatch("A", SemanticQuery(text="alpha", top_k=5))
                return [str(x.record_id) for x in out.records]
            finally:
                await db.close()

        a = await _run()
        b = await _run()
        assert a == b
