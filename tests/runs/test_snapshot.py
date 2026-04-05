"""Tests for volnix.runs.snapshot — run-aware snapshot management."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from volnix.core.types import RunId, SnapshotId
from volnix.runs.config import RunConfig
from volnix.runs.snapshot import SnapshotManager


def _make_manager(tmp_path) -> tuple[SnapshotManager, AsyncMock]:
    config = RunConfig(data_dir=str(tmp_path / "runs"), snapshot_interval_ticks=5)
    persistence = AsyncMock()
    mgr = SnapshotManager(config=config, persistence=persistence)
    # Inject a mock SnapshotStore so we don't need real SQLite
    mock_store = AsyncMock()
    mock_store.save_snapshot = AsyncMock(return_value=SnapshotId("snap_test_001"))
    mock_store.load_snapshot = AsyncMock()
    mock_store.list_snapshots = AsyncMock(return_value=[{"snapshot_id": "snap_test_001", "run_id": "run_1", "label": "test"}])
    mgr._snapshot_store = mock_store
    return mgr, mock_store


@pytest.mark.asyncio
async def test_take_snapshot_returns_snapshot_id(tmp_path):
    mgr, mock_store = _make_manager(tmp_path)
    snap_id = await mgr.take_snapshot(RunId("run_1"), "checkpoint", tick=10)
    assert str(snap_id) == "snap_test_001"
    mock_store.save_snapshot.assert_called_once()


@pytest.mark.asyncio
async def test_list_snapshots_by_run(tmp_path):
    mgr, mock_store = _make_manager(tmp_path)
    snapshots = await mgr.list_snapshots(RunId("run_1"))
    assert len(snapshots) == 1
    mock_store.list_snapshots.assert_called_once_with(run_id=RunId("run_1"))


@pytest.mark.asyncio
async def test_auto_snapshot_respects_interval(tmp_path):
    mgr, mock_store = _make_manager(tmp_path)
    # interval=5, tick=0 → should snapshot (0 >= 0+5 is false but first time)
    # Actually: last=0 (default), tick=0, 0-0=0 < 5 → NO snapshot
    result0 = await mgr.auto_snapshot(RunId("run_1"), tick=0)
    assert result0 is None

    # tick=5, 5-0=5 >= 5 → YES
    result5 = await mgr.auto_snapshot(RunId("run_1"), tick=5)
    assert result5 is not None

    # tick=6, 6-5=1 < 5 → NO (last was updated to 5)
    result6 = await mgr.auto_snapshot(RunId("run_1"), tick=6)
    assert result6 is None

    # tick=10, 10-5=5 >= 5 → YES
    result10 = await mgr.auto_snapshot(RunId("run_1"), tick=10)
    assert result10 is not None


@pytest.mark.asyncio
async def test_auto_snapshot_disabled(tmp_path):
    config = RunConfig(data_dir=str(tmp_path / "runs"), snapshot_interval_ticks=0)
    persistence = AsyncMock()
    mgr = SnapshotManager(config=config, persistence=persistence)
    result = await mgr.auto_snapshot(RunId("run_1"), tick=100)
    assert result is None
