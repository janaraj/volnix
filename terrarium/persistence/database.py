"""Abstract database interface.

Defines the :class:`Database` ABC that all concrete database backends
must implement.  Provides a uniform async API for executing SQL,
fetching results, managing transactions, and introspecting schema.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any


class Database(ABC):
    """Abstract base class for Terrarium database backends.

    Concrete implementations (e.g. :class:`SQLiteDatabase`) must provide
    all abstract methods defined here.
    """

    @abstractmethod
    async def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> Any:
        """Execute a single SQL statement.

        Args:
            sql: The SQL statement to execute.
            params: Optional positional parameters for the statement.

        Returns:
            Backend-specific result (e.g. cursor, row count).
        """
        ...

    @abstractmethod
    async def executemany(self, sql: str, params_list: list[tuple[Any, ...]]) -> None:
        """Execute a SQL statement against multiple parameter sets.

        Args:
            sql: The SQL statement to execute.
            params_list: List of parameter tuples, one per execution.
        """
        ...

    @abstractmethod
    async def fetchone(self, sql: str, params: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
        """Execute a query and return the first result row.

        Args:
            sql: The SQL query to execute.
            params: Optional positional parameters.

        Returns:
            A dict representing the row, or ``None`` if no rows matched.
        """
        ...

    @abstractmethod
    async def fetchall(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        """Execute a query and return all result rows.

        Args:
            sql: The SQL query to execute.
            params: Optional positional parameters.

        Returns:
            List of dicts, one per result row.
        """
        ...

    @abstractmethod
    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Context manager for an atomic transaction.

        Usage::

            async with db.transaction():
                await db.execute("INSERT ...")
                await db.execute("UPDATE ...")

        Yields:
            Nothing -- the transaction commits on clean exit and
            rolls back on exception.
        """
        yield  # pragma: no cover

    @abstractmethod
    async def close(self) -> None:
        """Close the database connection and release resources."""
        ...

    @abstractmethod
    async def table_exists(self, table_name: str) -> bool:
        """Check whether a table exists in the database.

        Args:
            table_name: Name of the table to check for.

        Returns:
            ``True`` if the table exists, ``False`` otherwise.
        """
        ...
