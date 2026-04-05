"""Tests for volnix.core.events — event dataclasses and serialization."""
import pytest
from volnix.core.events import (
    Event, WorldEvent,
    PermissionDeniedEvent, PolicyBlockEvent, PolicyHoldEvent,
    BudgetExhaustedEvent, BudgetDeductionEvent, CapabilityGapEvent,
    EngineLifecycleEvent,
)
from volnix.core.types import (
    Timestamp, ActorId, ServiceId, PolicyId, ToolName, EventId,
)
from datetime import datetime, timezone


def _ts():
    now = datetime.now(timezone.utc)
    return Timestamp(world_time=now, wall_time=now, tick=1)


def test_event_id_generation():
    e1 = Event(event_type="test", timestamp=_ts())
    e2 = Event(event_type="test", timestamp=_ts())
    assert e1.event_id != e2.event_id


def test_event_base_fields():
    e = Event(event_type="test", timestamp=_ts(), metadata={"k": "v"})
    assert e.event_type == "test"
    assert e.caused_by is None
    assert e.metadata == {"k": "v"}


def test_world_event_fields():
    e = WorldEvent(
        event_type="world.action",
        timestamp=_ts(),
        actor_id=ActorId("a1"),
        service_id=ServiceId("s1"),
        action="send_email",
    )
    assert e.actor_id == "a1"
    assert e.service_id == "s1"
    assert e.action == "send_email"


def test_permission_denied_event():
    e = PermissionDeniedEvent(
        event_type="permission.denied",
        timestamp=_ts(),
        actor_id=ActorId("a1"),
        action="delete_account",
        reason="insufficient role",
    )
    assert e.actor_id == "a1"
    assert e.reason == "insufficient role"
    assert e.action == "delete_account"


def test_policy_block_event():
    e = PolicyBlockEvent(
        event_type="policy.block",
        timestamp=_ts(),
        policy_id=PolicyId("p1"),
        actor_id=ActorId("a1"),
        action="transfer",
        reason="exceeds limit",
    )
    assert e.reason == "exceeds limit"


def test_policy_hold_event():
    e = PolicyHoldEvent(
        event_type="policy.hold",
        timestamp=_ts(),
        policy_id=PolicyId("p1"),
        actor_id=ActorId("a1"),
        action="transfer",
        approver_role="manager",
        timeout_seconds=3600,
        hold_id="h1",
    )
    assert e.hold_id == "h1"
    assert e.timeout_seconds == 3600


def test_budget_exhausted_event():
    e = BudgetExhaustedEvent(
        event_type="budget.exhausted",
        timestamp=_ts(),
        actor_id=ActorId("a1"),
        budget_type="api_calls",
    )
    assert e.actor_id == "a1"
    assert e.budget_type == "api_calls"


def test_capability_gap_event():
    e = CapabilityGapEvent(
        event_type="capability_gap",
        timestamp=_ts(),
        actor_id=ActorId("a1"),
        requested_tool=ToolName("unknown_tool"),
    )
    assert e.requested_tool == "unknown_tool"


def test_event_serialization_roundtrip():
    e = Event(event_type="test", timestamp=_ts(), metadata={"a": 1})
    data = e.model_dump()
    restored = Event.model_validate(data)
    assert restored.event_type == "test"
    assert restored.metadata == {"a": 1}
    assert restored.event_id == e.event_id


def test_event_type_discriminator():
    e1 = Event(event_type="test", timestamp=_ts())
    e2 = WorldEvent(
        event_type="world.action",
        timestamp=_ts(),
        actor_id=ActorId("a1"),
        service_id=ServiceId("s1"),
        action="do_thing",
    )
    assert e1.event_type == "test"
    assert e2.event_type == "world.action"
    # They are distinct event types
    assert type(e1) is not type(e2)
