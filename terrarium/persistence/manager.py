"""Connection manager for the persistence layer.

ConnectionManager owns the lifecycle of all database connections,
provides named access to individual databases, and exposes a
health-check endpoint.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from terrarium.persistence.config import PersistenceConfig
from terrarium.persistence.database import Database
from terrarium.persistence.sqlite import SQLiteDatabase

# Default factory that creates SQLiteDatabase instances.
# Composition root can inject a different factory for testing or other backends.
DatabaseFactory = Callable[[str, bool], Database]


def _default_db_factory(db_path: str, wal_mode: bool) -> Database:
    """Default factory creating SQLiteDatabase instances."""
    return SQLiteDatabase(db_path, wal_mode=wal_mode)


async def create_database(path: str, wal_mode: bool = True) -> Database:
    """Create, connect, and return a SQLiteDatabase.

    Standalone factory for engines that need a DB without going through
    ConnectionManager (e.g., StateEngine in test fixtures).
    This keeps SQLiteDatabase construction confined to the persistence
    layer (in the source guard allowlist).
    """
    db = SQLiteDatabase(path, wal_mode=wal_mode)
    await db.connect()
    return db


class ConnectionManager:
    """Manages database connections across the Terrarium system.

    Parameters:
        config: Persistence configuration controlling base directory,
                WAL mode, connection limits, and migration behaviour.
        db_factory: Optional callable ``(db_path, wal_mode) -> Database``.
                    Defaults to creating :class:`SQLiteDatabase` instances.
    """

    def __init__(
        self,
        config: PersistenceConfig,
        db_factory: DatabaseFactory | None = None,
    ) -> None:
        self._config = config
        self._db_factory = db_factory or _default_db_factory
        self._connections: dict[str, Database] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Create the base directory and initialise default connections."""
        base_dir = Path(self._config.base_dir)
        await asyncio.to_thread(base_dir.mkdir, parents=True, exist_ok=True)

    async def shutdown(self) -> None:
        """Close all open database connections."""
        errors: list[tuple[str, str]] = []
        for name, db in self._connections.items():
            try:
                await db.close()
            except Exception as e:
                errors.append((name, str(e)))
        self._connections.clear()
        if errors:
            raise RuntimeError(f"Errors closing connections: {errors}")

    async def get_connection(self, db_name: str) -> Database:
        """Retrieve (or create) a database connection by logical name.

        Args:
            db_name: Logical name of the database (e.g. ``"events"``,
                     ``"ledger"``, ``"state"``).

        Returns:
            A :class:`Database` instance for the requested database.
        """
        async with self._lock:
            if db_name not in self._connections:
                db_path = str(Path(self._config.base_dir) / f"{db_name}.db")
                db = self._db_factory(db_path, self._config.wal_mode)
                await db.connect()
                self._connections[db_name] = db
            return self._connections[db_name]

    async def health_check(self) -> dict[str, Any]:
        """Check the health of all managed connections.

        Returns:
            A dict with ``count`` (number of connections) and
            ``connections`` (a mapping of database names to their
            health status).
        """
        connections: dict[str, Any] = {}
        for name, db in self._connections.items():
            try:
                await db.fetchone("SELECT 1 AS ok")
                connections[name] = {"status": "healthy"}
            except Exception as exc:
                connections[name] = {"status": "unhealthy", "error": str(exc)}
        return {"count": len(self._connections), "connections": connections}
