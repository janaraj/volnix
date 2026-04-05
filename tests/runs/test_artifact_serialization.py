"""Tests for artifact serialization with WorldEvent fields.

Validates that state_deltas, cost, response_body, outcome, and run_id
all round-trip correctly through ArtifactStore save/load.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from volnix.core.events import WorldEvent
from volnix.core.types import ActorId, EventId, RunId, ServiceId, Timestamp
from volnix.runs.artifacts import ArtifactStore
from volnix.runs.config import RunConfig


def _ts(tick: int = 5) -> Timestamp:
    now = datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc)
    return Timestamp(world_time=now, wall_time=now, tick=tick)


@pytest.fixture
def artifact_store(tmp_path):
    config = RunConfig(data_dir=str(tmp_path / "runs"))
    return ArtifactStore(config)


async def test_event_with_state_deltas_serializes(artifact_store, tmp_path):
    """state_deltas should round-trip through save/load."""
    run_id = RunId("run-test-1")
    (tmp_path / "runs" / str(run_id)).mkdir(parents=True)

    event = WorldEvent(
        event_id=EventId("e1"),
        event_type="world.create_ticket",
        timestamp=_ts(),
        actor_id=ActorId("agent-1"),
        service_id=ServiceId("zendesk"),
        action="create_ticket",
        state_deltas=[
            {
                "entity_type": "ticket",
                "entity_id": "t-1",
                "operation": "create",
                "fields": {"subject": "Help"},
                "previous_fields": None,
            }
        ],
    )
    await artifact_store.save_event_log(run_id, [event])
    loaded = await artifact_store.load_artifact(run_id, "event_log")
    assert loaded is not None
    assert len(loaded) == 1
    assert loaded[0]["state_deltas"][0]["entity_type"] == "ticket"
    assert loaded[0]["state_deltas"][0]["fields"]["subject"] == "Help"
    assert loaded[0]["state_deltas"][0]["previous_fields"] is None


async def test_event_with_cost_serializes(artifact_store, tmp_path):
    """cost dict should round-trip."""
    run_id = RunId("run-test-2")
    (tmp_path / "runs" / str(run_id)).mkdir(parents=True)

    event = WorldEvent(
        event_id=EventId("e2"),
        event_type="world.send",
        timestamp=_ts(),
        actor_id=ActorId("agent-1"),
        service_id=ServiceId("gmail"),
        action="send",
        cost={"api_calls": 3, "llm_spend_usd": 0.15, "world_actions": 2},
    )
    await artifact_store.save_event_log(run_id, [event])
    loaded = await artifact_store.load_artifact(run_id, "event_log")
    assert loaded[0]["cost"]["api_calls"] == 3
    assert loaded[0]["cost"]["llm_spend_usd"] == 0.15
    assert loaded[0]["cost"]["world_actions"] == 2


async def test_event_with_response_body_serializes(artifact_store, tmp_path):
    """response_body dict should round-trip."""
    run_id = RunId("run-test-3")
    (tmp_path / "runs" / str(run_id)).mkdir(parents=True)

    event = WorldEvent(
        event_id=EventId("e3"),
        event_type="world.query",
        timestamp=_ts(),
        actor_id=ActorId("agent-1"),
        service_id=ServiceId("db"),
        action="query",
        response_body={"results": [1, 2, 3], "total": 3},
    )
    await artifact_store.save_event_log(run_id, [event])
    loaded = await artifact_store.load_artifact(run_id, "event_log")
    assert loaded[0]["response_body"]["total"] == 3
    assert loaded[0]["response_body"]["results"] == [1, 2, 3]


async def test_event_with_none_fields_serializes(artifact_store, tmp_path):
    """Events with all new fields as None/default should serialize cleanly."""
    run_id = RunId("run-test-4")
    (tmp_path / "runs" / str(run_id)).mkdir(parents=True)

    event = WorldEvent(
        event_id=EventId("e4"),
        event_type="world.noop",
        timestamp=_ts(),
        actor_id=ActorId("agent-1"),
        service_id=ServiceId("svc"),
        action="noop",
    )
    await artifact_store.save_event_log(run_id, [event])
    loaded = await artifact_store.load_artifact(run_id, "event_log")
    assert loaded[0]["response_body"] is None
    assert loaded[0]["outcome"] == "success"
    assert loaded[0]["state_deltas"] == []
    assert loaded[0]["cost"] is None
    assert loaded[0]["run_id"] is None


async def test_event_with_outcome_serializes(artifact_store, tmp_path):
    """Non-default outcome should round-trip."""
    run_id = RunId("run-test-5")
    (tmp_path / "runs" / str(run_id)).mkdir(parents=True)

    event = WorldEvent(
        event_id=EventId("e5"),
        event_type="world.blocked_action",
        timestamp=_ts(),
        actor_id=ActorId("agent-1"),
        service_id=ServiceId("stripe"),
        action="transfer",
        outcome="blocked",
    )
    await artifact_store.save_event_log(run_id, [event])
    loaded = await artifact_store.load_artifact(run_id, "event_log")
    assert loaded[0]["outcome"] == "blocked"


async def test_event_with_run_id_serializes(artifact_store, tmp_path):
    """run_id field on event should round-trip."""
    run_id = RunId("run-test-6")
    (tmp_path / "runs" / str(run_id)).mkdir(parents=True)

    event = WorldEvent(
        event_id=EventId("e6"),
        event_type="world.send",
        timestamp=_ts(),
        actor_id=ActorId("agent-1"),
        service_id=ServiceId("gmail"),
        action="send",
        run_id="run-test-6",
    )
    await artifact_store.save_event_log(run_id, [event])
    loaded = await artifact_store.load_artifact(run_id, "event_log")
    assert loaded[0]["run_id"] == "run-test-6"


async def test_multiple_events_serialize(artifact_store, tmp_path):
    """Multiple events in a single log should all round-trip."""
    run_id = RunId("run-test-7")
    (tmp_path / "runs" / str(run_id)).mkdir(parents=True)

    events = [
        WorldEvent(
            event_id=EventId(f"e{i}"),
            event_type="world.action",
            timestamp=_ts(tick=i),
            actor_id=ActorId("agent-1"),
            service_id=ServiceId("svc"),
            action=f"action_{i}",
            cost={"api_calls": i},
        )
        for i in range(5)
    ]
    await artifact_store.save_event_log(run_id, events)
    loaded = await artifact_store.load_artifact(run_id, "event_log")
    assert len(loaded) == 5
    for i, evt in enumerate(loaded):
        assert evt["event_id"] == f"e{i}"
        assert evt["cost"]["api_calls"] == i
