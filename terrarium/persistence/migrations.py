"""Schema migration support for Terrarium databases.

Provides a versioned migration model and a runner that tracks the
current schema version and applies forward or backward migrations.
"""

from __future__ import annotations

from pydantic import BaseModel

from terrarium.persistence.database import Database


# ---------------------------------------------------------------------------
# Migration model
# ---------------------------------------------------------------------------


class Migration(BaseModel):
    """A single versioned schema migration.

    Attributes:
        version: Integer version number (must be unique and sequential).
        name: Human-readable name for the migration.
        sql_up: SQL to apply the migration (forward).
        sql_down: SQL to revert the migration (backward).
    """

    version: int
    name: str
    sql_up: str
    sql_down: str


# ---------------------------------------------------------------------------
# Migration runner
# ---------------------------------------------------------------------------


class MigrationRunner:
    """Applies and reverts schema migrations against a database.

    Parameters:
        db: The database instance to run migrations against.
    """

    def __init__(self, db: Database) -> None:
        ...

    def register(self, migration: Migration) -> None:
        """Register a migration for future execution.

        Args:
            migration: The migration to register.
        """
        ...

    async def get_current_version(self) -> int:
        """Return the current schema version from the database.

        Returns:
            The current version number, or ``0`` if no migrations
            have been applied.
        """
        ...

    async def migrate_up(self, target_version: int | None = None) -> int:
        """Apply pending migrations up to the target version.

        Args:
            target_version: The version to migrate to. If ``None``,
                            apply all pending migrations.

        Returns:
            Number of migrations applied.
        """
        ...

    async def migrate_down(self, target_version: int) -> int:
        """Revert migrations down to the target version.

        Args:
            target_version: The version to revert to (exclusive --
                            migrations above this version are reverted).

        Returns:
            Number of migrations reverted.
        """
        ...

    async def get_pending(self) -> list[Migration]:
        """Return migrations that have not yet been applied.

        Returns:
            List of pending migrations in version order.
        """
        ...
