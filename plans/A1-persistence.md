# Phase A1: Persistence Module Implementation

## Context

**Phase:** A1 (first implementation phase)
**Module:** `terrarium/persistence/`
**Depends on:** Nothing (zero external dependencies)
**Goal:** A working async SQLite persistence layer that all other modules will use for database operations.

**After this phase:** We can create tables, CRUD rows, run migrations, and take/restore snapshots — all async, all tested.

**Status doc update:** After completion, update `IMPLEMENTATION_STATUS.md`:
- Flip persistence files from `📋 stub` to `✅ done`
- Add session log entry
- Note any decisions or issues

**Plans folder:** Save this plan to `plans/A1-persistence.md` in the project repo.

---

## What Exists (skeleton)

| File | Classes | Methods (all `...` bodies) |
|------|---------|---------------------------|
| `database.py` | `Database(ABC)` | execute, executemany, fetchone, fetchall, transaction, close, table_exists |
| `sqlite.py` | `SQLiteDatabase(Database)` | connect + all ABC methods + backup, vacuum |
| `manager.py` | `ConnectionManager` | initialize, shutdown, get_connection, health_check |
| `migrations.py` | `Migration(BaseModel)`, `MigrationRunner` | register, get_current_version, migrate_up, migrate_down, get_pending |
| `snapshot.py` | `SnapshotStore` | save_snapshot, load_snapshot, list_snapshots, delete_snapshot, get_snapshot_metadata |
| `config.py` | `PersistenceConfig(BaseModel)` | Fields: base_dir, wal_mode, max_connections, migration_auto_run, backup_interval_seconds |

Tests: 12 test stubs across 4 files (test_manager, test_sqlite, test_migrations, test_snapshot).

---

## Implementation Order

### Step 1: `config.py` — Already complete
PersistenceConfig is a Pydantic model with defaults. The skeleton already has all fields. Just verify it works.

### Step 2: `database.py` — Already complete (ABC)
Database ABC defines the interface. No implementation needed — it's abstract. Just verify the ABC works correctly (can't instantiate, subclass must implement all methods).

### Step 3: `sqlite.py` — Core implementation

This is the main work. Implement `SQLiteDatabase` using `aiosqlite`:

```python
class SQLiteDatabase(Database):
    def __init__(self, db_path: str, wal_mode: bool = True):
        self._db_path = db_path
        self._wal_mode = wal_mode
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row  # dict-like rows
        if self._wal_mode:
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")

    async def execute(self, sql, params=None) -> Any:
        cursor = await self._conn.execute(sql, params or ())
        await self._conn.commit()
        return cursor

    async def executemany(self, sql, params_list) -> None:
        await self._conn.executemany(sql, params_list)
        await self._conn.commit()

    async def fetchone(self, sql, params=None) -> dict | None:
        cursor = await self._conn.execute(sql, params or ())
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def fetchall(self, sql, params=None) -> list[dict]:
        cursor = await self._conn.execute(sql, params or ())
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    @asynccontextmanager
    async def transaction(self):
        await self._conn.execute("BEGIN")
        try:
            yield
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def table_exists(self, table_name: str) -> bool:
        row = await self.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return row is not None

    async def backup(self, target_path: str) -> None:
        async with aiosqlite.connect(target_path) as target:
            await self._conn.backup(target)

    async def vacuum(self) -> None:
        await self._conn.execute("VACUUM")
```

**Key decisions:**
- Use `aiosqlite.Row` for dict-like row access
- WAL mode + SYNCHRONOUS=NORMAL for concurrent reads + decent write performance
- Foreign keys ON by default
- Transactions via context manager with explicit BEGIN/COMMIT/ROLLBACK
- Supports both file-based and `:memory:` databases

### Step 4: `migrations.py` — Schema migration system

