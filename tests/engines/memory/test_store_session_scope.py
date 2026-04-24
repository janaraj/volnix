"""Store-layer session-scoping tests.

Locks the session-isolation semantics introduced by
``tnl/session-scoped-memory.tnl``. Integration-style against a real
in-memory SQLite (no mocks of the path under test).

Test discipline: every public behavior has a negative case before
the positive case; tight bounds (exact equality, not ``>= 0``);
observability side effects asserted where applicable.
"""

from __future__ import annotations

import pytest

from volnix.core.memory_types import MemoryRecord, content_hash_of
from volnix.core.types import MemoryRecordId, SessionId
from volnix.engines.memory.store import (
    SCHEMA_VERSION,
    TABLE_RECORDS,
    TABLE_SCHEMA_VERSION,
    SQLiteMemoryStore,
)
from volnix.persistence.manager import create_database

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db():
    database = await create_database(":memory:", wal_mode=False)
    yield database
    await database.close()


@pytest.fixture
async def store(db):
    s = SQLiteMemoryStore(db)
    await s.initialize()
    return s


def _rec(
    record_id: str,
    content: str,
    *,
    owner_id: str = "actor-1",
    session_id: SessionId | None = None,
    kind: str = "episodic",
    tier: str = "tier2",
    source: str = "explicit",
    importance: float = 0.5,
    created_tick: int = 10,
) -> MemoryRecord:
    return MemoryRecord(
        record_id=MemoryRecordId(record_id),
        scope="actor",
        owner_id=owner_id,
        session_id=session_id,
        kind=kind,  # type: ignore[arg-type]
        tier=tier,  # type: ignore[arg-type]
        source=source,  # type: ignore[arg-type]
        content=content,
        content_hash=content_hash_of(content),
        importance=importance,
        tags=[],
        created_tick=created_tick,
        consolidated_from=None,
        metadata={},
    )


# ---------------------------------------------------------------------------
# Isolation — read boundary
# ---------------------------------------------------------------------------


class TestListByOwnerSessionIsolation:
    """``list_by_owner`` MUST filter on session_id with NULL-safe
    semantics (``tnl/session-scoped-memory.tnl``)."""

    async def test_negative_cross_session_returns_empty(self, store) -> None:
        # Populate session alpha only; read with session beta — zero
        # rows. Not "few" — zero. Absence of cross-contamination is
        # the product.
        for i in range(3):
            await store.insert(_rec(f"a{i}", f"alpha-{i}", session_id=SessionId("sess-alpha")))
        hits = await store.list_by_owner("actor-1", session_id=SessionId("sess-beta"))
        assert hits == []

    async def test_negative_session_caller_cannot_see_null_rows(self, store) -> None:
        # A session caller must NOT pick up session-less rows.
        await store.insert(_rec("n1", "session-less record", session_id=None))
        hits = await store.list_by_owner("actor-1", session_id=SessionId("sess-alpha"))
        assert hits == []

    async def test_negative_null_caller_cannot_see_session_rows(self, store) -> None:
        # A session-less caller (session_id=None) must NOT pick up
        # session-scoped rows.
        await store.insert(_rec("s1", "scoped record", session_id=SessionId("sess-x")))
        hits = await store.list_by_owner("actor-1", session_id=None)
        assert hits == []

    async def test_positive_session_reads_are_isolated(self, store) -> None:
        await store.insert(_rec("a1", "alpha-one", session_id=SessionId("sess-alpha")))
        await store.insert(_rec("a2", "alpha-two", session_id=SessionId("sess-alpha")))
        await store.insert(_rec("b1", "beta-one", session_id=SessionId("sess-beta")))
        await store.insert(_rec("n1", "null-one", session_id=None))

        alpha = await store.list_by_owner("actor-1", session_id=SessionId("sess-alpha"))
        beta = await store.list_by_owner("actor-1", session_id=SessionId("sess-beta"))
        null = await store.list_by_owner("actor-1", session_id=None)

        assert {str(r.record_id) for r in alpha} == {"a1", "a2"}
        assert {str(r.record_id) for r in beta} == {"b1"}
        assert {str(r.record_id) for r in null} == {"n1"}
        # Every alpha row carries the alpha session_id exactly.
        for r in alpha:
            assert r.session_id == SessionId("sess-alpha")


