"""Tests for summary parameter on RunManager.complete_run()."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from volnix.core.types import RunId
from volnix.runs.config import RunConfig
from volnix.persistence.manager import ConnectionManager


def _make_manager(tmp_path: Path):
    """Create a RunManager with a temp data dir."""
    from volnix.runs.manager import RunManager
    config = RunConfig(data_dir=str(tmp_path / "runs"))
    persistence = ConnectionManager.__new__(ConnectionManager)
    persistence._base_dir = tmp_path
    return RunManager(config, persistence)


async def test_complete_run_with_summary(tmp_path):
    """Summary should be stored in run metadata."""
    mgr = _make_manager(tmp_path)
    run_id = await mgr.create_run(world_def={"name": "test"}, config_snapshot={})
    await mgr.start_run(run_id)
    summary = {"current_tick": 10, "event_count": 42, "actor_count": 2}
    await mgr.complete_run(run_id, summary=summary)
    run = await mgr.get_run(run_id)
    assert run is not None
    assert "summary" in run
    assert run["summary"]["current_tick"] == 10
    assert run["summary"]["event_count"] == 42


async def test_complete_run_without_summary(tmp_path):
    """Backward compat: complete_run without summary should not add key."""
    mgr = _make_manager(tmp_path)
    run_id = await mgr.create_run(world_def={"name": "test"}, config_snapshot={})
    await mgr.start_run(run_id)
    await mgr.complete_run(run_id)
    run = await mgr.get_run(run_id)
    assert run is not None
    assert "summary" not in run


async def test_summary_persisted_to_disk(tmp_path):
    """Summary should survive JSON persistence."""
    mgr = _make_manager(tmp_path)
    run_id = await mgr.create_run(world_def={"name": "test"}, config_snapshot={})
    await mgr.start_run(run_id)
    summary = {"governance_score": 85.5, "services": [{"id": "email"}]}
    await mgr.complete_run(run_id, summary=summary)

    # Read raw JSON from disk
    meta_path = Path(str(tmp_path / "runs" / str(run_id) / "metadata.json"))
    raw = json.loads(meta_path.read_text())
    assert raw["summary"]["governance_score"] == 85.5
    assert raw["summary"]["services"][0]["id"] == "email"


async def test_summary_survives_reload(tmp_path):
    """Summary should be reloaded when a new RunManager is created."""
    mgr = _make_manager(tmp_path)
    run_id = await mgr.create_run(world_def={"name": "test"}, config_snapshot={})
    await mgr.start_run(run_id)
    await mgr.complete_run(run_id, summary={"event_count": 99})

    # Create new manager — should reload from disk
    mgr2 = _make_manager(tmp_path)
    run = await mgr2.get_run(run_id)
    assert run is not None
    assert run["summary"]["event_count"] == 99
