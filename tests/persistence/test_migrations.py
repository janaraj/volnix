"""Tests for terrarium.persistence.migrations — schema migration system."""
import pytest
from terrarium.persistence.sqlite import SQLiteDatabase
from terrarium.persistence.migrations import Migration, MigrationRunner


@pytest.fixture
async def db(tmp_path):
    """Create a temporary SQLite database for migration tests."""
    database = SQLiteDatabase(str(tmp_path / "migrations.db"))
    await database.connect()
    yield database
    await database.close()


def _sample_migrations() -> list[Migration]:
    """Return a pair of sample migrations for testing."""
    return [
        Migration(
            version=1,
            name="create_users",
            sql_up="CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)",
            sql_down="DROP TABLE users",
        ),
        Migration(
            version=2,
            name="create_posts",
            sql_up="CREATE TABLE posts (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), body TEXT)",
            sql_down="DROP TABLE posts",
        ),
    ]


async def test_migration_register(db):
    """register() should store migrations sorted by version."""
    runner = MigrationRunner(db)
    m2, m1 = _sample_migrations()[1], _sample_migrations()[0]

    # Register out of order
    runner.register(m2)
    runner.register(m1)

    pending = await runner.get_pending()
    assert len(pending) == 2
    assert pending[0].version == 1
    assert pending[1].version == 2


async def test_migration_get_current_version(db):
    """get_current_version() should return 0 when no migrations applied."""
    runner = MigrationRunner(db)
    assert await runner.get_current_version() == 0


async def test_migration_migrate_up(db):
    """migrate_up() should apply pending migrations and create tables."""
    runner = MigrationRunner(db)
    for m in _sample_migrations():
        runner.register(m)

    applied = await runner.migrate_up()
    assert applied == 2
    assert await runner.get_current_version() == 2
    assert await db.table_exists("users") is True
    assert await db.table_exists("posts") is True


async def test_migration_get_pending(db):
    """get_pending() should return only unapplied migrations."""
    runner = MigrationRunner(db)
    for m in _sample_migrations():
        runner.register(m)

    # Apply only version 1
    await runner.migrate_up(target_version=1)
    pending = await runner.get_pending()
    assert len(pending) == 1
    assert pending[0].version == 2


async def test_migration_migrate_down(db):
    """migrate_down() should revert migrations above the target version."""
    runner = MigrationRunner(db)
    for m in _sample_migrations():
        runner.register(m)

    await runner.migrate_up()
    assert await db.table_exists("posts") is True

    reverted = await runner.migrate_down(target_version=1)
    assert reverted == 1
    assert await runner.get_current_version() == 1
    assert await db.table_exists("posts") is False
    assert await db.table_exists("users") is True


async def test_migration_idempotent(db):
    """Running migrate_up() twice should not fail or double-apply."""
    runner = MigrationRunner(db)
    for m in _sample_migrations():
        runner.register(m)

    applied1 = await runner.migrate_up()
    applied2 = await runner.migrate_up()
    assert applied1 == 2
    assert applied2 == 0
    assert await runner.get_current_version() == 2


async def test_migration_out_of_order_registration(db):
    """Migrations registered out of order are sorted correctly."""
    runner = MigrationRunner(db)
    runner.register(Migration(version=3, name="v3", sql_up="CREATE TABLE t3 (id INTEGER)", sql_down="DROP TABLE t3"))
    runner.register(Migration(version=1, name="v1", sql_up="CREATE TABLE t1 (id INTEGER)", sql_down="DROP TABLE t1"))
    runner.register(Migration(version=2, name="v2", sql_up="CREATE TABLE t2 (id INTEGER)", sql_down="DROP TABLE t2"))
    applied = await runner.migrate_up()
    assert applied == 3
    assert await runner.get_current_version() == 3


async def test_migration_down_to_zero(db):
    """migrate_down(0) reverts all migrations."""
    runner = MigrationRunner(db)
    runner.register(Migration(version=1, name="v1", sql_up="CREATE TABLE t1 (id INTEGER)", sql_down="DROP TABLE t1"))
    runner.register(Migration(version=2, name="v2", sql_up="CREATE TABLE t2 (id INTEGER)", sql_down="DROP TABLE t2"))
    await runner.migrate_up()
    reverted = await runner.migrate_down(target_version=0)
    assert reverted == 2
    assert await runner.get_current_version() == 0
    assert not await db.table_exists("t1")
    assert not await db.table_exists("t2")


async def test_migration_sql_failure_is_atomic(db):
    """If a migration fails, no partial state remains."""
    runner = MigrationRunner(db)
    runner.register(Migration(version=1, name="v1", sql_up="CREATE TABLE t1 (id INTEGER)", sql_down="DROP TABLE t1"))
    runner.register(Migration(version=2, name="v2_bad", sql_up="INVALID SQL THAT WILL FAIL", sql_down="SELECT 1"))
    with pytest.raises(Exception):
        await runner.migrate_up()
    # Since migrations are wrapped in a transaction, v1 should also be rolled back
    version = await runner.get_current_version()
    assert version == 0  # nothing applied because entire transaction rolled back
    assert not await db.table_exists("t1")  # t1 was rolled back too
