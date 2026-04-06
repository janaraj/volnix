"""Tests for volnix.persistence.sqlite — SQLite adapter operations."""
import pytest
from volnix.persistence.sqlite import SQLiteDatabase


@pytest.fixture
async def db(tmp_path):
    """Create a temporary SQLite database for each test."""
    database = SQLiteDatabase(str(tmp_path / "test.db"))
    await database.connect()
    yield database
    await database.close()


async def test_sqlite_connect(tmp_path):
    """connect() should open the database and enable foreign keys."""
    database = SQLiteDatabase(str(tmp_path / "conn.db"))
    await database.connect()
    row = await database.fetchone("PRAGMA foreign_keys")
    assert row is not None
    assert row["foreign_keys"] == 1
    await database.close()


async def test_sqlite_execute(db):
    """execute() should run DDL and DML statements."""
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    await db.execute("INSERT INTO t (val) VALUES (?)", ("hello",))
    row = await db.fetchone("SELECT val FROM t WHERE id = 1")
    assert row is not None
    assert row["val"] == "hello"


async def test_sqlite_fetchone(db):
    """fetchone() should return a dict or None."""
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    result = await db.fetchone("SELECT * FROM t WHERE id = 999")
    assert result is None

    await db.execute("INSERT INTO t (val) VALUES (?)", ("x",))
    result = await db.fetchone("SELECT * FROM t")
    assert result is not None
    assert result["val"] == "x"


async def test_sqlite_fetchall(db):
    """fetchall() should return a list of dicts."""
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    await db.execute("INSERT INTO t (val) VALUES (?)", ("a",))
    await db.execute("INSERT INTO t (val) VALUES (?)", ("b",))
    rows = await db.fetchall("SELECT val FROM t ORDER BY val")
    assert len(rows) == 2
    assert rows[0]["val"] == "a"
    assert rows[1]["val"] == "b"


async def test_sqlite_transaction(db):
    """transaction() should commit on success and rollback on failure."""
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")

    # Successful transaction
    async with db.transaction():
        await db.execute("INSERT INTO t (val) VALUES (?)", ("committed",))
    rows = await db.fetchall("SELECT val FROM t")
    assert len(rows) == 1

    # Failed transaction should rollback
    with pytest.raises(ValueError, match="rollback"):
        async with db.transaction():
            await db.execute("INSERT INTO t (val) VALUES (?)", ("rolledback",))
            raise ValueError("rollback")

    rows = await db.fetchall("SELECT val FROM t")
    assert len(rows) == 1
    assert rows[0]["val"] == "committed"


async def test_sqlite_table_exists(db):
    """table_exists() should detect created tables."""
    assert await db.table_exists("nonexistent") is False
    await db.execute("CREATE TABLE my_table (id INTEGER PRIMARY KEY)")
    assert await db.table_exists("my_table") is True


async def test_sqlite_memory_database():
    """In-memory databases should work without WAL mode."""
    db = SQLiteDatabase(":memory:", wal_mode=False)
    await db.connect()
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    assert await db.table_exists("t") is True
    await db.close()


async def test_sqlite_backup(db, tmp_path):
    """backup() should create a usable copy of the database."""
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    await db.execute("INSERT INTO t (val) VALUES (?)", ("original",))

    backup_path = str(tmp_path / "backup.db")
    await db.backup(backup_path)

    backup_db = SQLiteDatabase(backup_path)
    await backup_db.connect()
    row = await backup_db.fetchone("SELECT val FROM t")
    assert row is not None
    assert row["val"] == "original"
    await backup_db.close()


async def test_sqlite_vacuum(db):
    """vacuum() should run without errors."""
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    await db.execute("INSERT INTO t (val) VALUES (?)", ("data",))
    await db.execute("DELETE FROM t")
    await db.vacuum()  # Should not raise


async def test_sqlite_executemany(db):
    """executemany() should insert multiple rows in one call."""
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    await db.executemany(
        "INSERT INTO t (val) VALUES (?)",
        [("a",), ("b",), ("c",)],
    )
    rows = await db.fetchall("SELECT val FROM t ORDER BY val")
    assert len(rows) == 3
    assert [r["val"] for r in rows] == ["a", "b", "c"]


async def test_sqlite_close_and_reopen(tmp_path):
    """Database should be usable after close and reconnect."""
    path = str(tmp_path / "reopen.db")

    db = SQLiteDatabase(path)
    await db.connect()
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    await db.execute("INSERT INTO t (val) VALUES (?)", ("persist",))
    await db.close()

    db2 = SQLiteDatabase(path)
    await db2.connect()
    row = await db2.fetchone("SELECT val FROM t")
    assert row is not None
    assert row["val"] == "persist"
    await db2.close()


async def test_sqlite_operations_on_closed_db(tmp_path):
    """Calling methods on a closed database raises RuntimeError."""
    db = SQLiteDatabase(str(tmp_path / "closed.db"))
    await db.connect()
    await db.close()
    with pytest.raises(RuntimeError, match="not connected"):
        await db.execute("SELECT 1")
    with pytest.raises(RuntimeError, match="not connected"):
        await db.fetchone("SELECT 1")
    with pytest.raises(RuntimeError, match="not connected"):
        await db.fetchall("SELECT 1")


async def test_sqlite_parameterized_queries(db):
    """Parameter binding works correctly for queries."""
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)")
    await db.execute("INSERT INTO t (name, age) VALUES (?, ?)", ("alice", 30))
    await db.execute("INSERT INTO t (name, age) VALUES (?, ?)", ("bob", 25))
    row = await db.fetchone("SELECT name FROM t WHERE age = ?", (30,))
    assert row["name"] == "alice"
    rows = await db.fetchall("SELECT name FROM t WHERE age > ?", (20,))
    assert len(rows) == 2


async def test_sqlite_wal_mode_verified(tmp_path):
    """WAL mode is actually set on file-based databases."""
    db = SQLiteDatabase(str(tmp_path / "wal_test.db"), wal_mode=True)
    await db.connect()
    row = await db.fetchone("PRAGMA journal_mode")
    assert row["journal_mode"] == "wal"
    await db.close()


async def test_sqlite_wal_mode_skipped_for_memory():
    """WAL mode is not set for :memory: databases."""
    db = SQLiteDatabase(":memory:", wal_mode=True)
    await db.connect()
    # :memory: databases use "memory" journal mode regardless
    row = await db.fetchone("PRAGMA journal_mode")
    assert row["journal_mode"] == "memory"
    await db.close()


async def test_sqlite_foreign_key_enforcement(db):
    """Foreign key constraints are enforced."""
    await db.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
    await db.execute("CREATE TABLE child (id INTEGER, parent_id INTEGER REFERENCES parent(id))")
    await db.execute("INSERT INTO parent VALUES (1)")
    await db.execute("INSERT INTO child VALUES (1, 1)")  # valid FK
    with pytest.raises(Exception):  # IntegrityError via aiosqlite
        await db.execute("INSERT INTO child VALUES (2, 999)")  # invalid FK


async def test_sqlite_null_handling(db):
    """NULL values are handled correctly."""
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    await db.execute("INSERT INTO t (val) VALUES (?)", (None,))
    row = await db.fetchone("SELECT val FROM t WHERE id = 1")
    assert row["val"] is None


async def test_sqlite_malformed_sql(db):
    """Malformed SQL raises an exception."""
    with pytest.raises(Exception):
        await db.execute("THIS IS NOT SQL")
