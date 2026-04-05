"""Integration tests for the simulation loop with the Animator.

Covers: compile world -> configure animator -> tick -> verify events.
Tests static and dynamic modes end-to-end through the real pipeline.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from volnix.engines.world_compiler.plan import WorldPlan
from volnix.reality.dimensions import (
    ReliabilityDimension,
    WorldConditions,
)
from volnix.scheduling.scheduler import WorldScheduler


def _utc(**kwargs):
    defaults = {"year": 2026, "month": 3, "day": 22, "hour": 12}
    defaults.update(kwargs)
    return datetime(**defaults, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plan(behavior: str = "dynamic", conditions=None, animator_settings=None):
    """Create a WorldPlan for integration testing."""
    return WorldPlan(
        name="integration-test-world",
        description="Integration test world for simulation loop",
        behavior=behavior,
        conditions=conditions or WorldConditions(),
        animator_settings=animator_settings or {},
    )


# ---------------------------------------------------------------------------
# Static mode: zero animator events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_static_mode_zero_animator_events():
    """Static mode: animator produces no events on tick."""
    from volnix.engines.animator.engine import WorldAnimatorEngine

    engine = WorldAnimatorEngine()
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()

    await engine.initialize({}, bus)

    plan = _make_plan(behavior="static")
    scheduler = WorldScheduler()
    await engine.configure(plan, scheduler)

    # Tick should return empty
    results = await engine.tick(_utc())
    assert results == []

    # No events published to bus
    bus.publish.assert_not_called()


# ---------------------------------------------------------------------------
# Dynamic mode: events generated and executed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dynamic_mode_scheduled_events_executed():
    """Dynamic mode: scheduled events are picked up and executed through app."""
    from volnix.engines.animator.engine import WorldAnimatorEngine

    mock_app = AsyncMock()
    mock_app.handle_action = AsyncMock(return_value={"status": "ok"})

    engine = WorldAnimatorEngine()
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()

    await engine.initialize({"_app": mock_app}, bus)

    plan = _make_plan(behavior="dynamic")
    scheduler = WorldScheduler()
    await engine.configure(plan, scheduler)

    # Register a one-shot event
    t = _utc()
    scheduler.register_event(t, {
        "actor_id": "npc_support",
        "service_id": "gmail",
        "action": "send_reminder",
        "input_data": {"subject": "Follow up"},
        "sub_type": "scheduled",
    }, source="test")

    results = await engine.tick(t)
    assert len(results) >= 1

    # App pipeline was called
    mock_app.handle_action.assert_called_once_with(
        actor_id="npc_support",
        service_id="gmail",
        action="send_reminder",
        input_data={"subject": "Follow up"},
        world_time=t,
    )

    # AnimatorEvent was published
    bus.publish.assert_called()
    published = bus.publish.call_args_list[0][0][0]
    from volnix.core.events import AnimatorEvent
    assert isinstance(published, AnimatorEvent)
    assert published.sub_type == "scheduled"


@pytest.mark.asyncio
async def test_dynamic_mode_without_llm_no_events():
    """Dynamic mode without LLM: no events (probabilistic removed, organic needs LLM)."""
    from volnix.engines.animator.engine import WorldAnimatorEngine

    mock_app = AsyncMock()
    mock_app.handle_action = AsyncMock(return_value={"status": "ok"})

    conditions = WorldConditions(
        reliability=ReliabilityDimension(failures=100, timeouts=0, degradation=100),
    )

    engine = WorldAnimatorEngine()
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()

    await engine.initialize({"_app": mock_app}, bus)

    plan = _make_plan(behavior="dynamic", conditions=conditions)
    scheduler = WorldScheduler()
    await engine.configure(plan, scheduler)

    results = await engine.tick(_utc())
    # Without LLM, organic generation can't run — no events produced
    assert len(results) == 0
    assert mock_app.handle_action.call_count == 0


# ---------------------------------------------------------------------------
# Scheduler shared across engines
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_shared_across_engines():
    """WorldScheduler can receive events from any source and animator ticks them."""
    from volnix.engines.animator.engine import WorldAnimatorEngine

    mock_app = AsyncMock()
    mock_app.handle_action = AsyncMock(return_value={"status": "ok"})

    engine = WorldAnimatorEngine()
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()

    await engine.initialize({"_app": mock_app}, bus)

    plan = _make_plan(behavior="dynamic")
    scheduler = WorldScheduler()
    await engine.configure(plan, scheduler)

    # Another engine registers an event on the shared scheduler
    t = _utc()
    scheduler.register_event(t, {
        "actor_id": "system",
        "service_id": "world",
        "action": "approval_timeout",
        "input_data": {"hold_id": "hold_001"},
        "sub_type": "scheduled",
    }, source="policy_engine")

    results = await engine.tick(t)
    # The policy engine's event should be picked up by the animator
    assert any(
        call.kwargs.get("action") == "approval_timeout" or
        (len(call.args) >= 3 and call.args[2] == "approval_timeout")
        for call in mock_app.handle_action.call_args_list
    ) or mock_app.handle_action.call_count >= 1