```python
class MigrationRunner:
    def __init__(self, db: Database):
        self._db = db
        self._migrations: list[Migration] = []

    def register(self, migration: Migration) -> None:
        self._migrations.append(migration)
        self._migrations.sort(key=lambda m: m.version)

    async def _ensure_migrations_table(self) -> None:
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

    async def get_current_version(self) -> int:
        await self._ensure_migrations_table()
        row = await self._db.fetchone("SELECT MAX(version) as v FROM _migrations")
        return row["v"] if row and row["v"] is not None else 0

    async def migrate_up(self, target_version: int | None = None) -> int:
        await self._ensure_migrations_table()
        current = await self.get_current_version()
        applied = 0
        for m in self._migrations:
            if m.version <= current:
                continue
            if target_version and m.version > target_version:
                break
            await self._db.execute(m.sql_up)
            await self._db.execute(
                "INSERT INTO _migrations (version, name) VALUES (?, ?)",
                (m.version, m.name)
            )
            applied += 1
        return applied

    async def migrate_down(self, target_version: int) -> int:
        current = await self.get_current_version()
        reverted = 0
        for m in reversed(self._migrations):
            if m.version <= target_version:
                break
            if m.version > current:
                continue
            await self._db.execute(m.sql_down)
            await self._db.execute("DELETE FROM _migrations WHERE version = ?", (m.version,))
            reverted += 1
        return reverted

    async def get_pending(self) -> list[Migration]:
        current = await self.get_current_version()
        return [m for m in self._migrations if m.version > current]
```

### Step 5: `manager.py` — Connection manager

```python
class ConnectionManager:
    def __init__(self, config: PersistenceConfig):
        self._config = config
        self._connections: dict[str, SQLiteDatabase] = {}

    async def initialize(self) -> None:
        Path(self._config.base_dir).mkdir(parents=True, exist_ok=True)

    async def shutdown(self) -> None:
        for db in self._connections.values():
            await db.close()
        self._connections.clear()

    async def get_connection(self, db_name: str) -> Database:
        if db_name not in self._connections:
            db_path = str(Path(self._config.base_dir) / f"{db_name}.db")
            db = SQLiteDatabase(db_path, wal_mode=self._config.wal_mode)
            await db.connect()
            self._connections[db_name] = db
        return self._connections[db_name]

    async def health_check(self) -> dict[str, Any]:
        results = {}
        for name, db in self._connections.items():
            try:
                await db.fetchone("SELECT 1 as ok")
                results[name] = {"status": "healthy"}
            except Exception as e:
                results[name] = {"status": "unhealthy", "error": str(e)}
        return {"connections": results, "count": len(self._connections)}
```

### Step 6: `snapshot.py` — Snapshot store

```python
class SnapshotStore:
    def __init__(self, config: PersistenceConfig):
        self._config = config
        self._snapshot_dir = Path(config.base_dir) / "snapshots"

    async def save_snapshot(self, run_id: RunId, label: str, db: Database) -> SnapshotId:
        snapshot_id = SnapshotId(f"snap_{run_id}_{label}_{uuid4().hex[:8]}")
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        target = self._snapshot_dir / f"{snapshot_id}.db"
        await db.backup(str(target))
        # Save metadata
        meta = {"snapshot_id": snapshot_id, "run_id": run_id, "label": label,
                "created_at": datetime.now(UTC).isoformat()}
        (self._snapshot_dir / f"{snapshot_id}.json").write_text(json.dumps(meta))
        return snapshot_id

    async def load_snapshot(self, snapshot_id: SnapshotId) -> Database:
        source = self._snapshot_dir / f"{snapshot_id}.db"
        if not source.exists():
            raise FileNotFoundError(f"Snapshot {snapshot_id} not found")
        db = SQLiteDatabase(str(source), wal_mode=self._config.wal_mode)
        await db.connect()
        return db

    async def list_snapshots(self, run_id: RunId | None = None) -> list[dict]:
        results = []
        for meta_file in self._snapshot_dir.glob("*.json"):
            meta = json.loads(meta_file.read_text())
            if run_id is None or meta.get("run_id") == run_id:
                results.append(meta)
        return sorted(results, key=lambda m: m["created_at"])

    async def delete_snapshot(self, snapshot_id: SnapshotId) -> None:
        (self._snapshot_dir / f"{snapshot_id}.db").unlink(missing_ok=True)
        (self._snapshot_dir / f"{snapshot_id}.json").unlink(missing_ok=True)

    async def get_snapshot_metadata(self, snapshot_id: SnapshotId) -> dict:
        meta_file = self._snapshot_dir / f"{snapshot_id}.json"
        if not meta_file.exists():
            raise FileNotFoundError(f"Snapshot metadata for {snapshot_id} not found")
        return json.loads(meta_file.read_text())
```

