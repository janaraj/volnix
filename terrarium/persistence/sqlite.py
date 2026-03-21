"""SQLite implementation of the Database ABC.

Provides an async SQLite backend with WAL mode support, backup, and
vacuum utilities.  This is the default (and currently only) concrete
database backend for Terrarium.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any

from terrarium.persistence.database import Database


class SQLiteDatabase(Database):
    """Async SQLite database with WAL mode and utility methods.

    Parameters:
        db_path: Filesystem path to the SQLite database file.
        wal_mode: Whether to enable WAL (Write-Ahead Logging) mode
                  for improved concurrent read performance.
    """

    def __init__(self, db_path: str, wal_mode: bool = True) -> None:
        ...

    async def connect(self) -> None:
        """Open the database connection and apply pragmas."""
        ...

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
        ...

    async def executemany(self, sql: str, params_list: list[tuple[Any, ...]]) -> None:
        """Execute a SQL statement against multiple parameter sets.

        Args:
            sql: The SQL statement to execute.
            params_list: List of parameter tuples.
        """
        ...

    async def fetchone(self, sql: str, params: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
        """Execute a query and return the first result row.

        Args:
            sql: The SQL query to execute.
            params: Optional positional parameters.

        Returns:
            A dict representing the row, or ``None``.
        """
        ...

    async def fetchall(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        """Execute a query and return all result rows.

        Args:
            sql: The SQL query to execute.
            params: Optional positional parameters.

        Returns:
            List of dicts, one per result row.
        """
        ...

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Context manager for an atomic SQLite transaction.

        Yields:
            Nothing -- commits on clean exit, rolls back on exception.
        """
        yield  # pragma: no cover

    async def close(self) -> None:
        """Close the SQLite connection."""
        ...

    async def table_exists(self, table_name: str) -> bool:
        """Check whether a table exists in the SQLite database.

        Args:
            table_name: Name of the table to check.

        Returns:
            ``True`` if the table exists.
        """
        ...

    # ------------------------------------------------------------------
    # SQLite-specific utilities
    # ------------------------------------------------------------------

    async def backup(self, target_path: str) -> None:
        """Create a backup of the database at the given path.

        Args:
            target_path: Filesystem path for the backup file.
        """
        ...

    async def vacuum(self) -> None:
        """Reclaim unused space by vacuuming the database."""
        ...
