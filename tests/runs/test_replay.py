"""Tests for volnix.runs.replay — run replay engine."""
import pytest
from unittest.mock import AsyncMock

from volnix.core.types import RunId
from volnix.runs.config import RunConfig
from volnix.runs.replay import RunReplayer


def _make_replayer(tmp_path) -> RunReplayer:
    config = RunConfig(data_dir=str(tmp_path / "runs"))
    persistence = AsyncMock()
    return RunReplayer(config=config, persistence=persistence)


def _seed_event_log(tmp_path, run_id: str, events: list):
    """Write an event log artifact directly so the replayer can load it."""
    import json
    from pathlib import Path
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "event_log.json").write_text(json.dumps(events))


@pytest.mark.asyncio
async def test_start_replay_loads_events(tmp_path):
    replayer = _make_replayer(tmp_path)
    events = [{"event_type": "world.action", "tick": 0}, {"event_type": "world.action", "tick": 1}]
    _seed_event_log(tmp_path, "run_r1", events)
    await replayer.start_replay(RunId("run_r1"), speed=2.0)
    state = await replayer.get_replay_state()
    assert state["total_events"] == 2
    assert state["speed"] == 2.0
    assert state["status"] == "replaying"


@pytest.mark.asyncio
async def test_pause_resume(tmp_path):
    replayer = _make_replayer(tmp_path)
    _seed_event_log(tmp_path, "run_r2", [{"event_type": "x", "tick": 0}])
    await replayer.start_replay(RunId("run_r2"))
    await replayer.pause_replay()
    state = await replayer.get_replay_state()
    assert state["paused"] is True
    assert state["status"] == "paused"
    await replayer.resume_replay()
    state = await replayer.get_replay_state()
    assert state["paused"] is False


@pytest.mark.asyncio
async def test_seek_to_tick(tmp_path):
    replayer = _make_replayer(tmp_path)
    events = [{"event_type": "a", "tick": 0}, {"event_type": "b", "tick": 5}, {"event_type": "c", "tick": 10}]
    _seed_event_log(tmp_path, "run_r3", events)
    await replayer.start_replay(RunId("run_r3"))
    await replayer.seek_to_tick(5)
    state = await replayer.get_replay_state()
    assert state["tick"] == 5
    assert state["events_at_tick"] == 2  # tick 0 and tick 5


@pytest.mark.asyncio
async def test_get_replay_state_structure(tmp_path):
    replayer = _make_replayer(tmp_path)
    state = await replayer.get_replay_state()
    assert state["run_id"] is None
    assert state["tick"] == 0
    assert state["paused"] is False
    assert state["speed"] == 1.0
    assert state["status"] == "idle"
    assert state["total_events"] == 0


@pytest.mark.asyncio
async def test_stop_replay_resets_state(tmp_path):
    replayer = _make_replayer(tmp_path)
    events = [{"event_type": "a", "tick": 0}, {"event_type": "b", "tick": 1}]
    _seed_event_log(tmp_path, "run_stop", events)
    await replayer.start_replay(RunId("run_stop"))
    state = await replayer.get_replay_state()
    assert state["status"] == "replaying"
    assert state["total_events"] == 2
    await replayer.stop_replay()
    state = await replayer.get_replay_state()
    assert state["status"] == "idle"
    assert state["total_events"] == 0
    assert state["events_at_tick"] == 0


@pytest.mark.asyncio
async def test_seek_beyond_events(tmp_path):
    replayer = _make_replayer(tmp_path)
    events = [{"event_type": "a", "tick": 0}, {"event_type": "b", "tick": 5}]
    _seed_event_log(tmp_path, "run_seek", events)
    await replayer.start_replay(RunId("run_seek"))
    await replayer.seek_to_tick(999)
    state = await replayer.get_replay_state()
    assert state["tick"] == 999
    # events_at_tick should only count the 2 existing events (both have tick <= 999)
    assert state["events_at_tick"] == 2
