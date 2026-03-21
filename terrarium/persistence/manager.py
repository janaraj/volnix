"""Connection manager for the persistence layer.

ConnectionManager owns the lifecycle of all database connections,
provides named access to individual databases, and exposes a
health-check endpoint.
"""

from __future__ import annotations

from typing import Any

from terrarium.persistence.config import PersistenceConfig
from terrarium.persistence.database import Database


class ConnectionManager:
    """Manages database connections across the Terrarium system.

    Parameters:
        config: Persistence configuration controlling base directory,
                WAL mode, connection limits, and migration behaviour.
    """

    def __init__(self, config: PersistenceConfig) -> None:
        ...

    async def initialize(self) -> None:
        """Create the base directory and initialise default connections."""
        ...

    async def shutdown(self) -> None:
        """Close all open database connections."""
        ...

    async def get_connection(self, db_name: str) -> Database:
        """Retrieve (or create) a database connection by logical name.

        Args:
            db_name: Logical name of the database (e.g. ``"events"``,
                     ``"ledger"``, ``"state"``).

        Returns:
            A :class:`Database` instance for the requested database.
        """
        ...

    async def health_check(self) -> dict[str, Any]:
        """Check the health of all managed connections.

        Returns:
            A dict mapping database names to their health status.
        """
        ...
