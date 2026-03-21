"""Configuration model for the persistence layer.

Provides a Pydantic model that centralises all tuneable parameters for
the unified persistence subsystem, including storage location, WAL mode,
connection pooling, and migration behaviour.
"""

from __future__ import annotations

from pydantic import BaseModel


class PersistenceConfig(BaseModel):
    """Configuration for the Terrarium persistence layer.

    Attributes:
        base_dir: Base directory for all database files.
        wal_mode: Whether to enable WAL mode on SQLite databases.
        max_connections: Maximum number of concurrent database connections.
        migration_auto_run: Whether to automatically run pending migrations
                           on initialisation.
        backup_interval_seconds: Interval in seconds between automatic backups.
                                 Set to ``0`` to disable automatic backups.
    """

    base_dir: str = "terrarium_data"
    wal_mode: bool = True
    max_connections: int = 5
    migration_auto_run: bool = True
    backup_interval_seconds: int = 0
