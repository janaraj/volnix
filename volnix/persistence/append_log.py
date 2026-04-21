"""Append-only log backed by SQLite. Shared by bus event log and ledger audit log."""

from __future__ import annotations

import re
from typing import Any

from volnix.persistence.database import Database

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_sql_name(name: str) -> None:
    """Raise ValueError if name is not a safe SQL identifier."""
    if not _SAFE_NAME_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier: {name!r}")


class AppendOnlyLog:
    """Generic append-only log table backed by a SQLite database.

    Receives a :class:`Database` via dependency injection -- does NOT
    create its own connection.  The caller (typically ConnectionManager)
    owns the database lifecycle.

    Parameters:
        db: The database backend to use.
        table_name: Name of the underlying SQL table.
        columns: List of ``(name, sql_type)`` pairs for user-defined columns.
    """

    def __init__(self, db: Database, table_name: str, columns: list[tuple[str, str]]) -> None:
        _validate_sql_name(table_name)
        for col_name, _ in columns:
            _validate_sql_name(col_name)
        self._db = db
        self._table = table_name
        self._columns = columns
        self._column_names = {col_name for col_name, _ in columns}

    async def create_index(self, column_name: str) -> None:
        """Create an index on the specified column.

        Args:
            column_name: The column to index (must be a declared column or 'created_at').
        """
        _validate_sql_name(column_name)
        index_name = f"idx_{self._table}_{column_name}"
        await self._db.execute(
            f"CREATE INDEX IF NOT EXISTS {index_name} ON {self._table}({column_name})"
        )

    async def initialize(self) -> None:
        """Create the backing table + ALTER TABLE ADD COLUMN for any
        declared column not present in the live table.

        PMF Plan Phase 4C Step 6 — lightweight migration-on-connect
        so the schema can grow without an out-of-band tool. SQLite
        ``ADD COLUMN`` with no ``NOT NULL``/``DEFAULT`` is a
        metadata-only operation, safe on every connect.

        **Caveat (audit M1):** ``ADD COLUMN`` does not carry
        ``DEFAULT`` from the declared type — the application layer
        must handle missing values on existing rows. Acceptable for
        Step 6's nullable ``session_id`` column; future non-null
        columns requiring ``DEFAULT`` should use a proper migration
        tool, not this on-connect pass.
        """
        cols = ", ".join(f"{name} {typ}" for name, typ in self._columns)
        await self._db.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._table} (
                sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                {cols},
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Migration-on-connect: read live columns, add any missing.
        live_rows = await self._db.fetchall(f"PRAGMA table_info({self._table})")
        live_names = {row["name"] for row in live_rows}
        for col_name, col_type in self._columns:
            if col_name not in live_names:
                # Strip NOT NULL / DEFAULT clauses — ADD COLUMN on
                # an existing table cannot accept NOT NULL without
                # a default.
                bare_type = col_type.split()[0]
                await self._db.execute(
                    f"ALTER TABLE {self._table} ADD COLUMN {col_name} {bare_type}"
                )
                # Audit C1: update _column_names so subsequent
                # append() calls recognise the new column — without
                # this, every append() with the new column raises
                # ValueError("Unknown column(s)").
                self._column_names.add(col_name)

    async def append(self, values: dict[str, Any]) -> int:
        """Append a row and return its auto-generated sequence ID.

        Args:
            values: Mapping of column name to value for the new row.

        Returns:
            The ``sequence_id`` assigned to the new row.
        """
        for key in values:
            _validate_sql_name(key)
        if not set(values.keys()).issubset(self._column_names):
            unknown = set(values.keys()) - self._column_names
            raise ValueError(f"Unknown column(s): {unknown}")
        col_names = ", ".join(values.keys())
        placeholders = ", ".join("?" for _ in values)
        await self._db.execute(
            f"INSERT INTO {self._table} ({col_names}) VALUES ({placeholders})",
            tuple(values.values()),
        )
        row = await self._db.fetchone("SELECT last_insert_rowid() as seq")
        return row["seq"]  # type: ignore[index]

    async def query(
        self,
        from_sequence: int = 0,
        filters: dict[str, Any] | None = None,
        range_filters: list[tuple[str, str, Any]] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order: str = "asc",
    ) -> list[dict[str, Any]]:
        """Query rows from the log.

        Args:
            from_sequence: Only return rows with ``sequence_id >= from_sequence``.
            filters: Optional column filters.  Values may be scalars (``=``)
                     or lists (``IN``).
            range_filters: Optional range filters as ``(column, operator, value)``
                          tuples. Supported operators: ``>=``, ``<=``, ``>``, ``<``.
            limit: Maximum number of rows to return.
            offset: Number of rows to skip (SQL OFFSET).
            order: Sort direction — ``"asc"`` (oldest first) or ``"desc"`` (newest first).

        Returns:
            Ordered list of matching rows as dicts.
        """
        _VALID_OPS = {">=", "<=", ">", "<"}
        if filters:
            for col in filters:
                _validate_sql_name(col)
        if range_filters:
            for col, op, val in range_filters:
                _validate_sql_name(col)
        sql = f"SELECT * FROM {self._table} WHERE sequence_id >= ?"
        params: list[Any] = [from_sequence]
        if filters:
            for col, val in filters.items():
                if isinstance(val, list):
                    placeholders = ",".join("?" for _ in val)
                    sql += f" AND {col} IN ({placeholders})"
                    params.extend(val)
                else:
                    sql += f" AND {col} = ?"
                    params.append(val)
        if range_filters:
            for col, op, val in range_filters:
                if op not in _VALID_OPS:
                    raise ValueError(f"Invalid range operator '{op}'. Must be one of {_VALID_OPS}")
                sql += f" AND {col} {op} ?"
                params.append(val)
        direction = "DESC" if order == "desc" else "ASC"
        sql += f" ORDER BY sequence_id {direction}"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        if offset is not None and offset > 0:
            sql += " OFFSET ?"
            params.append(offset)
        return await self._db.fetchall(sql, tuple(params))

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        """Return the number of rows, optionally filtered.

        Args:
            filters: Optional column-value filters (scalar equality only).

        Returns:
            Row count.
        """
        sql = f"SELECT COUNT(*) as cnt FROM {self._table}"
        params: list[Any] = []
        if filters:
            for col in filters:
                _validate_sql_name(col)
            conditions = []
            for col, val in filters.items():
                conditions.append(f"{col} = ?")
                params.append(val)
            if conditions:
                sql += " WHERE " + " AND ".join(conditions)
        row = await self._db.fetchone(sql, tuple(params) if params else None)
        return row["cnt"]  # type: ignore[index]

    async def latest_sequence(self) -> int:
        """Return the highest ``sequence_id`` in the log, or 0 if empty.

        Returns:
            The maximum sequence ID, or ``0`` when the table is empty.
        """
        row = await self._db.fetchone(f"SELECT MAX(sequence_id) as seq FROM {self._table}")
        return row["seq"] if row and row["seq"] is not None else 0