---

## Tests to Implement

### `tests/persistence/test_sqlite.py`

```python
@pytest.fixture
async def db(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "test.db"))
    await db.connect()
    yield db
    await db.close()

async def test_sqlite_connect(db):
    # Verify connection is open, WAL mode is set
    row = await db.fetchone("PRAGMA journal_mode")
    assert row["journal_mode"] == "wal"

async def test_sqlite_execute(db):
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    await db.execute("INSERT INTO t (name) VALUES (?)", ("hello",))
    row = await db.fetchone("SELECT name FROM t WHERE id = 1")
    assert row["name"] == "hello"

async def test_sqlite_fetchone(db):
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    assert await db.fetchone("SELECT * FROM t") is None  # empty
    await db.execute("INSERT INTO t (val) VALUES (?)", ("x",))
    row = await db.fetchone("SELECT * FROM t")
    assert row is not None and row["val"] == "x"

async def test_sqlite_fetchall(db):
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    await db.execute("INSERT INTO t (val) VALUES (?)", ("a",))
    await db.execute("INSERT INTO t (val) VALUES (?)", ("b",))
    rows = await db.fetchall("SELECT val FROM t ORDER BY val")
    assert len(rows) == 2
    assert rows[0]["val"] == "a"

async def test_sqlite_transaction(db):
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, val TEXT)")
    # Successful transaction
    async with db.transaction():
        await db.execute("INSERT INTO t (val) VALUES (?)", ("committed",))
    assert (await db.fetchone("SELECT val FROM t"))["val"] == "committed"
    # Failed transaction (rollback)
    try:
        async with db.transaction():
            await db.execute("INSERT INTO t (val) VALUES (?)", ("rolled_back",))
            raise ValueError("force rollback")
    except ValueError:
        pass
    rows = await db.fetchall("SELECT val FROM t")
    assert len(rows) == 1  # rolled_back row should not exist

async def test_sqlite_table_exists(db):
    assert not await db.table_exists("nonexistent")
    await db.execute("CREATE TABLE real_table (id INTEGER)")
    assert await db.table_exists("real_table")
```

### `tests/persistence/test_migrations.py`

```python
async def test_migration_register(db):
    runner = MigrationRunner(db)
    runner.register(Migration(version=1, name="create_users", sql_up="CREATE TABLE users (id INTEGER)", sql_down="DROP TABLE users"))
    assert len(runner._migrations) == 1

async def test_migration_get_current_version(db):
    runner = MigrationRunner(db)
    assert await runner.get_current_version() == 0

async def test_migration_migrate_up(db):
    runner = MigrationRunner(db)
    runner.register(Migration(version=1, name="v1", sql_up="CREATE TABLE t1 (id INTEGER)", sql_down="DROP TABLE t1"))
    runner.register(Migration(version=2, name="v2", sql_up="CREATE TABLE t2 (id INTEGER)", sql_down="DROP TABLE t2"))
    applied = await runner.migrate_up()
    assert applied == 2
    assert await runner.get_current_version() == 2
    assert await db.table_exists("t1")
    assert await db.table_exists("t2")

async def test_migration_get_pending(db):
    runner = MigrationRunner(db)
    runner.register(Migration(version=1, name="v1", sql_up="CREATE TABLE t1 (id INTEGER)", sql_down="DROP TABLE t1"))
    runner.register(Migration(version=2, name="v2", sql_up="CREATE TABLE t2 (id INTEGER)", sql_down="DROP TABLE t2"))
    pending = await runner.get_pending()
    assert len(pending) == 2
    await runner.migrate_up(target_version=1)
    pending = await runner.get_pending()
    assert len(pending) == 1
```

### `tests/persistence/test_manager.py`

