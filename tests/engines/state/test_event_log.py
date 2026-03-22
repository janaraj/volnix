"""Tests for terrarium.engines.state.event_log -- EventLog append/query."""
import pytest
from datetime import datetime, timezone, timedelta
from terrarium.core.types import ActorId, ServiceId, EntityId, EventId, Timestamp
from terrarium.core.events import WorldEvent, Event
from terrarium.engines.state.event_log import EventLog


def _make_event(action="test_action", actor="agent-1", service="svc-1",
                tick=1, world_time=None, target_entity=None, **kwargs):
    """Helper to build a WorldEvent with sensible defaults."""
    return WorldEvent(
        event_type=f"world.{action}",
        timestamp=Timestamp(
            world_time=world_time or datetime(2026, 1, 15, tzinfo=timezone.utc),
            wall_time=datetime.now(timezone.utc),
            tick=tick,
        ),
        actor_id=ActorId(actor),
        service_id=ServiceId(service),
        action=action,
        target_entity=EntityId(target_entity) if target_entity else None,
        **kwargs,
    )


async def test_append_and_get(event_log):
    """Append an event and get it back by id; verify all fields match."""
    event = _make_event(action="create_user", actor="agent-1")
    returned_id = await event_log.append(event)

    assert returned_id == event.event_id

    retrieved = await event_log.get(event.event_id)
    assert retrieved is not None
    assert retrieved.event_id == event.event_id
    assert retrieved.event_type == "world.create_user"
    assert retrieved.actor_id == ActorId("agent-1")
    assert retrieved.action == "create_user"


async def test_get_missing_none(event_log):
    """Getting a nonexistent event_id returns None."""
    result = await event_log.get(EventId("nonexistent-id"))
    assert result is None


async def test_query_time_range(event_log):
    """Query with start/end filters returns only events in the time range."""
    t1 = datetime(2026, 1, 10, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 15, tzinfo=timezone.utc)
    t3 = datetime(2026, 1, 20, tzinfo=timezone.utc)

    await event_log.append(_make_event(action="a1", tick=1, world_time=t1))
    await event_log.append(_make_event(action="a2", tick=2, world_time=t2))
    await event_log.append(_make_event(action="a3", tick=3, world_time=t3))

    results = await event_log.query(
        start=datetime(2026, 1, 12, tzinfo=timezone.utc),
        end=datetime(2026, 1, 18, tzinfo=timezone.utc),
    )
    assert len(results) == 1
    assert results[0].action == "a2"


async def test_query_by_actor(event_log):
    """Query by actor_id returns only events from that actor."""
    await event_log.append(_make_event(action="a1", actor="alice", tick=1))
    await event_log.append(_make_event(action="a2", actor="bob", tick=2))
    await event_log.append(_make_event(action="a3", actor="alice", tick=3))

    results = await event_log.query(actor_id=ActorId("alice"))
    assert len(results) == 2
    assert all(r.actor_id == ActorId("alice") for r in results)


async def test_query_by_entity(event_log):
    """Query by entity_id returns only events targeting that entity."""
    await event_log.append(_make_event(action="a1", target_entity="ent-1", tick=1))
    await event_log.append(_make_event(action="a2", target_entity="ent-2", tick=2))
    await event_log.append(_make_event(action="a3", target_entity="ent-1", tick=3))

    results = await event_log.query(entity_id=EntityId("ent-1"))
    assert len(results) == 2


async def test_query_by_event_type(event_log):
    """Query by event_type returns only matching events."""
    await event_log.append(_make_event(action="create_user", tick=1))
    await event_log.append(_make_event(action="update_user", tick=2))
    await event_log.append(_make_event(action="create_user", tick=3))

    results = await event_log.query(event_type="world.create_user")
    assert len(results) == 2
    assert all(r.event_type == "world.create_user" for r in results)


async def test_query_with_limit(event_log):
    """Query with limit returns at most that many events."""
    for i in range(5):
        await event_log.append(_make_event(action=f"action_{i}", tick=i + 1))

    results = await event_log.query(limit=2)
    assert len(results) == 2


async def test_query_empty(event_log):
    """Query with no matching events returns an empty list."""
    results = await event_log.query(actor_id=ActorId("nonexistent"))
    assert results == []


async def test_get_by_entity(event_log):
    """get_by_entity returns events targeting a specific entity in time order."""
    t1 = datetime(2026, 1, 10, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 15, tzinfo=timezone.utc)

    await event_log.append(_make_event(action="a1", target_entity="ent-1", tick=1, world_time=t1))
    await event_log.append(_make_event(action="a2", target_entity="ent-2", tick=2, world_time=t2))
    await event_log.append(_make_event(action="a3", target_entity="ent-1", tick=3, world_time=t2))

    results = await event_log.get_by_entity("user", EntityId("ent-1"))
    assert len(results) == 2
    assert results[0].action == "a1"
    assert results[1].action == "a3"


async def test_events_ordered(event_log):
    """Verify query results are ordered by timestamp ASC."""
    t3 = datetime(2026, 1, 20, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 10, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 15, tzinfo=timezone.utc)

    # Insert out of order
    await event_log.append(_make_event(action="third", tick=3, world_time=t3))
    await event_log.append(_make_event(action="first", tick=1, world_time=t1))
    await event_log.append(_make_event(action="second", tick=2, world_time=t2))

    results = await event_log.query()
    assert len(results) == 3
    assert results[0].action == "first"
    assert results[1].action == "second"
    assert results[2].action == "third"
