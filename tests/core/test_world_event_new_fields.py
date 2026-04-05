"""Tests for the 5 new fields added to WorldEvent."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from volnix.core.events import WorldEvent
from volnix.core.types import ActorId, EntityId, EventId, ServiceId, Timestamp

def _make_timestamp():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return Timestamp(world_time=now, wall_time=now, tick=1)

def _base_kwargs():
    return {
        "event_id": EventId("evt-1"),
        "event_type": "world.test_action",
        "timestamp": _make_timestamp(),
        "actor_id": ActorId("actor-1"),
        "service_id": ServiceId("svc-1"),
        "action": "test_action",
    }


def test_default_values():
    """New fields should have safe defaults."""
    event = WorldEvent(**_base_kwargs())
    assert event.response_body is None
    assert event.outcome == "success"
    assert event.state_deltas == []
    assert event.cost is None
    assert event.run_id is None


def test_explicit_values():
    """New fields can be set explicitly."""
    deltas = [{"entity_type": "ticket", "entity_id": "t-1", "operation": "create", "fields": {"id": "t-1"}, "previous_fields": None}]
    cost = {"api_calls": 1, "llm_spend_usd": 0.05, "world_actions": 1}
    event = WorldEvent(
        **_base_kwargs(),
        response_body={"status": "ok"},
        outcome="blocked",
        state_deltas=deltas,
        cost=cost,
        run_id="run-123",
    )
    assert event.response_body == {"status": "ok"}
    assert event.outcome == "blocked"
    assert len(event.state_deltas) == 1
    assert event.state_deltas[0]["entity_type"] == "ticket"
    assert event.cost["api_calls"] == 1
    assert event.run_id == "run-123"


def test_serialization_round_trip():
    """New fields survive model_dump → reconstruct."""
    original = WorldEvent(
        **_base_kwargs(),
        response_body={"data": [1, 2, 3]},
        outcome="held",
        state_deltas=[{"entity_type": "email", "entity_id": "e-1", "operation": "update", "fields": {"status": "read"}, "previous_fields": {"status": "unread"}}],
        cost={"api_calls": 2, "llm_spend_usd": 0.1, "world_actions": 1},
        run_id="run-456",
    )
    dumped = original.model_dump(mode="json")
    assert dumped["response_body"] == {"data": [1, 2, 3]}
    assert dumped["outcome"] == "held"
    assert len(dumped["state_deltas"]) == 1
    assert dumped["cost"]["api_calls"] == 2
    assert dumped["run_id"] == "run-456"


def test_backward_compat_deserialization():
    """Old event dicts without new fields should still work."""
    old_dict = {
        "event_id": "evt-old",
        "event_type": "world.old_action",
        "timestamp": {"world_time": "2026-01-01T00:00:00Z", "wall_time": "2026-01-01T00:00:00Z", "tick": 0},
        "actor_id": "actor-1",
        "service_id": "svc-1",
        "action": "old_action",
    }
    event = WorldEvent(**old_dict)
    assert event.response_body is None
    assert event.outcome == "success"
    assert event.state_deltas == []
    assert event.cost is None
    assert event.run_id is None


def test_frozen_field_assignment():
    """WorldEvent is frozen — field assignment should raise."""
    event = WorldEvent(**_base_kwargs())
    with pytest.raises(ValidationError):
        event.outcome = "blocked"