class TestFtsSearchSessionIsolation:
    """FTS search paths also MUST respect session isolation."""

    async def test_negative_cross_session_fts_returns_empty(self, store) -> None:
        await store.insert(_rec("a1", "distinctive alpha text", session_id=SessionId("sess-alpha")))
        hits = await store.fts_search(
            "actor-1", "distinctive", 10, session_id=SessionId("sess-beta")
        )
        assert hits == []

    async def test_positive_fts_session_scoped(self, store) -> None:
        await store.insert(_rec("a1", "unique-token alpha", session_id=SessionId("sess-alpha")))
        await store.insert(_rec("b1", "unique-token beta", session_id=SessionId("sess-beta")))
        hits = await store.fts_search(
            "actor-1", "unique-token", 10, session_id=SessionId("sess-alpha")
        )
        assert len(hits) == 1
        rec, _score = hits[0]
        assert str(rec.record_id) == "a1"
        assert rec.session_id == SessionId("sess-alpha")


# ---------------------------------------------------------------------------
# Ring-buffer caps per (owner, session) slice
# ---------------------------------------------------------------------------


class TestPerSessionRingBuffer:
    """Ring-buffer caps MUST be enforced per ``(owner_id, session_id)``
    slice. One session's overflow MUST NOT evict another session's
    records (``tnl/session-scoped-memory.tnl``)."""

    async def test_positive_sessions_have_independent_caps(self, db) -> None:
        store = SQLiteMemoryStore(db, max_episodic_per_owner=3)
        await store.initialize()
        # 5 in alpha, 5 in beta, 5 session-less — expect 3 in each slice.
        for i in range(5):
            await store.insert(
                _rec(f"a{i}", f"alpha-{i}", session_id=SessionId("sess-alpha"), created_tick=i)
            )
            await store.insert(
                _rec(f"b{i}", f"beta-{i}", session_id=SessionId("sess-beta"), created_tick=i)
            )
            await store.insert(_rec(f"n{i}", f"null-{i}", session_id=None, created_tick=i))

        alpha = await store.list_by_owner("actor-1", session_id=SessionId("sess-alpha"))
        beta = await store.list_by_owner("actor-1", session_id=SessionId("sess-beta"))
        null = await store.list_by_owner("actor-1", session_id=None)

        assert len(alpha) == 3
        assert len(beta) == 3
        assert len(null) == 3
        # Newest three per slice retained, oldest evicted.
        assert {str(r.record_id) for r in alpha} == {"a2", "a3", "a4"}
        assert {str(r.record_id) for r in beta} == {"b2", "b3", "b4"}
        assert {str(r.record_id) for r in null} == {"n2", "n3", "n4"}

    async def test_negative_session_overflow_does_not_evict_null_rows(self, db) -> None:
        # Dedicated regression: overflowing a session-scoped slice
        # MUST NOT touch session-less rows.
        store = SQLiteMemoryStore(db, max_episodic_per_owner=2)
        await store.initialize()
        # Two session-less rows (at cap), then overflow alpha aggressively.
        await store.insert(_rec("n1", "keep-me-1", session_id=None, created_tick=0))
        await store.insert(_rec("n2", "keep-me-2", session_id=None, created_tick=1))
        for i in range(10):
            await store.insert(
                _rec(
                    f"a{i}",
                    f"alpha-overflow-{i}",
                    session_id=SessionId("sess-alpha"),
                    created_tick=100 + i,
                )
            )

        null = await store.list_by_owner("actor-1", session_id=None)
        alpha = await store.list_by_owner("actor-1", session_id=SessionId("sess-alpha"))
        assert {str(r.record_id) for r in null} == {"n1", "n2"}  # untouched
        assert len(alpha) == 2  # capped at 2 within its slice


# ---------------------------------------------------------------------------
# Prune + session filter
# ---------------------------------------------------------------------------


class TestPruneOldestEpisodicSessionScoped:
    """``prune_oldest_episodic`` MUST only prune records in the
    caller's session slice."""

    async def test_positive_prune_only_targets_requested_session(self, store) -> None:
        # 3 in alpha, 3 session-less; prune alpha keep=1 → 2 alpha
        # pruned, 3 session-less untouched.
        for i in range(3):
            await store.insert(
                _rec(f"a{i}", f"alpha-{i}", session_id=SessionId("sess-alpha"), created_tick=i)
            )
            await store.insert(_rec(f"n{i}", f"null-{i}", session_id=None, created_tick=i))

        pruned = await store.prune_oldest_episodic(
            "actor-1", keep=1, session_id=SessionId("sess-alpha")
        )
        # The oldest 2 in alpha should be pruned
        assert len(pruned) == 2
        assert {str(p) for p in pruned} == {"a0", "a1"}

        alpha = await store.list_by_owner("actor-1", session_id=SessionId("sess-alpha"))
        null = await store.list_by_owner("actor-1", session_id=None)
        assert {str(r.record_id) for r in alpha} == {"a2"}
        assert {str(r.record_id) for r in null} == {"n0", "n1", "n2"}  # untouched


