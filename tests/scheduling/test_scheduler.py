"""Tests for volnix.scheduling.scheduler -- WorldScheduler.

Covers: one-shot events, recurring events, trigger events,
        cancellation, empty scheduler, ordering.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from volnix.scheduling.scheduler import (
    WorldScheduler,
    ScheduledEvent,
    RecurringEvent,
    TriggerEvent,
)


def _utc(year=2026, month=3, day=22, hour=12, minute=0, second=0):
    """Create a UTC datetime for testing."""
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# One-shot events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_shot_fires_at_correct_time():
    """One-shot event fires when world_time >= fire_time."""
    scheduler = WorldScheduler()
    t0 = _utc(minute=0)
    t1 = _utc(minute=5)

    event_def = {"action": "npc_check", "actor_id": "npc1"}
    scheduler.register_event(t1, event_def, source="test")

    # Before fire_time -> nothing
    due = await scheduler.get_due_events(t0)
    assert due == []

    # At fire_time -> fires
    due = await scheduler.get_due_events(t1)
    assert len(due) == 1
    assert due[0]["action"] == "npc_check"


@pytest.mark.asyncio
async def test_one_shot_removed_after_firing():
    """One-shot event is removed after it fires once."""
    scheduler = WorldScheduler()
    t = _utc(minute=5)

    scheduler.register_event(t, {"action": "once"}, source="test")

    # First call fires it
    due = await scheduler.get_due_events(t)
    assert len(due) == 1

    # Second call -> gone
    due = await scheduler.get_due_events(t)
    assert due == []


@pytest.mark.asyncio
async def test_one_shot_events_before_world_time_returned():
    """All one-shot events at or before world_time are returned."""
    scheduler = WorldScheduler()
    t1 = _utc(minute=1)
    t2 = _utc(minute=2)
    t3 = _utc(minute=3)
    t_check = _utc(minute=2, second=30)

    scheduler.register_event(t1, {"action": "e1"}, source="test")
    scheduler.register_event(t2, {"action": "e2"}, source="test")
    scheduler.register_event(t3, {"action": "e3"}, source="test")

    due = await scheduler.get_due_events(t_check)
    assert len(due) == 2
    actions = [e["action"] for e in due]
    assert "e1" in actions
    assert "e2" in actions


@pytest.mark.asyncio
async def test_events_after_world_time_not_returned():
    """Events with fire_time > world_time are NOT returned."""
    scheduler = WorldScheduler()
    t_future = _utc(minute=30)
    t_now = _utc(minute=10)

    scheduler.register_event(t_future, {"action": "future"}, source="test")
    due = await scheduler.get_due_events(t_now)
    assert due == []


# ---------------------------------------------------------------------------
# Recurring events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recurring_fires_repeatedly():
    """Recurring event fires on each interval."""
    scheduler = WorldScheduler()
    t_start = _utc(minute=0)

    scheduler.register_recurring(
        interval_seconds=60,
        event_def={"action": "heartbeat"},
        source="test",
        start_time=t_start,
    )

    # First fire at t_start
    due = await scheduler.get_due_events(t_start)
    assert len(due) == 1
    assert due[0]["action"] == "heartbeat"

    # Next fire at t_start + 60s
    t_next = t_start + timedelta(seconds=60)
    due = await scheduler.get_due_events(t_next)
    assert len(due) == 1

    # Check at t_start + 90s -- should not fire (next is at 120s)
    t_between = t_start + timedelta(seconds=90)
    due = await scheduler.get_due_events(t_between)
    assert due == []

    # Fire at t_start + 120s
    t_third = t_start + timedelta(seconds=120)
    due = await scheduler.get_due_events(t_third)
    assert len(due) == 1


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_one_shot():
    """Cancel removes a one-shot event."""
    scheduler = WorldScheduler()
    t = _utc(minute=5)

    eid = scheduler.register_event(t, {"action": "cancel_me"}, source="test")
    assert scheduler.cancel(eid) is True

    due = await scheduler.get_due_events(t)
    assert due == []


@pytest.mark.asyncio
async def test_cancel_recurring():
    """Cancel removes a recurring event."""
    scheduler = WorldScheduler()
    t = _utc(minute=0)

    eid = scheduler.register_recurring(60, {"action": "cancel_recur"}, source="test", start_time=t)
    assert scheduler.cancel(eid) is True

    due = await scheduler.get_due_events(t)
    assert due == []


@pytest.mark.asyncio
async def test_cancel_nonexistent_returns_false():
    """Cancelling a non-existent event returns False."""
    scheduler = WorldScheduler()
    assert scheduler.cancel("nonexistent_id") is False


# ---------------------------------------------------------------------------
# Trigger events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_fires_when_condition_met():
    """Trigger event fires when condition evaluates to True."""
    scheduler = WorldScheduler()
    t = _utc(minute=0)

    scheduler.register_trigger(
        condition="True",  # Always true
        event_def={"action": "triggered"},
        source="test",
    )

    # With a mock state_engine (triggers need state_engine to evaluate)
    from unittest.mock import AsyncMock
    state_engine = AsyncMock()

    due = await scheduler.get_due_events(t, state_engine=state_engine)
    assert len(due) == 1
    assert due[0]["action"] == "triggered"

    # Trigger is removed after firing (one-shot)
    due = await scheduler.get_due_events(t, state_engine=state_engine)
    assert due == []


@pytest.mark.asyncio
async def test_trigger_does_not_fire_without_state_engine():
    """Trigger events require state_engine; without it, they don't fire."""
    scheduler = WorldScheduler()
    t = _utc()

    scheduler.register_trigger(
        condition="True",
        event_def={"action": "triggered"},
        source="test",
    )

    # No state_engine -> triggers skipped
    due = await scheduler.get_due_events(t, state_engine=None)
    assert due == []


# ---------------------------------------------------------------------------
# Empty scheduler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_scheduler_returns_empty_list():
    """An empty scheduler returns [] for any world_time."""
    scheduler = WorldScheduler()
    due = await scheduler.get_due_events(_utc())
    assert due == []
    assert scheduler.pending_count == 0


# ---------------------------------------------------------------------------
# Pending count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_count():
    """pending_count reflects all event types."""
    scheduler = WorldScheduler()
    t = _utc()

    scheduler.register_event(t, {"action": "a"}, source="test")
    scheduler.register_recurring(60, {"action": "b"}, source="test")
    scheduler.register_trigger("True", {"action": "c"}, source="test")

    assert scheduler.pending_count == 3
