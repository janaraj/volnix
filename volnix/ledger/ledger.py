"""Core Ledger implementation.

The Ledger provides an append-only audit trail for all significant
operations within the Volnix framework.  Entries are typed, immutable,
and queryable.

Receives a :class:`Database` via dependency injection -- does NOT create
its own ``SQLiteDatabase``.  The database lifecycle is managed externally
by :class:`ConnectionManager`.
"""

from __future__ import annotations

from volnix.ledger.config import LedgerConfig
from volnix.ledger.entries import LedgerEntry, deserialize_entry
from volnix.ledger.query import LedgerQuery
from volnix.persistence.append_log import AppendOnlyLog
from volnix.persistence.database import Database


class Ledger:
    """Append-only audit ledger for Volnix operations.

    Parameters:
        config: Ledger configuration controlling storage, retention, and
                which entry types are enabled.
        db: A :class:`Database` instance (provided via DI, not created here).
    """

    COLUMNS = [
        ("entry_type", "TEXT NOT NULL"),
        ("timestamp", "TEXT NOT NULL"),
        ("actor_id", "TEXT"),
        ("engine_name", "TEXT"),
        ("payload", "TEXT NOT NULL"),
    ]

    def __init__(self, config: LedgerConfig, db: Database) -> None:
        self._config = config
        self._db = db
        self._log = AppendOnlyLog(db=db, table_name="ledger_log", columns=self.COLUMNS)
        # None = all types enabled; non-empty set = only those types
        # An empty list in config means "all types" (None), not "no types"
        self._entry_types_enabled: set[str] | None = (
            set(config.entry_types_enabled) if config.entry_types_enabled else None
        )

    async def initialize(self) -> None:
        """Open the backing store and ensure the schema exists."""
        await self._log.initialize()
        await self._log.create_index("entry_type")
        await self._log.create_index("timestamp")
        await self._log.create_index("actor_id")

    async def shutdown(self) -> None:
        """No-op -- Database lifecycle is managed by ConnectionManager."""
        pass

    async def append(self, entry: LedgerEntry) -> int:
        """Append an entry to the ledger.

        Args:
            entry: The ledger entry to persist.

        Returns:
            The auto-assigned entry ID, or -1 if the entry type is disabled.
        """
        if self._entry_types_enabled and entry.entry_type not in self._entry_types_enabled:
            return -1
        return await self._log.append(
            {
                "entry_type": entry.entry_type,
                "timestamp": entry.timestamp.isoformat(),
                "actor_id": _extract_actor_id(entry),
                "engine_name": _extract_engine_name(entry),
                "payload": entry.model_dump_json(),
            }
        )

    async def query(self, filters: LedgerQuery) -> list[LedgerEntry]:
        """Query the ledger with structured filters.

        ALL filtering is pushed to SQL for performance:
        - entry_type, actor_id, engine_name → equality filters
        - start_time, end_time → range filters on timestamp column
        - limit, offset → SQL LIMIT/OFFSET

        Args:
            filters: Query parameters specifying type, time range,
                     actor, engine, and pagination.

        Returns:
            Ordered list of matching ledger entries.
        """
        # Equality filters → SQL WHERE col = ?
        sql_filters: dict = {}
        if filters.entry_type:
            sql_filters["entry_type"] = filters.entry_type
        if filters.actor_id:
            sql_filters["actor_id"] = str(filters.actor_id)
        if filters.engine_name:
            sql_filters["engine_name"] = filters.engine_name

        # Range filters → SQL WHERE col >= ? AND col <= ?
        range_filters: list[tuple[str, str, str]] = []
        if filters.start_time:
            range_filters.append(("timestamp", ">=", filters.start_time.isoformat()))
        if filters.end_time:
            range_filters.append(("timestamp", "<=", filters.end_time.isoformat()))

        rows = await self._log.query(
            from_sequence=0,
            filters=sql_filters if sql_filters else None,
            range_filters=range_filters if range_filters else None,
            limit=filters.limit,
            offset=filters.offset if filters.offset is not None else None,
        )

        # Typed deserialization via entry registry
        return [deserialize_entry(row) for row in rows]

    async def get_count(self, entry_type: str | None = None) -> int:
        """Return the total number of ledger entries.

        Args:
            entry_type: If provided, count only entries of this type.

        Returns:
            Number of matching entries.
        """
        filters = {"entry_type": entry_type} if entry_type else None
        return await self._log.count(filters)


def _extract_actor_id(entry: LedgerEntry) -> str:
    """Extract actor_id from an entry if it has one."""
    val = getattr(entry, "actor_id", None)
    return str(val) if val else ""


def _extract_engine_name(entry: LedgerEntry) -> str:
    """Extract engine_name from an entry if it has one."""
    return getattr(entry, "engine_name", None) or ""
