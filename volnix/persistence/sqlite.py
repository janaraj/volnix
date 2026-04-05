"""SQLite implementation of the Database ABC.

Provides an async SQLite backend with WAL mode support, backup, and
vacuum utilities.  This is the default (and currently only) concrete
database backend for Volnix.
"""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any

import aiosqlite

from volnix.persistence.database import Database


class SQLiteDatabase(Database):
    """Async SQLite database with WAL mode and utility methods.

    Parameters:
        db_path: Filesystem path to the SQLite database file.
        wal_mode: Whether to enable WAL (Write-Ahead Logging) mode
                  for improved concurrent read performance.
    """

    def __init__(self, db_path: str, wal_mode: bool = True) -> None:
        self._db_path = db_path
        self._wal_mode = wal_mode
        self._conn: aiosqlite.Connection | None = None
        self._transaction_depth: int = 0

    async def connect(self) -> None:
        """Open the database connection and apply pragmas."""
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        if self._wal_mode and self._db_path != ":memory:":
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")  # 5s wait on lock contention
        await self._conn.execute("PRAGMA foreign_keys=ON")

    # ------------------------------------------------------------------
    # Database ABC implementation
    # ------------------------------------------------------------------

    async def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> Any:
        """Execute a single SQL statement.

        Args:
            sql: The SQL statement to execute.
            params: Optional positional parameters.

        Returns:
            Backend-specific result.
        """
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        cursor = await self._conn.execute(sql, params or ())
        if self._transaction_depth == 0:
            await self._conn.commit()
        return cursor

    async def executemany(self, sql: str, params_list: list[tuple[Any, ...]]) -> None:
        """Execute a SQL statement against multiple parameter sets.

        Args:
            sql: The SQL statement to execute.
            params_list: List of parameter tuples.
        """
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        await self._conn.executemany(sql, params_list)
        if self._transaction_depth == 0:
            await self._conn.commit()

    async def fetchone(self, sql: str, params: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
        """Execute a query and return the first result row.

        Args:
            sql: The SQL query to execute.
            params: Optional positional parameters.

        Returns:
            A dict representing the row, or ``None``.
        """
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        cursor = await self._conn.execute(sql, params or ())
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetchall(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        """Execute a query and return all result rows.

        Args:
            sql: The SQL query to execute.
            params: Optional positional parameters.

        Returns:
            List of dicts, one per result row.
        """
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        cursor = await self._conn.execute(sql, params or ())
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Context manager for an atomic SQLite transaction.

        Supports nesting: only the outermost transaction issues BEGIN/COMMIT/ROLLBACK.

        Yields:
            Nothing -- commits on clean exit, rolls back on exception.
        """
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        if self._transaction_depth > 0:
            # Nested transaction - just track depth
            self._transaction_depth += 1
            try:
                yield
            finally:
                self._transaction_depth -= 1
            return
        self._transaction_depth += 1
        await self._conn.execute("BEGIN")
        try:
            yield
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise
        finally:
            self._transaction_depth -= 1

    async def close(self) -> None:
        """Close the SQLite connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def table_exists(self, table_name: str) -> bool:
        """Check whether a table exists in the SQLite database.

        Args:
            table_name: Name of the table to check.

        Returns:
            ``True`` if the table exists.
        """
        row = await self.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return row is not None

    # ------------------------------------------------------------------
    # SQLite-specific utilities
    # ------------------------------------------------------------------

    async def backup(self, target_path: str) -> None:
        """Create a backup of the database at the given path.

        Uses sqlite3's built-in backup API, dispatched to a thread to
        avoid blocking the event loop and to satisfy SQLite's
        thread-affinity requirement.

        Args:
            target_path: Filesystem path for the backup file.
        """
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")

        # NOTE: Accesses aiosqlite internal `_connection` — pin aiosqlite>=0.19,<1.0
        source_conn: sqlite3.Connection = self._conn._connection  # type: ignore[attr-defined]

        def _do_backup() -> None:
            target = sqlite3.connect(target_path)
            try:
                source_conn.backup(target)
            finally:
                target.close()

        # Run on aiosqlite's dedicated thread so we stay on the same
        # thread that owns source_conn.
        await self._conn._execute(_do_backup)  # type: ignore[attr-defined]

    async def vacuum(self) -> None:
        """Reclaim unused space by vacuuming the database."""
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        await self._conn.execute("VACUUM")
        await self._conn.commit()
