"""Unified Persistence Layer for the Volnix framework.

This package provides a common database abstraction, connection management,
SQLite implementation with WAL mode, schema migrations, and snapshot
storage for world state.

Re-exports the primary public API surface so downstream code can do::

    from volnix.persistence import ConnectionManager, Database
"""

from volnix.persistence.append_log import AppendOnlyLog
from volnix.persistence.config import PersistenceConfig
from volnix.persistence.database import Database
from volnix.persistence.manager import ConnectionManager
from volnix.persistence.migrations import Migration, MigrationRunner
from volnix.persistence.snapshot import SnapshotStore
from volnix.persistence.sqlite import SQLiteDatabase

__all__ = [
    # Public API — use Database ABC, not SQLiteDatabase directly
    "AppendOnlyLog",
    "ConnectionManager",
    "Database",
    "Migration",
    "MigrationRunner",
    "PersistenceConfig",
    "SnapshotStore",
    # Concrete impl (composition root only)
    "SQLiteDatabase",
]
