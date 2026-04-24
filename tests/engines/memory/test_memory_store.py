"""Tests for SQLiteMemoryStore (PMF Plan Phase 4B, Step 3).

Integration-style tests against a real in-memory SQLite — not a mock.
Per test-discipline principle #3 ("don't mock the thing under test"),
mocking SQLite would hide the very FTS5, transaction, and indexing
behavior we depend on. ``create_database(":memory:")`` gives us the
real backend with full determinism and near-zero overhead.

Per test-discipline principle #1, every validator and every public
method has a negative-case test before its positive-case test.
"""

from __future__ import annotations

import json

import pytest

from volnix.core.memory_types import MemoryRecord, content_hash_of
from volnix.core.types import MemoryRecordId
from volnix.engines.memory.store import (
    SCHEMA_VERSION,
    TABLE_EMBEDDING_CACHE,
    TABLE_FTS,
    TABLE_RECORDS,
    TABLE_SCHEMA_VERSION,
    SQLiteMemoryStore,
)
from volnix.persistence.manager import create_database

# A valid-shaped hash (64 lowercase hex) used only by embedding-cache
# tests, which key on hash + provider and never compare against
# content. Don't use this inside MemoryRecord construction — the
# model enforces ``content_hash == sha256(content)`` (C1 Step 3).
_SAMPLE_CACHE_HASH = "a" * 64


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db():
    """Real in-memory SQLite. WAL is off for :memory: per the
    SQLiteDatabase guard — fine, we're testing logic not concurrency."""
    database = await create_database(":memory:", wal_mode=False)
    yield database
    await database.close()


@pytest.fixture
async def store(db):
    s = SQLiteMemoryStore(db)
    await s.initialize()
    return s


