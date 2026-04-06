"""Tests for volnix.runs.manager — run lifecycle management."""

from unittest.mock import AsyncMock

import pytest

from volnix.core.types import RunId
from volnix.runs.config import RunConfig
from volnix.runs.manager import RunManager


def _make_manager(tmp_path) -> RunManager:
    config = RunConfig(data_dir=str(tmp_path / "runs"))
    persistence = AsyncMock()
    return RunManager(config=config, persistence=persistence)


@pytest.mark.asyncio
async def test_create_run_returns_run_id(tmp_path):
    mgr = _make_manager(tmp_path)
    run_id = await mgr.create_run(world_def={"name": "test"}, config_snapshot={"seed": 42})
    assert str(run_id).startswith("run_")


@pytest.mark.asyncio
async def test_create_run_with_tag(tmp_path):
    mgr = _make_manager(tmp_path)
    run_id = await mgr.create_run(
        world_def={},
        config_snapshot={},
        tag="gov",
    )
    run = await mgr.get_run(RunId("gov"))
    assert run is not None
    assert run["run_id"] == str(run_id)
    assert run["tag"] == "gov"


@pytest.mark.asyncio
async def test_start_run_transitions_status(tmp_path):
    mgr = _make_manager(tmp_path)
    run_id = await mgr.create_run(world_def={}, config_snapshot={})
    await mgr.start_run(run_id)
    run = await mgr.get_run(run_id)
    assert run["status"] == "running"
    assert run["started_at"] is not None


@pytest.mark.asyncio
async def test_complete_run_transitions_status(tmp_path):
    mgr = _make_manager(tmp_path)
    run_id = await mgr.create_run(world_def={}, config_snapshot={})
    await mgr.start_run(run_id)
    await mgr.complete_run(run_id)
    run = await mgr.get_run(run_id)
    assert run["status"] == "completed"
    assert run["completed_at"] is not None


@pytest.mark.asyncio
async def test_fail_run_records_error(tmp_path):
    mgr = _make_manager(tmp_path)
    run_id = await mgr.create_run(world_def={}, config_snapshot={})
    await mgr.start_run(run_id)
    await mgr.fail_run(run_id, "Something went wrong")
    run = await mgr.get_run(run_id)
    assert run["status"] == "failed"
    assert run["error"] == "Something went wrong"


@pytest.mark.asyncio
async def test_list_runs_newest_first(tmp_path):
    mgr = _make_manager(tmp_path)
    id1 = await mgr.create_run(world_def={"n": 1}, config_snapshot={}, tag="first")
    id2 = await mgr.create_run(world_def={"n": 2}, config_snapshot={}, tag="second")
    runs = await mgr.list_runs()
    assert len(runs) == 2
    assert runs[0]["run_id"] == str(id2)
    assert runs[1]["run_id"] == str(id1)


@pytest.mark.asyncio
async def test_get_run_resolves_tag(tmp_path):
    mgr = _make_manager(tmp_path)
    run_id = await mgr.create_run(world_def={}, config_snapshot={}, tag="my-tag")
    result = await mgr.get_run(RunId("my-tag"))
    assert result is not None
    assert result["run_id"] == str(run_id)


@pytest.mark.asyncio
async def test_get_active_run(tmp_path):
    mgr = _make_manager(tmp_path)
    run_id = await mgr.create_run(world_def={}, config_snapshot={})
    assert await mgr.get_active_run() is None
    await mgr.start_run(run_id)
    active = await mgr.get_active_run()
    assert active == run_id
    await mgr.complete_run(run_id)
    assert await mgr.get_active_run() is None


@pytest.mark.asyncio
async def test_metadata_persisted_to_disk(tmp_path):
    mgr = _make_manager(tmp_path)
    run_id = await mgr.create_run(world_def={}, config_snapshot={})
    meta_path = tmp_path / "runs" / str(run_id) / "metadata.json"
    assert meta_path.exists()


@pytest.mark.asyncio
async def test_get_run_unknown_id_returns_none(tmp_path):
    mgr = _make_manager(tmp_path)
    result = await mgr.get_run(RunId("nonexistent"))
    assert result is None


@pytest.mark.asyncio
async def test_list_runs_respects_limit(tmp_path):
    mgr = _make_manager(tmp_path)
    await mgr.create_run(world_def={"n": 1}, config_snapshot={})
    await mgr.create_run(world_def={"n": 2}, config_snapshot={})
    await mgr.create_run(world_def={"n": 3}, config_snapshot={})
    runs = await mgr.list_runs(limit=2)
    assert len(runs) == 2


@pytest.mark.asyncio
async def test_resolve_last_keyword(tmp_path):
    mgr = _make_manager(tmp_path)
    _id1 = await mgr.create_run(world_def={"n": 1}, config_snapshot={}, tag="first")
    id2 = await mgr.create_run(world_def={"n": 2}, config_snapshot={}, tag="second")
    result = await mgr.get_run(RunId("last"))
    assert result is not None
    assert result["run_id"] == str(id2)


@pytest.mark.asyncio
async def test_start_already_running_run(tmp_path):
    mgr = _make_manager(tmp_path)
    run_id = await mgr.create_run(world_def={}, config_snapshot={})
    await mgr.start_run(run_id)
    run = await mgr.get_run(run_id)
    assert run["status"] == "running"
    first_started_at = run["started_at"]
    # Starting again should still work (idempotent transition)
    await mgr.start_run(run_id)
    run = await mgr.get_run(run_id)
    assert run["status"] == "running"
    assert run["started_at"] is not None
    # started_at may be updated, but status stays running
    assert run["started_at"] >= first_started_at