```python
async def test_connection_manager_initialize(tmp_path):
    config = PersistenceConfig(base_dir=str(tmp_path / "data"))
    mgr = ConnectionManager(config)
    await mgr.initialize()
    assert (tmp_path / "data").exists()
    await mgr.shutdown()

async def test_connection_manager_get_connection(tmp_path):
    config = PersistenceConfig(base_dir=str(tmp_path / "data"))
    mgr = ConnectionManager(config)
    await mgr.initialize()
    db = await mgr.get_connection("test")
    assert isinstance(db, SQLiteDatabase)
    # Same name returns same connection
    db2 = await mgr.get_connection("test")
    assert db is db2
    await mgr.shutdown()

async def test_connection_manager_health_check(tmp_path):
    config = PersistenceConfig(base_dir=str(tmp_path / "data"))
    mgr = ConnectionManager(config)
    await mgr.initialize()
    await mgr.get_connection("test")
    health = await mgr.health_check()
    assert health["connections"]["test"]["status"] == "healthy"
    await mgr.shutdown()
```

### `tests/persistence/test_snapshot.py`

```python
async def test_save_snapshot(tmp_path):
    config = PersistenceConfig(base_dir=str(tmp_path))
    db = SQLiteDatabase(str(tmp_path / "world.db"))
    await db.connect()
    await db.execute("CREATE TABLE entities (id TEXT, data TEXT)")
    await db.execute("INSERT INTO entities VALUES (?, ?)", ("e1", "hello"))
    store = SnapshotStore(config)
    snap_id = await store.save_snapshot(RunId("run1"), "checkpoint", db)
    assert snap_id is not None
    await db.close()

async def test_load_snapshot(tmp_path):
    config = PersistenceConfig(base_dir=str(tmp_path))
    db = SQLiteDatabase(str(tmp_path / "world.db"))
    await db.connect()
    await db.execute("CREATE TABLE entities (id TEXT, data TEXT)")
    await db.execute("INSERT INTO entities VALUES (?, ?)", ("e1", "original"))
    store = SnapshotStore(config)
    snap_id = await store.save_snapshot(RunId("run1"), "before_change", db)
    # Modify original
    await db.execute("UPDATE entities SET data = ? WHERE id = ?", ("modified", "e1"))
    # Load snapshot — should have original data
    restored = await store.load_snapshot(snap_id)
    row = await restored.fetchone("SELECT data FROM entities WHERE id = ?", ("e1",))
    assert row["data"] == "original"
    await db.close()
    await restored.close()

async def test_list_snapshots(tmp_path):
    config = PersistenceConfig(base_dir=str(tmp_path))
    db = SQLiteDatabase(str(tmp_path / "world.db"))
    await db.connect()
    store = SnapshotStore(config)
    await store.save_snapshot(RunId("run1"), "a", db)
    await store.save_snapshot(RunId("run1"), "b", db)
    await store.save_snapshot(RunId("run2"), "c", db)
    all_snaps = await store.list_snapshots()
    assert len(all_snaps) == 3
    run1_snaps = await store.list_snapshots(RunId("run1"))
    assert len(run1_snaps) == 2
    await db.close()
```

### `tests/conftest.py` — Update temp_sqlite_db fixture

```python
@pytest.fixture
async def temp_sqlite_db(tmp_path):
    from terrarium.persistence.sqlite import SQLiteDatabase
    db = SQLiteDatabase(str(tmp_path / "test.db"))
    await db.connect()
    yield db
    await db.close()
```

---

## Files to Modify / Create