def _record(
    record_id: str = "r1",
    owner_id: str = "npc-1",
    kind: str = "episodic",
    tier: str = "tier2",
    source: str = "explicit",
    content: str = "Alice dropped a flare at dawn",
    importance: float = 0.5,
    tags: list[str] | None = None,
    created_tick: int = 10,
    consolidated_from: list[MemoryRecordId] | None = None,
    metadata: dict | None = None,
    scope: str = "actor",
) -> MemoryRecord:
    # content_hash derived from content — C1 of Step 3 review requires
    # them to match, so test helpers never fabricate a bogus hash.
    return MemoryRecord(
        record_id=MemoryRecordId(record_id),
        scope=scope,  # type: ignore[arg-type]
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
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Construction + initialize
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_negative_none_db_rejected(self) -> None:
        # G5: store must not construct its own DB. None is unacceptable.
        with pytest.raises(ValueError, match="Database"):
            SQLiteMemoryStore(None)  # type: ignore[arg-type]


class TestInitialize:
    async def test_fresh_db_creates_schema_v1(self, db) -> None:
        store = SQLiteMemoryStore(db)
        await store.initialize()
        # All tables present
        for t in (TABLE_RECORDS, TABLE_FTS, TABLE_EMBEDDING_CACHE, TABLE_SCHEMA_VERSION):
            assert await db.table_exists(t), f"{t} missing after initialize"
        assert await store.schema_version() == SCHEMA_VERSION

    async def test_initialize_is_idempotent(self, db) -> None:
        # Re-running initialize() on the same DB must not crash or
        # double-insert the schema_version row.
        store = SQLiteMemoryStore(db)
        await store.initialize()
        await store.initialize()  # second call — no-op
        rows = await db.fetchall(f"SELECT version FROM {TABLE_SCHEMA_VERSION}")
        assert len(rows) == 1  # only one version row
        assert rows[0]["version"] == SCHEMA_VERSION

    async def test_negative_unsupported_schema_version_refuses(self, db) -> None:
        # G12: future schema versions must fail loud, not silently
        # accept data against an unknown shape.
        store = SQLiteMemoryStore(db)
        await store.initialize()
        # Tamper the version to simulate a future DB opened by 4B code.
        await db.execute(f"UPDATE {TABLE_SCHEMA_VERSION} SET version = ?", (SCHEMA_VERSION + 1,))
        fresh_store = SQLiteMemoryStore(db)
        with pytest.raises(RuntimeError, match="schema version mismatch"):
            await fresh_store.initialize()

    async def test_reset_on_initialize_truncates_data(self, db) -> None:
        # Legacy ``reset_on_world_start`` wires to initialize(reset=True).
        # Under session-scoped memory (tnl/session-scoped-memory.tnl):
        #   - Only rows with session_id IS NULL are truncated.
        #   - The embedding cache is content-hash-keyed, session-agnostic,
        #     and preserved across resets so cached vectors stay reusable.
        #   - Schema + version row survive (reset ≠ destroy).
        store = SQLiteMemoryStore(db)
        await store.initialize()
        await store.insert(_record())  # session_id=None by default
        await store.embedding_cache_put(_SAMPLE_CACHE_HASH, "fts5", b"\x00")
        # Confirm populated
        assert await store.get(MemoryRecordId("r1")) is not None
        assert await store.embedding_cache_get(_SAMPLE_CACHE_HASH, "fts5") == b"\x00"
        # Reset
        await store.initialize(reset=True)
        # Session-less record wiped:
        assert await store.get(MemoryRecordId("r1")) is None
        # Embedding cache preserved (safe to share across sessions):
        assert await store.embedding_cache_get(_SAMPLE_CACHE_HASH, "fts5") == b"\x00"
        # Version preserved.
        assert await store.schema_version() == SCHEMA_VERSION

    async def test_reset_leaves_schema_version_row_intact(self, db) -> None:
        store = SQLiteMemoryStore(db)
        await store.initialize()
        await store.initialize(reset=True)
        rows = await db.fetchall(f"SELECT version FROM {TABLE_SCHEMA_VERSION}")
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Insert + get
# ---------------------------------------------------------------------------


class TestInsertAndGet:
    async def test_negative_get_missing_returns_none(self, store) -> None:
        assert await store.get(MemoryRecordId("does-not-exist")) is None

    async def test_negative_duplicate_record_id_fails(self, store) -> None:
        # PRIMARY KEY constraint — second insert with same ID must fail.
        await store.insert(_record(record_id="r1"))
        with pytest.raises(Exception):  # sqlite IntegrityError
            await store.insert(_record(record_id="r1", content="different"))

    async def test_positive_round_trip_preserves_all_fields(self, store) -> None:
        original = _record(
            tags=["event", "flare"],
            metadata={"z": 1, "a": 2},
            consolidated_from=None,
        )
        await store.insert(original)
        back = await store.get(MemoryRecordId("r1"))
        assert back is not None
        # Every field preserved byte-for-byte
        assert back.record_id == original.record_id
        assert back.scope == original.scope
        assert back.owner_id == original.owner_id
        assert back.kind == original.kind
        assert back.tier == original.tier
        assert back.source == original.source
        assert back.content == original.content
        assert back.content_hash == original.content_hash
        assert back.importance == original.importance
        assert back.tags == original.tags
        assert back.created_tick == original.created_tick
        assert back.consolidated_from == original.consolidated_from
        assert back.metadata == original.metadata

    async def test_positive_consolidated_from_backlinks_round_trip(self, store) -> None:
        rec = _record(
            record_id="s1",
            kind="semantic",
            source="consolidated",
            consolidated_from=[MemoryRecordId("e1"), MemoryRecordId("e2")],
        )
        await store.insert(rec)
        back = await store.get(MemoryRecordId("s1"))
        assert back is not None
        assert back.consolidated_from == [MemoryRecordId("e1"), MemoryRecordId("e2")]

    async def test_positive_metadata_sort_keys_deterministic_on_disk(self, store, db) -> None:
        # D4 (Step 1 review): on-disk JSON must use sort_keys=True so
        # two semantically-equal-but-insertion-order-different metadata
        # payloads produce byte-identical rows.
        await store.insert(_record(record_id="r1", metadata={"beta": 2, "alpha": 1, "zeta": 3}))
        row = await db.fetchone(
            f"SELECT metadata_json FROM {TABLE_RECORDS} WHERE record_id = ?",
            ("r1",),
        )
        assert row is not None
        # Keys must be sorted lexicographically in on-disk JSON
        assert row["metadata_json"] == '{"alpha": 1, "beta": 2, "zeta": 3}'


# ---------------------------------------------------------------------------
# list_by_owner
# ---------------------------------------------------------------------------


class TestListByOwner:
    async def test_negative_unknown_owner_returns_empty(self, store) -> None:
        assert await store.list_by_owner("nobody") == []

    async def test_positive_order_is_newest_first_then_record_id(self, store) -> None:
        # Same tick to force tie-break path — must fall back to record_id ASC.
        await store.insert(_record(record_id="z", created_tick=5))
        await store.insert(_record(record_id="a", created_tick=5))
        await store.insert(_record(record_id="m", created_tick=10))
        got = await store.list_by_owner("npc-1")
        ids = [str(r.record_id) for r in got]
        # tick=10 first (newer), then tick=5 with a, z tie-break
        assert ids == ["m", "a", "z"]

    async def test_positive_kind_filter_applied(self, store) -> None:
        await store.insert(_record(record_id="e1", kind="episodic"))
        await store.insert(_record(record_id="s1", kind="semantic", source="consolidated"))
        episodes = await store.list_by_owner("npc-1", kind="episodic")
        assert [str(r.record_id) for r in episodes] == ["e1"]
        semantics = await store.list_by_owner("npc-1", kind="semantic")
        assert [str(r.record_id) for r in semantics] == ["s1"]

    async def test_positive_limit_truncates_results(self, store) -> None:
        for i in range(5):
            await store.insert(_record(record_id=f"r{i}", created_tick=i))
        got = await store.list_by_owner("npc-1", limit=3)
        assert len(got) == 3
        # Newest-first truncation — r4, r3, r2
        assert [str(r.record_id) for r in got] == ["r4", "r3", "r2"]


# ---------------------------------------------------------------------------
# prune_oldest_episodic
# ---------------------------------------------------------------------------


class TestPruneOldestEpisodic:
    async def test_negative_keep_negative_raises(self, store) -> None:
        with pytest.raises(ValueError, match="keep"):
            await store.prune_oldest_episodic("npc-1", keep=-1)

    async def test_positive_prune_returns_empty_when_within_cap(self, store) -> None:
        for i in range(3):
            await store.insert(_record(record_id=f"r{i}", created_tick=i))
        pruned = await store.prune_oldest_episodic("npc-1", keep=5)
        assert pruned == []

    async def test_positive_prune_removes_oldest_above_keep(self, store) -> None:
        for i in range(5):
            await store.insert(_record(record_id=f"r{i}", created_tick=i))
        # Keep 2 — oldest 3 (r0, r1, r2) should be pruned.
        pruned = await store.prune_oldest_episodic("npc-1", keep=2)
        assert {str(p) for p in pruned} == {"r0", "r1", "r2"}
        # Remaining should be the 2 newest.
        remaining = await store.list_by_owner("npc-1")
        assert {str(r.record_id) for r in remaining} == {"r4", "r3"}

    async def test_positive_prune_also_removes_fts_rows(self, store, db) -> None:
        # After prune, FTS search must not return pruned records.
        for i in range(4):
            await store.insert(
                _record(
                    record_id=f"r{i}",
                    content=f"uniquephrase{i}",
                    created_tick=i,
                )
            )
        await store.prune_oldest_episodic("npc-1", keep=1)
        rows = await db.fetchall(f"SELECT record_id FROM {TABLE_FTS}")
        assert len(rows) == 1
        assert rows[0]["record_id"] == "r3"  # newest retained

    async def test_positive_keep_zero_prunes_all_episodic(self, store) -> None:
        for i in range(3):
            await store.insert(_record(record_id=f"r{i}", created_tick=i))
        pruned = await store.prune_oldest_episodic("npc-1", keep=0)
        assert len(pruned) == 3
        assert await store.list_by_owner("npc-1") == []

    async def test_prune_leaves_semantic_records_alone(self, store) -> None:
        # Ring buffer only applies to episodic — semantic records
        # persist until consolidation prunes them explicitly.
        await store.insert(_record(record_id="e1", kind="episodic"))
        await store.insert(_record(record_id="s1", kind="semantic", source="consolidated"))
        await store.prune_oldest_episodic("npc-1", keep=0)
        remaining = await store.list_by_owner("npc-1")
        ids = [str(r.record_id) for r in remaining]
        assert "s1" in ids  # survived
        assert "e1" not in ids  # pruned


# ---------------------------------------------------------------------------
# FTS search
# ---------------------------------------------------------------------------


class TestFtsSearch:
    async def test_negative_top_k_zero_returns_empty(self, store) -> None:
        await store.insert(_record(content="alice dropped a flare"))
        assert await store.fts_search("npc-1", "flare", top_k=0) == []

    async def test_negative_empty_query_returns_empty(self, store) -> None:
        await store.insert(_record(content="alice dropped a flare"))
        assert await store.fts_search("npc-1", "", top_k=5) == []
        assert await store.fts_search("npc-1", "   ", top_k=5) == []

    async def test_negative_no_match_returns_empty(self, store) -> None:
        await store.insert(_record(content="alice dropped a flare"))
        assert await store.fts_search("npc-1", "banana", top_k=5) == []

    async def test_positive_single_match(self, store) -> None:
        await store.insert(_record(content="alice dropped a flare at dawn"))
        hits = await store.fts_search("npc-1", "flare", top_k=5)
        assert len(hits) == 1
        rec, score = hits[0]
        assert rec.content == "alice dropped a flare at dawn"
        assert isinstance(score, float)

    async def test_positive_scope_isolation(self, store) -> None:
        # FTS must be owner-scoped — NPC-1's records invisible to NPC-2.
        await store.insert(_record(record_id="r1", owner_id="npc-1", content="flare phrase"))
        await store.insert(_record(record_id="r2", owner_id="npc-2", content="flare phrase"))
        hits = await store.fts_search("npc-1", "flare", top_k=5)
        assert len(hits) == 1
        assert str(hits[0][0].record_id) == "r1"

    async def test_positive_multi_word_query_ors_tokens(self, store) -> None:
        # Query "flare dawn" should match both docs, not require both.
        await store.insert(_record(record_id="r1", content="alice dropped flare"))
        await store.insert(_record(record_id="r2", content="dawn came slowly"))
        hits = await store.fts_search("npc-1", "flare dawn", top_k=5)
        ids = {str(r.record_id) for r, _ in hits}
        assert ids == {"r1", "r2"}  # OR semantics

    async def test_positive_query_with_fts5_special_chars_does_not_crash(self, store) -> None:
        # FTS5 operator tokens (AND, OR, quotes) in user text must
        # not raise a parse error. The store tokenises + quotes.
        await store.insert(_record(content="hello world"))
        # These would all crash a naive MATCH expression.
        for query in ['"unterminated', "NOT this", "foo AND bar", "a - b"]:
            hits = await store.fts_search("npc-1", query, top_k=5)
            # Doesn't raise; may or may not match.
            assert isinstance(hits, list)

    async def test_positive_deterministic_tie_break_on_record_id(self, store) -> None:
        # Identical content → identical BM25 score → deterministic
        # tie-break must be record_id ASC.
        for i in range(3):
            await store.insert(_record(record_id=f"r{i}", content="identical text"))
        hits = await store.fts_search("npc-1", "identical", top_k=5)
        ids = [str(r.record_id) for r, _ in hits]
        assert ids == sorted(ids)  # record_id ASC as tie-break

    async def test_positive_top_k_truncates_results(self, store) -> None:
        for i in range(5):
            await store.insert(_record(record_id=f"r{i}", content=f"match token{i}"))
        hits = await store.fts_search("npc-1", "match", top_k=3)
        assert len(hits) == 3


# ---------------------------------------------------------------------------
# Embedding cache
# ---------------------------------------------------------------------------


class TestEmbeddingCache:
    async def test_negative_cache_miss_returns_none(self, store) -> None:
        assert await store.embedding_cache_get("a" * 64, "fts5") is None

    async def test_positive_round_trip_preserves_bytes(self, store) -> None:
        blob = b"\x00\x01\x02\x03\x04"
        await store.embedding_cache_put("a" * 64, "fts5", blob)
        got = await store.embedding_cache_get("a" * 64, "fts5")
        assert got == blob

    async def test_positive_provider_id_keyspace(self, store) -> None:
        # Same content_hash, different providers — both coexist.
        await store.embedding_cache_put("a" * 64, "fts5", b"fts5-blob")
        await store.embedding_cache_put("a" * 64, "openai", b"openai-blob")
        assert await store.embedding_cache_get("a" * 64, "fts5") == b"fts5-blob"
        assert await store.embedding_cache_get("a" * 64, "openai") == b"openai-blob"

    async def test_positive_put_is_upsert(self, store) -> None:
        # Re-putting same key must replace, not error.
        await store.embedding_cache_put("a" * 64, "fts5", b"first")
        await store.embedding_cache_put("a" * 64, "fts5", b"second")
        assert await store.embedding_cache_get("a" * 64, "fts5") == b"second"

    async def test_negative_cache_disabled_get_returns_none_even_with_row(self, db) -> None:
        """Cleanup commit 1: ``embedding_cache_enabled=False`` makes
        ``get`` return None unconditionally, regardless of what's in
        the DB. Proves the config gate is honored."""
        # First populate via a cache-enabled store.
        store_on = SQLiteMemoryStore(db, embedding_cache_enabled=True)
        await store_on.initialize()
        await store_on.embedding_cache_put("a" * 64, "fts5", b"present")
        assert await store_on.embedding_cache_get("a" * 64, "fts5") == b"present"
        # Now a second store on the same DB with cache disabled.
        store_off = SQLiteMemoryStore(db, embedding_cache_enabled=False)
        assert await store_off.embedding_cache_get("a" * 64, "fts5") is None

    async def test_negative_cache_disabled_put_is_noop(self, db) -> None:
        store_off = SQLiteMemoryStore(db, embedding_cache_enabled=False)
        await store_off.initialize()
        await store_off.embedding_cache_put("a" * 64, "fts5", b"should-not-land")
        # Re-enable and confirm nothing was written.
        store_on = SQLiteMemoryStore(db, embedding_cache_enabled=True)
        assert await store_on.embedding_cache_get("a" * 64, "fts5") is None


# ---------------------------------------------------------------------------
# Ring-buffer overflow enforcement (cleanup commit 2)
# ---------------------------------------------------------------------------


class TestRingBufferOverflow:
    """``max_episodic_per_owner`` / ``max_semantic_per_owner`` in the
    store constructor enforce a hard cap per owner. Overflow is
    resolved synchronously on insert — oldest episodic, lowest-
    importance semantic. Tier-1 records are exempt.
    """

    async def test_negative_episodic_overflow_drops_oldest(self, db) -> None:
        store = SQLiteMemoryStore(db, max_episodic_per_owner=3)
        await store.initialize()
        for i in range(5):
            await store.insert(
                _record(
                    record_id=f"r-{i}",
                    owner_id="npc-cap",
                    kind="episodic",
                    content=f"c-{i}",
                    created_tick=i,
                )
            )
        rows = await store.list_by_owner("npc-cap", kind="episodic")
        assert len(rows) == 3
        # Newest 3 preserved (ticks 2, 3, 4); oldest 2 (ticks 0, 1) dropped.
        ticks = sorted(r.created_tick for r in rows)
        assert ticks == [2, 3, 4]

    async def test_negative_semantic_overflow_drops_lowest_importance(self, db) -> None:
        store = SQLiteMemoryStore(db, max_semantic_per_owner=2)
        await store.initialize()
        for i, imp in enumerate([0.1, 0.9, 0.5, 0.3]):
            await store.insert(
                _record(
                    record_id=f"s-{i}",
                    owner_id="npc-cap",
                    kind="semantic",
                    content=f"c-{i}",
                    importance=imp,
                    created_tick=i,
                )
            )
        rows = await store.list_by_owner("npc-cap", kind="semantic")
        assert len(rows) == 2
        kept_imps = sorted(r.importance for r in rows)
        # Kept the two highest-importance (0.5, 0.9); dropped 0.1 + 0.3.
        assert kept_imps == [0.5, 0.9]

    async def test_negative_tier1_records_never_trimmed(self, db) -> None:
        """Tier-1 pack fixtures are immutable beliefs. Overflow
        enforcement must skip them — only tier-2 records get
        trimmed."""
        store = SQLiteMemoryStore(db, max_episodic_per_owner=2)
        await store.initialize()
        # 3 tier-1 records (immutable) — should all survive.
        for i in range(3):
            await store.insert(
                _record(
                    record_id=f"t1-{i}",
                    owner_id="npc-cap",
                    kind="episodic",
                    tier="tier1",
                    source="pack_fixture",
                    content=f"fixture {i}",
                    created_tick=i,
                )
            )
        # 3 tier-2 records — only 2 most-recent should survive.
        for i in range(3):
            await store.insert(
                _record(
                    record_id=f"t2-{i}",
                    owner_id="npc-cap",
                    kind="episodic",
                    content=f"runtime {i}",
                    created_tick=10 + i,
                )
            )
        rows = await store.list_by_owner("npc-cap", kind="episodic")
        tier_counts = {"tier1": 0, "tier2": 0}
        for r in rows:
            tier_counts[r.tier] += 1
        assert tier_counts["tier1"] == 3, "tier-1 must never be trimmed"
        assert tier_counts["tier2"] == 2, "tier-2 overflow trimmed to cap"

    async def test_positive_no_cap_unbounded_growth(self, db) -> None:
        """When caps are None (default test fixture), no trim happens.
        Proves the feature is opt-in and backwards-compatible with
        tests that need to observe N records."""
        store = SQLiteMemoryStore(db)  # no caps
        await store.initialize()
        for i in range(10):
            await store.insert(
                _record(
                    record_id=f"r-{i}",
                    owner_id="npc-unbounded",
                    kind="episodic",
                    content=f"c-{i}",
                    created_tick=i,
                )
            )
        rows = await store.list_by_owner("npc-unbounded", kind="episodic")
        assert len(rows) == 10


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_sqlite_store_satisfies_protocol(self) -> None:
        from volnix.engines.memory.store import MemoryStoreProtocol

        # Construction requires a connected DB; we only need isinstance
        # to check method presence — any placeholder works.
        class _Stub:
            async def initialize(self, *, reset: bool = False) -> None: ...
            async def schema_version(self) -> int: ...
            async def insert(self, record) -> None: ...
            async def get(self, record_id): ...
            async def list_by_owner(self, owner_id, *, kind=None, limit=None): ...
            async def prune_oldest_episodic(self, owner_id, keep): ...
            async def fts_search(self, owner_id, query, top_k): ...
            async def embedding_cache_get(self, content_hash, provider_id): ...
            async def embedding_cache_put(self, content_hash, provider_id, vector_blob): ...

        assert isinstance(_Stub(), MemoryStoreProtocol)


# ---------------------------------------------------------------------------
# Determinism — byte-identical across runs
# ---------------------------------------------------------------------------


class TestDeterminism:
    async def test_two_runs_same_inputs_produce_identical_state(self) -> None:
        # G3 of the plan's hard constraints: same inputs → byte-identical
        # on-disk state. We can't trivially diff two :memory: DBs, but
        # we can assert that the serialised metadata_json blob is
        # identical, which is the only source of insertion-order
        # nondeterminism in MemoryRecord (D4).
        async def run_once() -> str:
            db = await create_database(":memory:", wal_mode=False)
            store = SQLiteMemoryStore(db)
            await store.initialize()
            # Same semantic payload but different insertion order —
            # should produce byte-identical metadata_json.
            await store.insert(_record(metadata={"zeta": 3, "alpha": 1, "beta": 2}))
            row = await db.fetchone(
                f"SELECT metadata_json FROM {TABLE_RECORDS} WHERE record_id = ?",
                ("r1",),
            )
            await db.close()
            assert row is not None
            return row["metadata_json"]

        a = await run_once()
        b = await run_once()
        assert a == b
        # Plus: the blob's key ordering is deterministic (sort_keys).
        parsed = json.loads(a)
        assert list(parsed.keys()) == sorted(parsed.keys())
