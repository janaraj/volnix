"""Tests for RunComparator.compute_divergence_points()."""

from __future__ import annotations

from unittest.mock import AsyncMock

from volnix.core.types import RunId
from volnix.runs.comparison import RunComparator


def _make_event(event_type: str, actor_id: str, action: str, tick: int) -> dict:
    return {
        "event_id": f"evt-{event_type}-{actor_id}-{tick}",
        "event_type": event_type,
        "actor_id": actor_id,
        "action": action,
        "timestamp": {
            "world_time": "2026-01-01T00:00:00Z",
            "wall_time": "2026-01-01T00:00:00Z",
            "tick": tick,
        },
    }


def _mock_store(run_events: dict[str, list[dict]]) -> AsyncMock:
    store = AsyncMock()

    async def _load(run_id, artifact_type):
        if artifact_type == "event_log":
            return run_events.get(str(run_id), [])
        return None

    store.load_artifact = _load
    return store


async def test_empty_event_logs():
    """Both runs empty → no divergence."""
    store = _mock_store({"run-a": [], "run-b": []})
    comp = RunComparator(store)
    points = await comp.compute_divergence_points([RunId("run-a"), RunId("run-b")])
    assert points == []


async def test_identical_runs():
    """Same events in both runs → no divergence."""
    events = [_make_event("world.send", "agent-1", "send", 1)]
    store = _mock_store({"run-a": events, "run-b": events})
    comp = RunComparator(store)
    points = await comp.compute_divergence_points([RunId("run-a"), RunId("run-b")])
    assert points == []


async def test_diverging_runs():
    """Different events at tick 2 → divergence detected."""
    store = _mock_store(
        {
            "run-a": [
                _make_event("world.send", "agent-1", "send", 1),
                _make_event("world.send", "agent-1", "send", 2),
            ],
            "run-b": [
                _make_event("world.send", "agent-1", "send", 1),
                _make_event("world.refund", "agent-1", "refund", 2),
            ],
        }
    )
    comp = RunComparator(store)
    points = await comp.compute_divergence_points([RunId("run-a"), RunId("run-b")])
    assert len(points) == 1
    assert points[0]["tick"] == 2
    assert points[0]["type"] == "event_set_mismatch"


async def test_three_runs_divergence():
    """B2 regression: A=B but C differs → divergence detected."""
    shared = [_make_event("world.send", "agent-1", "send", 1)]
    different = [_make_event("world.refund", "agent-1", "refund", 1)]
    store = _mock_store({"run-a": shared, "run-b": shared, "run-c": different})
    comp = RunComparator(store)
    points = await comp.compute_divergence_points([RunId("run-a"), RunId("run-b"), RunId("run-c")])
    assert len(points) >= 1
    assert points[0]["tick"] == 1


async def test_single_run():
    """Single run → no divergence possible."""
    store = _mock_store({"run-a": [_make_event("world.send", "agent-1", "send", 1)]})
    comp = RunComparator(store)
    points = await comp.compute_divergence_points([RunId("run-a")])
    assert points == []


async def test_different_tick_ranges():
    """Runs with different tick ranges → divergence at ticks only one has."""
    store = _mock_store(
        {
            "run-a": [_make_event("world.send", "agent-1", "send", t) for t in range(3)],
            "run-b": [_make_event("world.send", "agent-1", "send", t) for t in range(5)],
        }
    )
    comp = RunComparator(store)
    points = await comp.compute_divergence_points([RunId("run-a"), RunId("run-b")])
    # Ticks 3 and 4 only exist in run-b
    divergent_ticks = {p["tick"] for p in points}
    assert 3 in divergent_ticks
    assert 4 in divergent_ticks
