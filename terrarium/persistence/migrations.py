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
        self._db = db
        self._migrations: list[Migration] = []

    async def _ensure_migrations_table(self) -> None:
        """Create the internal migrations tracking table if it does not exist."""
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS _migrations (
                version  INTEGER PRIMARY KEY,
                name     TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

    def register(self, migration: Migration) -> None:
        """Register a migration for future execution.

        Args:
            migration: The migration to register.
        """
        self._migrations.append(migration)
        self._migrations.sort(key=lambda m: m.version)

    async def get_current_version(self) -> int:
        """Return the current schema version from the database.

        Returns:
            The current version number, or ``0`` if no migrations
            have been applied.
        """
        await self._ensure_migrations_table()
        row = await self._db.fetchone("SELECT MAX(version) AS v FROM _migrations")
        if row is None or row["v"] is None:
            return 0
        return int(row["v"])

    async def migrate_up(self, target_version: int | None = None) -> int:
        """Apply pending migrations up to the target version.

        Args:
            target_version: The version to migrate to. If ``None``,
                            apply all pending migrations.

        Returns:
            Number of migrations applied.
        """
        await self._ensure_migrations_table()
        current = await self.get_current_version()
        pending = [m for m in self._migrations if m.version > current]
        if target_version is not None:
            pending = [m for m in pending if m.version <= target_version]

        if not pending:
            return 0

        applied = 0
        async with self._db.transaction():
            for migration in pending:
                await self._db.execute(migration.sql_up)
                await self._db.execute(
                    "INSERT INTO _migrations (version, name) VALUES (?, ?)",
                    (migration.version, migration.name),
                )
                applied += 1
        return applied

    async def migrate_down(self, target_version: int) -> int:
        """Revert migrations down to the target version.

        Args:
            target_version: The version to revert to (exclusive --
                            migrations above this version are reverted).

        Returns:
            Number of migrations reverted.
        """
        await self._ensure_migrations_table()
        current = await self.get_current_version()
        to_revert = [m for m in reversed(self._migrations)
                     if m.version > target_version and m.version <= current]

        if not to_revert:
            return 0

        reverted = 0
        async with self._db.transaction():
            for migration in to_revert:
                await self._db.execute(migration.sql_down)
                await self._db.execute(
                    "DELETE FROM _migrations WHERE version = ?",
                    (migration.version,),
                )
                reverted += 1
        return reverted

    async def get_pending(self) -> list[Migration]:
        """Return migrations that have not yet been applied.

        Returns:
            List of pending migrations in version order.
        """
        current = await self.get_current_version()
        return [m for m in self._migrations if m.version > current]
