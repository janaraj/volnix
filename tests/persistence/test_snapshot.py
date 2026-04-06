"""Tests for volnix.persistence.snapshot — state snapshot save/load."""

import pytest

from volnix.core.types import RunId, SnapshotId
from volnix.persistence.config import PersistenceConfig
from volnix.persistence.snapshot import SnapshotStore
from volnix.persistence.sqlite import SQLiteDatabase


@pytest.fixture
async def snapshot_env(tmp_path):
    """Create a snapshot store and a source database for testing."""
    cfg = PersistenceConfig(base_dir=str(tmp_path / "data"))
    store = SnapshotStore(cfg)

    db = SQLiteDatabase(str(tmp_path / "source.db"))
    await db.connect()
    await db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    await db.execute("INSERT INTO items (name) VALUES (?)", ("alpha",))

    yield store, db

    await db.close()


async def test_save_snapshot(snapshot_env):
    """save_snapshot() should create .db and .json files."""
    store, db = snapshot_env
    run_id = RunId("run-1")
    sid = await store.save_snapshot(run_id, "checkpoint-1", db)
    assert isinstance(sid, str)
    assert len(sid) > 0

    # Metadata file should exist
    meta = await store.get_snapshot_metadata(SnapshotId(sid))
    assert meta["run_id"] == "run-1"
    assert meta["label"] == "checkpoint-1"
    assert "timestamp" in meta
    assert meta["size_bytes"] > 0


async def test_load_snapshot(snapshot_env):
    """load_snapshot() should return a usable database."""
    store, db = snapshot_env
    run_id = RunId("run-1")
    sid = await store.save_snapshot(run_id, "load-test", db)

    loaded = await store.load_snapshot(SnapshotId(sid))
    try:
        row = await loaded.fetchone("SELECT name FROM items")
        assert row is not None
        assert row["name"] == "alpha"
    finally:
        await loaded.close()


async def test_list_snapshots(snapshot_env):
    """list_snapshots() should filter by run_id when provided."""
    store, db = snapshot_env

    await store.save_snapshot(RunId("run-A"), "snap-a", db)
    await store.save_snapshot(RunId("run-B"), "snap-b", db)

    all_snaps = await store.list_snapshots()
    assert len(all_snaps) == 2

    run_a_snaps = await store.list_snapshots(run_id=RunId("run-A"))
    assert len(run_a_snaps) == 1
    assert run_a_snaps[0]["run_id"] == "run-A"


async def test_delete_snapshot(snapshot_env):
    """delete_snapshot() should remove the .db and .json files."""
    store, db = snapshot_env
    sid = await store.save_snapshot(RunId("run-1"), "delete-me", db)

    await store.delete_snapshot(SnapshotId(sid))

    snaps = await store.list_snapshots()
    assert len(snaps) == 0

    with pytest.raises(FileNotFoundError):
        await store.get_snapshot_metadata(SnapshotId(sid))


async def test_get_snapshot_metadata(snapshot_env):
    """get_snapshot_metadata() should return complete metadata dict."""
    store, db = snapshot_env
    sid = await store.save_snapshot(RunId("run-meta"), "meta-test", db)

    meta = await store.get_snapshot_metadata(SnapshotId(sid))
    assert meta["snapshot_id"] == sid
    assert meta["run_id"] == "run-meta"
    assert meta["label"] == "meta-test"
    assert "timestamp" in meta
    assert "size_bytes" in meta


async def test_load_nonexistent_snapshot(tmp_path):
    """Loading a non-existent snapshot raises FileNotFoundError."""
    config = PersistenceConfig(base_dir=str(tmp_path))
    store = SnapshotStore(config)
    with pytest.raises(FileNotFoundError):
        await store.load_snapshot(SnapshotId("nonexistent"))


async def test_get_metadata_nonexistent_snapshot(tmp_path):
    """Getting metadata for non-existent snapshot raises FileNotFoundError."""
    config = PersistenceConfig(base_dir=str(tmp_path))
    store = SnapshotStore(config)
    with pytest.raises(FileNotFoundError):
        await store.get_snapshot_metadata(SnapshotId("nonexistent"))


async def test_list_snapshots_empty_dir(tmp_path):
    """list_snapshots returns empty list when no snapshots exist."""
    config = PersistenceConfig(base_dir=str(tmp_path))
    store = SnapshotStore(config)
    snaps = await store.list_snapshots()
    assert snaps == []