| File | Action | Tests |
|------|--------|-------|
| `terrarium/persistence/config.py` | **VERIFY** — Pydantic defaults correct | test_config.py (2 tests) |
| `terrarium/persistence/database.py` | **VERIFY** — ABC correct, add `self` params if missing | test_database.py (1 test) |
| `terrarium/persistence/sqlite.py` | **IMPLEMENT** — full SQLiteDatabase (10 methods) | test_sqlite.py (11 tests) |
| `terrarium/persistence/migrations.py` | **IMPLEMENT** — MigrationRunner (6 methods) | test_migrations.py (6 tests) |
| `terrarium/persistence/manager.py` | **IMPLEMENT** — ConnectionManager (4 methods) | test_manager.py (3 tests) |
| `terrarium/persistence/snapshot.py` | **IMPLEMENT** — SnapshotStore (5 methods) | test_snapshot.py (5 tests) |
| `tests/persistence/test_config.py` | **CREATE** — new test file | 2 tests |
| `tests/persistence/test_database.py` | **CREATE** — new test file | 1 test |
| `tests/persistence/test_sqlite.py` | **IMPLEMENT** — replace stubs with real tests | 11 tests |
| `tests/persistence/test_migrations.py` | **IMPLEMENT** — replace stubs with real tests | 6 tests |
| `tests/persistence/test_manager.py` | **IMPLEMENT** — replace stubs with real tests | 3 tests |
| `tests/persistence/test_snapshot.py` | **IMPLEMENT** — replace stubs with real tests | 5 tests |
| `tests/conftest.py` | **UPDATE** — implement temp_sqlite_db fixture | — |
| `IMPLEMENTATION_STATUS.md` | **UPDATE** — flip persistence to ✅ done, add session log | — |
| `plans/A1-persistence.md` | **CREATE** — copy of this plan in project repo | — |

**Totals: 6 source files implemented, 6 test files (28+ tests), 0 stubs remaining after completion.**

---

## Additional Tests Required

### `tests/persistence/test_config.py` (NEW — not in original skeleton, add it)

```python
def test_persistence_config_defaults():
    config = PersistenceConfig()
    assert config.base_dir == "terrarium_data"
    assert config.wal_mode is True
    assert config.max_connections == 5
    assert config.migration_auto_run is True

def test_persistence_config_custom():
    config = PersistenceConfig(base_dir="/tmp/custom", wal_mode=False, max_connections=10)
    assert config.base_dir == "/tmp/custom"
    assert config.wal_mode is False
```

### `tests/persistence/test_sqlite.py` — Additional tests

```python
async def test_sqlite_memory_database():
    db = SQLiteDatabase(":memory:")
    await db.connect()
    await db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    assert await db.table_exists("t")
    await db.close()

async def test_sqlite_backup(db, tmp_path):
    await db.execute("CREATE TABLE t (id INTEGER, val TEXT)")
    await db.execute("INSERT INTO t VALUES (1, 'hello')")
    backup_path = str(tmp_path / "backup.db")
    await db.backup(backup_path)
    # Verify backup has the data
    backup = SQLiteDatabase(backup_path, wal_mode=False)
    await backup.connect()
    row = await backup.fetchone("SELECT val FROM t WHERE id = 1")
    assert row["val"] == "hello"
    await backup.close()

async def test_sqlite_vacuum(db):
    await db.execute("CREATE TABLE t (id INTEGER)")
    await db.vacuum()  # Should not raise

async def test_sqlite_executemany(db):
    await db.execute("CREATE TABLE t (id INTEGER, val TEXT)")
    await db.executemany("INSERT INTO t VALUES (?, ?)", [(1, "a"), (2, "b"), (3, "c")])
    rows = await db.fetchall("SELECT * FROM t ORDER BY id")
    assert len(rows) == 3

async def test_sqlite_close_and_reopen(tmp_path):
    path = str(tmp_path / "reopen.db")
    db = SQLiteDatabase(path)
    await db.connect()
    await db.execute("CREATE TABLE t (val TEXT)")
    await db.execute("INSERT INTO t VALUES (?)", ("persisted",))
    await db.close()
    # Reopen
    db2 = SQLiteDatabase(path)
    await db2.connect()
    row = await db2.fetchone("SELECT val FROM t")
    assert row["val"] == "persisted"
    await db2.close()
```

### `tests/persistence/test_migrations.py` — Additional tests

```python
async def test_migration_migrate_down(db):
    runner = MigrationRunner(db)
    runner.register(Migration(version=1, name="v1", sql_up="CREATE TABLE t1 (id INTEGER)", sql_down="DROP TABLE t1"))
    runner.register(Migration(version=2, name="v2", sql_up="CREATE TABLE t2 (id INTEGER)", sql_down="DROP TABLE t2"))
    await runner.migrate_up()
    assert await db.table_exists("t2")
    reverted = await runner.migrate_down(target_version=1)
    assert reverted == 1
    assert not await db.table_exists("t2")
    assert await db.table_exists("t1")

async def test_migration_idempotent(db):
    runner = MigrationRunner(db)
    runner.register(Migration(version=1, name="v1", sql_up="CREATE TABLE t1 (id INTEGER)", sql_down="DROP TABLE t1"))
    await runner.migrate_up()
    applied = await runner.migrate_up()  # Run again — should do nothing
    assert applied == 0
```

