"""Unified Persistence Layer for the Terrarium framework.

This package provides a common database abstraction, connection management,
SQLite implementation with WAL mode, schema migrations, and snapshot
storage for world state.

Re-exports the primary public API surface so downstream code can do::

    from terrarium.persistence import ConnectionManager, Database
"""

from terrarium.persistence.config import PersistenceConfig
from terrarium.persistence.database import Database
from terrarium.persistence.manager import ConnectionManager
from terrarium.persistence.migrations import Migration, MigrationRunner
from terrarium.persistence.snapshot import SnapshotStore
from terrarium.persistence.sqlite import SQLiteDatabase

__all__ = [
    "ConnectionManager",
    "Database",
    "Migration",
    "MigrationRunner",
    "PersistenceConfig",
    "SnapshotStore",
    "SQLiteDatabase",
]
