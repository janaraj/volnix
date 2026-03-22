"""Tests for terrarium.persistence.manager — database connection management."""
import pytest
from terrarium.persistence.config import PersistenceConfig
from terrarium.persistence.manager import ConnectionManager


async def test_connection_manager_initialize(tmp_path):
    """initialize() should create the base directory."""
    base = tmp_path / "data"
    cfg = PersistenceConfig(base_dir=str(base))
    mgr = ConnectionManager(cfg)

    await mgr.initialize()
    assert base.exists() and base.is_dir()
    await mgr.shutdown()


async def test_connection_manager_get_connection(tmp_path):
    """get_connection() should create and cache database connections."""
    cfg = PersistenceConfig(base_dir=str(tmp_path))
    mgr = ConnectionManager(cfg)
    await mgr.initialize()

    db1 = await mgr.get_connection("events")
    db2 = await mgr.get_connection("events")
    assert db1 is db2  # same cached instance

    # Should be usable
    await db1.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    assert await db1.table_exists("t") is True

    await mgr.shutdown()


async def test_connection_manager_health_check(tmp_path):
    """health_check() should report healthy for active connections."""
    cfg = PersistenceConfig(base_dir=str(tmp_path))
    mgr = ConnectionManager(cfg)
    await mgr.initialize()

    await mgr.get_connection("ledger")
    await mgr.get_connection("state")

    health = await mgr.health_check()
    assert health["count"] == 2
    assert "ledger" in health["connections"]
    assert health["connections"]["ledger"]["status"] == "healthy"
    assert "state" in health["connections"]
    assert health["connections"]["state"]["status"] == "healthy"

    await mgr.shutdown()


async def test_connection_manager_shutdown_closes_all(tmp_path):
    """shutdown() actually closes all connections."""
    config = PersistenceConfig(base_dir=str(tmp_path / "data"))
    mgr = ConnectionManager(config)
    await mgr.initialize()
    db1 = await mgr.get_connection("db1")
    db2 = await mgr.get_connection("db2")
    await mgr.shutdown()
    # After shutdown, the internal dict should be empty
    assert len(mgr._connections) == 0
    # Connections should be closed (accessing them should fail)
    with pytest.raises(RuntimeError, match="not connected"):
        await db1.execute("SELECT 1")


async def test_connection_manager_multiple_named_connections(tmp_path):
    """Different names create different databases."""
    config = PersistenceConfig(base_dir=str(tmp_path / "data"))
    mgr = ConnectionManager(config)
    await mgr.initialize()
    events_db = await mgr.get_connection("events")
    state_db = await mgr.get_connection("state")
    assert events_db is not state_db
    # They're independent databases
    await events_db.execute("CREATE TABLE e (id INTEGER)")
    assert await events_db.table_exists("e")
    assert not await state_db.table_exists("e")
    await mgr.shutdown()


async def test_connection_manager_health_check_empty(tmp_path):
    """health_check with no connections returns empty."""
    config = PersistenceConfig(base_dir=str(tmp_path / "data"))
    mgr = ConnectionManager(config)
    await mgr.initialize()
    health = await mgr.health_check()
    assert health["count"] == 0
    assert health["connections"] == {}
    await mgr.shutdown()