### `tests/persistence/test_snapshot.py` — Additional tests

```python
async def test_delete_snapshot(tmp_path):
    config = PersistenceConfig(base_dir=str(tmp_path))
    db = SQLiteDatabase(str(tmp_path / "world.db"))
    await db.connect()
    store = SnapshotStore(config)
    snap_id = await store.save_snapshot(RunId("run1"), "del_me", db)
    snaps = await store.list_snapshots()
    assert len(snaps) == 1
    await store.delete_snapshot(snap_id)
    snaps = await store.list_snapshots()
    assert len(snaps) == 0
    await db.close()

async def test_get_snapshot_metadata(tmp_path):
    config = PersistenceConfig(base_dir=str(tmp_path))
    db = SQLiteDatabase(str(tmp_path / "world.db"))
    await db.connect()
    store = SnapshotStore(config)
    snap_id = await store.save_snapshot(RunId("run1"), "meta_test", db)
    meta = await store.get_snapshot_metadata(snap_id)
    assert meta["run_id"] == "run1"
    assert meta["label"] == "meta_test"
    assert "created_at" in meta
    await db.close()
```

### `tests/persistence/test_database.py` (NEW — verify ABC)

```python
import pytest
from terrarium.persistence.database import Database

def test_database_abc_cannot_instantiate():
    with pytest.raises(TypeError):
        Database()
```

---

## Completion Criteria (Zero Stubs)

**After this phase completes, the following must be true:**

1. **Every method in every file in `terrarium/persistence/` has a real implementation.** No `...` bodies remain. Zero stubs.
2. **Every file has matching tests that exercise all public methods.**
3. **Coverage > 90%** for the persistence module (critical infrastructure).

### File-by-file completion checklist:

| File | Methods | All Implemented? | All Tested? |
|------|---------|-----------------|-------------|
| `config.py` | PersistenceConfig fields | ✅ (Pydantic defaults) | ✅ test_config.py |
| `database.py` | 7 abstract methods | ✅ (ABC, no impl needed) | ✅ test_database.py (can't instantiate) |
| `sqlite.py` | connect, execute, executemany, fetchone, fetchall, transaction, close, table_exists, backup, vacuum | ✅ all 10 methods | ✅ test_sqlite.py (11 tests) |
| `migrations.py` | register, get_current_version, migrate_up, migrate_down, get_pending, _ensure_migrations_table | ✅ all 6 methods | ✅ test_migrations.py (6 tests) |
| `manager.py` | initialize, shutdown, get_connection, health_check | ✅ all 4 methods | ✅ test_manager.py (3 tests) |
| `snapshot.py` | save_snapshot, load_snapshot, list_snapshots, delete_snapshot, get_snapshot_metadata | ✅ all 5 methods | ✅ test_snapshot.py (5 tests) |
| `__init__.py` | re-exports 7 symbols | ✅ verified by import test | ✅ |

**Total: 6 implementation files, ~30 methods, ~30 tests, 0 stubs remaining.**

---

## Verification

1. `.venv/bin/python -m pytest tests/persistence/ -v` — ALL tests pass (0 failures)
2. `.venv/bin/python -m pytest tests/persistence/ --cov=terrarium/persistence --cov-report=term-missing` — coverage > 90%
3. `grep -r "^\s*\.\.\." terrarium/persistence/*.py` — returns 0 results (no stubs remaining)
4. Import smoke test:
   ```python
   from terrarium.persistence import SQLiteDatabase, ConnectionManager, PersistenceConfig, MigrationRunner, SnapshotStore, Migration, Database
   ```
5. IMPLEMENTATION_STATUS.md updated: persistence files → `✅ done`, session log entry added
6. `plans/A1-persistence.md` saved in project repo
