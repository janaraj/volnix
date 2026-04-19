"""SQLite-backed memory store (PMF Plan Phase 4B, Step 3).

Pure persistence layer. No LLM, no bus, no engine references.
Fully unit-testable against an in-memory SQLite via ``create_database(":memory:")``.

Design decisions
----------------
- **DI by ``Database``, not by path.** The store receives a connected
  ``Database`` instance and never constructs one itself. This matches
  the project's DI pattern (see ``StateEngine``) and keeps sqlite
  construction inside the persistence module per the source-guard
  allowlist. Composition (Step 10) resolves
  ``cfg.memory.storage_db_name`` → ``Database`` via
  ``ConnectionManager.get_connection()`` and injects it here (G5).
- **Schema versioning** (G12): a ``memory_schema_version`` table
  carries the installed version. ``initialize()`` creates v1 on a
  fresh DB, refuses to proceed on any mismatch. Phase 4B ships
  version 1 only; migrations land when a later phase needs them.
- **Determinism** (G4 of the plan's hard constraints):
  * Every ``SELECT`` that returns a list uses
    ``ORDER BY <primary_key_or_score> [ASC|DESC], record_id ASC``
    so tie-breaks are deterministic.
  * JSON-typed columns (``tags_json``, ``metadata_json``,
    ``consolidated_from_json``) are serialised with
    ``json.dumps(..., sort_keys=True)`` so same-content rows produce
    byte-identical payloads (D4 of Step 1 review).
- **Content-hash invariant**: the store trusts ``MemoryRecord.content_hash``
  to already be validated (``core.memory_types`` enforces the
  ``^[a-f0-9]{64}$`` pattern at construction). The store does not
  re-validate — that would be duplicate work. Two records with the
  same content share the same ``content_hash`` and therefore the same
  embedding cache row. This is documented invariant, not an accident.
- **FTS5 query safety**: user-supplied query text may contain FTS5
  operator tokens (``AND``, ``OR``, quotes, etc.) that would error
  at parse time. ``fts_search`` tokenises the query on whitespace
  and OR-joins quoted tokens, producing a recall-friendly BM25
  search that survives any input text.

See: ``internal_docs/pmf/phase-4b-memory-engine.md`` §Code Pointers
and the approved plan at
``.claude/plans/the-pdf-is-the-wiggly-matsumoto.md``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable

from volnix.core.memory_types import MemoryKind, MemoryRecord
from volnix.core.types import MemoryRecordId
from volnix.persistence.database import Database

logger = logging.getLogger(__name__)

# Module-level schema constants. Single source of truth — tests and
# future migrations reference these by name instead of re-declaring.
SCHEMA_VERSION: int = 1
TABLE_RECORDS: str = "memory_records"
TABLE_FTS: str = "memory_fts"
TABLE_EMBEDDING_CACHE: str = "embedding_cache"
TABLE_SCHEMA_VERSION: str = "memory_schema_version"


@runtime_checkable
class MemoryStoreProtocol(Protocol):
    """Engine-internal storage contract consumed by ``MemoryEngine``,
    ``Recall``, and ``Consolidator``. Not a cross-engine protocol —
    lives in ``engines/memory/`` alongside the concrete impl.
    """

    async def initialize(self, *, reset: bool = False) -> None: ...
    async def schema_version(self) -> int: ...
    async def insert(self, record: MemoryRecord) -> None: ...
    async def get(self, record_id: MemoryRecordId) -> MemoryRecord | None: ...
    async def list_by_owner(
        self,
        owner_id: str,
        *,
        kind: MemoryKind | None = None,
        limit: int | None = None,
    ) -> list[MemoryRecord]: ...

    async def prune_oldest_episodic(
        self, owner_id: str, keep: int
    ) -> list[MemoryRecordId]: ...

    async def fts_search(
        self, owner_id: str, query: str, top_k: int
    ) -> list[tuple[MemoryRecord, float]]: ...

    async def embedding_cache_get(
        self, content_hash: str, provider_id: str
    ) -> bytes | None: ...

    async def embedding_cache_put(
        self, content_hash: str, provider_id: str, vector_blob: bytes
    ) -> None: ...


class SQLiteMemoryStore:
    """SQLite implementation of :class:`MemoryStoreProtocol`.

    Accepts a connected ``Database`` via DI; never constructs one
    itself. Tests inject ``await create_database(":memory:")`` and
    get a real SQLite backend with full FTS5 support.
    """

    def __init__(self, db: Database) -> None:
        if db is None:
            raise ValueError(
                "SQLiteMemoryStore requires a connected Database instance "
                "(G5 — inject via ConnectionManager or create_database)."
            )
        self._db = db

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self, *, reset: bool = False) -> None:
        """Create schema v1 on a fresh DB, refuse to proceed on a
        version mismatch. When ``reset=True``, truncate data tables
        after schema is present (G15 — ``reset_on_world_start``).
        """
        has_version_table = await self._db.table_exists(TABLE_SCHEMA_VERSION)
        if not has_version_table:
            await self._create_schema_v1()
            await self._db.execute(
                f"INSERT INTO {TABLE_SCHEMA_VERSION} (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
        else:
            installed = await self._read_schema_version()
            if installed != SCHEMA_VERSION:
                raise RuntimeError(
                    f"MemoryStore schema version mismatch: DB has v{installed}, "
                    f"code expects v{SCHEMA_VERSION}. Phase 4B ships v1 only; "
                    f"no migration path is implemented yet. A later phase will "
                    f"add upward migrations. Refusing to proceed."
                )

        if reset:
            await self._truncate_data()

    async def _create_schema_v1(self) -> None:
        """Create all tables and indices. Each DDL is idempotent
        (``IF NOT EXISTS``) so a partial prior initialise doesn't
        cause a collision on rerun."""
        ddls: list[str] = [
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE_SCHEMA_VERSION} (
                version INTEGER PRIMARY KEY
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE_RECORDS} (
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
            """,
            f"""
            CREATE INDEX IF NOT EXISTS idx_memory_owner_kind
            ON {TABLE_RECORDS}(owner_id, kind, created_tick DESC)
            """,
            f"""
            CREATE INDEX IF NOT EXISTS idx_memory_importance
            ON {TABLE_RECORDS}(owner_id, importance DESC)
            """,
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS {TABLE_FTS} USING fts5(
                record_id UNINDEXED,
                content,
                tokenize='porter unicode61'
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE_EMBEDDING_CACHE} (
                content_hash TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                vector_blob BLOB NOT NULL,
                PRIMARY KEY (content_hash, provider_id)
            )
            """,
        ]
        async with self._db.transaction():
            for ddl in ddls:
                await self._db.execute(ddl)

    async def _truncate_data(self) -> None:
        """Clear data tables while preserving schema + version row.
        Used by ``reset_on_world_start`` (G15)."""
        async with self._db.transaction():
            await self._db.execute(f"DELETE FROM {TABLE_RECORDS}")
            await self._db.execute(f"DELETE FROM {TABLE_FTS}")
            await self._db.execute(f"DELETE FROM {TABLE_EMBEDDING_CACHE}")

    async def _read_schema_version(self) -> int:
        row = await self._db.fetchone(
            f"SELECT version FROM {TABLE_SCHEMA_VERSION} LIMIT 1"
        )
        return int(row["version"]) if row else 0

    async def schema_version(self) -> int:
        """Return the installed schema version. Useful for migration
        code + tests; not called on the hot path."""
        return await self._read_schema_version()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def insert(self, record: MemoryRecord) -> None:
        """Persist one record + its FTS row atomically.

        ``content_hash`` is already validated by ``MemoryRecord``
        construction — the store does not re-check. JSON-typed
        columns are serialised with ``sort_keys=True`` for
        replay-determinism (D4)."""
        tags_json = json.dumps(list(record.tags), sort_keys=True)
        consolidated_json: str | None = None
        if record.consolidated_from is not None:
            consolidated_json = json.dumps(
                [str(r) for r in record.consolidated_from], sort_keys=True
            )
        metadata_json = json.dumps(record.metadata, sort_keys=True)

        async with self._db.transaction():
            await self._db.execute(
                f"""
                INSERT INTO {TABLE_RECORDS} (
                    record_id, scope, owner_id, kind, tier, source,
                    content, content_hash, importance, tags_json,
                    created_tick, consolidated_from_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(record.record_id),
                    record.scope,
                    record.owner_id,
                    record.kind,
                    record.tier,
                    record.source,
                    record.content,
                    record.content_hash,
                    float(record.importance),
                    tags_json,
                    int(record.created_tick),
                    consolidated_json,
                    metadata_json,
                ),
            )
            await self._db.execute(
                f"INSERT INTO {TABLE_FTS} (record_id, content) VALUES (?, ?)",
                (str(record.record_id), record.content),
            )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get(self, record_id: MemoryRecordId) -> MemoryRecord | None:
        row = await self._db.fetchone(
            f"SELECT * FROM {TABLE_RECORDS} WHERE record_id = ?",
            (str(record_id),),
        )
        return self._row_to_record(row) if row else None

    async def list_by_owner(
        self,
        owner_id: str,
        *,
        kind: MemoryKind | None = None,
        limit: int | None = None,
    ) -> list[MemoryRecord]:
        """List records for ``owner_id`` ordered newest-first with
        deterministic tie-break on ``record_id ASC``."""
        clauses = ["owner_id = ?"]
        params: list[Any] = [owner_id]
        if kind is not None:
            clauses.append("kind = ?")
            params.append(kind)
        where = " AND ".join(clauses)
        sql = (
            f"SELECT * FROM {TABLE_RECORDS} "
            f"WHERE {where} "
            f"ORDER BY created_tick DESC, record_id ASC"
        )
        if limit is not None:
            # ``limit`` is always a server-validated int (MemoryQuery
            # fields have ``Field(le=...)``), so inlining is safe.
            sql += f" LIMIT {int(limit)}"
        rows = await self._db.fetchall(sql, tuple(params))
        return [self._row_to_record(r) for r in rows]

    async def prune_oldest_episodic(
        self, owner_id: str, keep: int
    ) -> list[MemoryRecordId]:
        """Remove episodic records beyond the ``keep`` most recent.

        Ring-buffer enforcement for ``max_episodic_per_actor``.
        Returns the pruned IDs (for observability / test assertions).
        """
        if keep < 0:
            raise ValueError(f"prune_oldest_episodic: keep must be >= 0, got {keep}")
        # Select IDs to prune first (so we can return them), then
        # delete by explicit IDs — avoids any dependence on the
        # LIMIT/OFFSET ordering inside a DELETE.
        rows = await self._db.fetchall(
            f"""
            SELECT record_id FROM {TABLE_RECORDS}
            WHERE owner_id = ? AND kind = 'episodic'
            ORDER BY created_tick DESC, record_id ASC
            LIMIT -1 OFFSET ?
            """,
            (owner_id, keep),
        )
        pruned_ids = [MemoryRecordId(r["record_id"]) for r in rows]
        if not pruned_ids:
            return []
        placeholders = ",".join("?" * len(pruned_ids))
        async with self._db.transaction():
            await self._db.execute(
                f"DELETE FROM {TABLE_RECORDS} WHERE record_id IN ({placeholders})",
                tuple(str(i) for i in pruned_ids),
            )
            await self._db.execute(
                f"DELETE FROM {TABLE_FTS} WHERE record_id IN ({placeholders})",
                tuple(str(i) for i in pruned_ids),
            )
        return pruned_ids

    async def fts_search(
        self, owner_id: str, query: str, top_k: int
    ) -> list[tuple[MemoryRecord, float]]:
        """FTS5 BM25 search scoped to ``owner_id``. Sorted by score
        (lower bm25 = better match) with deterministic tie-break.

        Query text is tokenised on whitespace and OR-joined so
        arbitrary prose is safe against FTS5 operator parsing.
        """
        if top_k <= 0:
            return []
        match_expr = self._build_fts_match(query)
        if not match_expr:
            return []
        rows = await self._db.fetchall(
            f"""
            SELECT r.*, bm25({TABLE_FTS}) AS score
            FROM {TABLE_FTS}
            JOIN {TABLE_RECORDS} r ON r.record_id = {TABLE_FTS}.record_id
            WHERE r.owner_id = ? AND {TABLE_FTS} MATCH ?
            ORDER BY score ASC, r.record_id ASC
            LIMIT ?
            """,
            (owner_id, match_expr, int(top_k)),
        )
        return [(self._row_to_record(r), float(r["score"])) for r in rows]

    # ------------------------------------------------------------------
    # Embedding cache
    # ------------------------------------------------------------------

    async def embedding_cache_get(
        self, content_hash: str, provider_id: str
    ) -> bytes | None:
        row = await self._db.fetchone(
            f"""
            SELECT vector_blob FROM {TABLE_EMBEDDING_CACHE}
            WHERE content_hash = ? AND provider_id = ?
            """,
            (content_hash, provider_id),
        )
        return row["vector_blob"] if row else None

    async def embedding_cache_put(
        self, content_hash: str, provider_id: str, vector_blob: bytes
    ) -> None:
        await self._db.execute(
            f"""
            INSERT OR REPLACE INTO {TABLE_EMBEDDING_CACHE}
            (content_hash, provider_id, vector_blob) VALUES (?, ?, ?)
            """,
            (content_hash, provider_id, vector_blob),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_fts_match(query: str) -> str:
        """Safely translate arbitrary user text into an FTS5 MATCH
        expression. Each whitespace-separated token is quoted and
        embedded-quotes escaped. Tokens are OR-joined for recall.
        Empty / whitespace-only input returns an empty string; the
        caller short-circuits to no-match."""
        tokens = query.split()
        if not tokens:
            return ""
        escaped: list[str] = []
        for t in tokens:
            # FTS5 escapes embedded quotes by doubling.
            safe = t.replace('"', '""')
            escaped.append(f'"{safe}"')
        return " OR ".join(escaped)

    @staticmethod
    def _row_to_record(row: dict[str, Any]) -> MemoryRecord:
        consolidated: list[MemoryRecordId] | None = None
        raw = row.get("consolidated_from_json")
        if raw:
            consolidated = [MemoryRecordId(x) for x in json.loads(raw)]
        return MemoryRecord(
            record_id=MemoryRecordId(row["record_id"]),
            scope=row["scope"],
            owner_id=row["owner_id"],
            kind=row["kind"],
            tier=row["tier"],
            source=row["source"],
            content=row["content"],
            content_hash=row["content_hash"],
            importance=float(row["importance"]),
            tags=json.loads(row["tags_json"]),
            created_tick=int(row["created_tick"]),
            consolidated_from=consolidated,
            metadata=json.loads(row["metadata_json"]),
        )