# ---------------------------------------------------------------------------
# Schema migration v1 → v2
# ---------------------------------------------------------------------------


class TestMigrationV1ToV2:
    """Schema v1 → v2 migration runs in place, does not rewrite
    existing rows, and is transactional
    (``tnl/session-scoped-memory.tnl``)."""

    async def _create_v1_schema(self, db) -> None:
        """Author a v1 DB by hand (mirrors pre-0.2.0 layout)."""
        async with db.transaction():
            await db.execute(f"CREATE TABLE {TABLE_SCHEMA_VERSION} (version INTEGER PRIMARY KEY)")
            await db.execute(f"INSERT INTO {TABLE_SCHEMA_VERSION} (version) VALUES (1)")
            await db.execute(
                f"""
                CREATE TABLE {TABLE_RECORDS} (
                    record_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    source TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    importance REAL NOT NULL,
                    tags_json TEXT NOT NULL,
                    created_tick INTEGER NOT NULL,
                    consolidated_from_json TEXT,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            await db.execute(
                f"CREATE INDEX idx_memory_owner_kind "
                f"ON {TABLE_RECORDS}(owner_id, kind, created_tick DESC)"
            )
            await db.execute(
                f"CREATE INDEX idx_memory_importance ON {TABLE_RECORDS}(owner_id, importance DESC)"
            )
            await db.execute(
                """
                CREATE VIRTUAL TABLE memory_fts USING fts5(
                    record_id UNINDEXED,
                    content,
                    tokenize='porter unicode61 remove_diacritics 2'
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE embedding_cache (
                    content_hash TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    vector_blob BLOB NOT NULL,
                    PRIMARY KEY (content_hash, provider_id)
                )
                """
            )
            # Insert one v1 row by hand (no session_id column).
            await db.execute(
                f"""
                INSERT INTO {TABLE_RECORDS} (
                    record_id, scope, owner_id, kind, tier, source,
                    content, content_hash, importance, tags_json,
                    created_tick, consolidated_from_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-1",
                    "actor",
                    "actor-1",
                    "episodic",
                    "tier2",
                    "explicit",
                    "legacy content",
                    content_hash_of("legacy content"),
                    0.5,
                    "[]",
                    5,
                    None,
                    "{}",
                ),
            )

    async def test_positive_v1_to_v2_migration_in_place(self, db) -> None:
        await self._create_v1_schema(db)

        # Construct fresh store + initialize → migration runs.
        store = SQLiteMemoryStore(db)
        await store.initialize()

        # Version bumped.
        assert await store.schema_version() == SCHEMA_VERSION == 2

        # session_id column present.
        cols = await db.fetchall(f"PRAGMA table_info({TABLE_RECORDS})")
        col_names = {row["name"] for row in cols}
        assert "session_id" in col_names

        # v1 index names are gone.
        idx = await db.fetchall("SELECT name FROM sqlite_master WHERE type = 'index'")
        idx_names = {row["name"] for row in idx}
        assert "idx_memory_owner_kind" not in idx_names
        assert "idx_memory_importance" not in idx_names
        # v2 indexes present.
        assert "idx_memory_session_owner_kind" in idx_names
        assert "idx_memory_session_owner_importance" in idx_names

        # Legacy row still readable with session_id IS NULL.
        legacy = await store.get(MemoryRecordId("legacy-1"))
        assert legacy is not None
        assert legacy.session_id is None  # unrewritten

    async def test_positive_migration_is_idempotent_on_v2(self, db) -> None:
        # Fresh v2 DB, then calling initialize() again must be a no-op.
        store = SQLiteMemoryStore(db)
        await store.initialize()
        await store.initialize()  # re-init → up-to-date branch
        assert await store.schema_version() == 2

    async def test_negative_unknown_future_version_refused(self, db) -> None:
        # Install a v3 marker — migration path does not know v3.
        async with db.transaction():
            await db.execute(f"CREATE TABLE {TABLE_SCHEMA_VERSION} (version INTEGER PRIMARY KEY)")
            await db.execute(f"INSERT INTO {TABLE_SCHEMA_VERSION} (version) VALUES (3)")
        store = SQLiteMemoryStore(db)
        with pytest.raises(RuntimeError, match=r"v3.*v2|v2.*v3|version mismatch"):
            await store.initialize()
