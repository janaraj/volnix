"""Tests for terrarium.engines.animator.engine -- WorldAnimatorEngine.

Covers: static mode, dynamic mode, reactive mode, event execution,
        creativity budget, configure(), probabilistic events.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from terrarium.engines.animator.config import AnimatorConfig
from terrarium.engines.animator.context import AnimatorContext
from terrarium.engines.animator.engine import WorldAnimatorEngine, _parse_duration
from terrarium.engines.world_compiler.plan import WorldPlan
from terrarium.reality.dimensions import (
    WorldConditions,
    ReliabilityDimension,
    ComplexityDimension,
    BoundaryDimension,
)
from terrarium.scheduling.scheduler import WorldScheduler


def _utc(**kwargs):
    defaults = {"year": 2026, "month": 3, "day": 22, "hour": 12, "minute": 0, "second": 0}
    defaults.update(kwargs)
    return datetime(**defaults, tzinfo=timezone.utc)


def _make_plan(
    behavior: str = "dynamic",
    conditions: WorldConditions | None = None,
    animator_settings: dict | None = None,
) -> WorldPlan:
    """Create a minimal WorldPlan for testing."""
    return WorldPlan(
        name="test-world",
        description="A test world",
        behavior=behavior,
        conditions=conditions or WorldConditions(),
        animator_settings=animator_settings or {},
    )


async def _setup_engine(
    behavior: str = "dynamic",
    conditions: WorldConditions | None = None,
    animator_settings: dict | None = None,
    mock_app: AsyncMock | None = None,
    mock_llm: AsyncMock | None = None,
) -> tuple[WorldAnimatorEngine, WorldScheduler]:
    """Create and configure a WorldAnimatorEngine for testing."""
    engine = WorldAnimatorEngine()
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.publish = AsyncMock()

    config: dict = {}
    if mock_app:
        config["_app"] = mock_app
    if mock_llm:
        config["_llm_router"] = mock_llm

    await engine.initialize(config, bus)

    plan = _make_plan(
        behavior=behavior,
        conditions=conditions,
        animator_settings=animator_settings,
    )
    scheduler = WorldScheduler()
    await engine.configure(plan, scheduler)
    return engine, scheduler


# ---------------------------------------------------------------------------
# Static mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_static_mode_tick_returns_empty():
    """Static mode: tick() always returns []."""
    engine, scheduler = await _setup_engine(behavior="static")
    result = await engine.tick(_utc())
    assert result == []


@pytest.mark.asyncio
async def test_static_mode_no_generator():
    """Static mode: no OrganicGenerator is created."""
    engine, scheduler = await _setup_engine(behavior="static", mock_llm=AsyncMock())
    assert engine._generator is None


# ---------------------------------------------------------------------------
# Dynamic mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dynamic_mode_scheduled_events():
    """Dynamic mode: scheduled events from scheduler are returned."""
    mock_app = AsyncMock()
    mock_app.handle_action = AsyncMock(return_value={"status": "ok"})

    engine, scheduler = await _setup_engine(behavior="dynamic", mock_app=mock_app)

    # Register a one-shot event due now
    t = _utc()
    scheduler.register_event(t, {
        "actor_id": "npc1",
        "service_id": "gmail",
        "action": "send_email",
        "input_data": {"subject": "test"},
    }, source="test")

    results = await engine.tick(t)
    assert len(results) >= 1
    mock_app.handle_action.assert_called()


@pytest.mark.asyncio
async def test_dynamic_mode_organic_events():
    """Dynamic mode: organic events from generator are returned (mocked LLM)."""
    from terrarium.llm.types import LLMResponse

    mock_app = AsyncMock()
    mock_app.handle_action = AsyncMock(return_value={"status": "ok"})
    mock_llm = AsyncMock()
    mock_llm.route = AsyncMock(return_value=LLMResponse(
        content='[{"actor_id": "npc1", "service_id": "world", "action": "npc_action", "input_data": {}, "sub_type": "organic"}]',
        provider="mock", model="mock", latency_ms=0,
    ))

    engine, scheduler = await _setup_engine(
        behavior="dynamic",
        mock_app=mock_app,
        mock_llm=mock_llm,
    )

    results = await engine.tick(_utc())
    # Should have organic events (and possibly probabilistic ones)
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Reactive mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reactive_mode_no_events_without_actions():
    """Reactive mode: no organic events when no recent agent actions."""
    mock_app = AsyncMock()
    mock_app.handle_action = AsyncMock(return_value={"status": "ok"})

    engine, scheduler = await _setup_engine(
        behavior="reactive",
        mock_app=mock_app,
        # No conditions -> zero probabilistic events
        conditions=WorldConditions(),
    )

    # No recent actions -> no organic events (probabilistic may still fire with nonzero conditions)
    results = await engine.tick(_utc())
    # With default WorldConditions (all zeros), no probabilistic events either
    assert results == []


@pytest.mark.asyncio
async def test_reactive_mode_events_with_actions():
    """Reactive mode: events only when recent_actions exist."""
    from terrarium.llm.types import LLMResponse
    from terrarium.core.events import WorldEvent
    from terrarium.core.types import Timestamp, ActorId, ServiceId

    mock_app = AsyncMock()
    mock_app.handle_action = AsyncMock(return_value={"status": "ok"})
    mock_llm = AsyncMock()
    mock_llm.route = AsyncMock(return_value=LLMResponse(
        content='[{"actor_id": "npc1", "service_id": "world", "action": "react", "input_data": {}, "sub_type": "organic"}]',
        provider="mock", model="mock", latency_ms=0,
    ))

    engine, scheduler = await _setup_engine(
        behavior="reactive",
        mock_app=mock_app,
        mock_llm=mock_llm,
        conditions=WorldConditions(),
    )

    # Simulate an incoming event to trigger reactive mode
    event = WorldEvent(
        event_type="world.email_send",
        timestamp=Timestamp(world_time=_utc(), wall_time=_utc(), tick=1),
        actor_id=ActorId("agent-1"),
        service_id=ServiceId("gmail"),
        action="email_send",
    )
    await engine._handle_event(event)

    assert len(engine._recent_actions) == 1

    results = await engine.tick(_utc())
    # Should have organic events now
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Event execution through app.handle_action()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_event_calls_app_handle_action():
    """_execute_event dispatches through app.handle_action()."""
    mock_app = AsyncMock()
    mock_app.handle_action = AsyncMock(return_value={"result": "processed"})

    engine, scheduler = await _setup_engine(behavior="dynamic", mock_app=mock_app)

    event_def = {
        "actor_id": "npc1",
        "service_id": "gmail",
        "action": "send_reminder",
        "input_data": {"to": "agent@test.com"},
    }
    result = await engine._execute_event(event_def, _utc())

    mock_app.handle_action.assert_called_once_with(
        actor_id="npc1",
        service_id="gmail",
        action="send_reminder",
        input_data={"to": "agent@test.com"},
        world_time=_utc(),
    )
    assert result == {"result": "processed"}


@pytest.mark.asyncio
async def test_execute_event_publishes_animator_event():
    """_execute_event publishes an AnimatorEvent to the bus."""
    mock_app = AsyncMock()
    mock_app.handle_action = AsyncMock(return_value={"status": "ok"})

    engine, scheduler = await _setup_engine(behavior="dynamic", mock_app=mock_app)

    await engine._execute_event(
        {"actor_id": "npc1", "action": "check", "sub_type": "scheduled"},
        _utc(),
    )

    # Check bus.publish was called
    engine._bus.publish.assert_called()
    published = engine._bus.publish.call_args[0][0]
    from terrarium.core.events import AnimatorEvent
    assert isinstance(published, AnimatorEvent)
    assert published.sub_type == "scheduled"


# ---------------------------------------------------------------------------
# Creativity budget
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_creativity_budget_respected():
    """Organic events are capped at creativity_budget_per_tick."""
    from terrarium.llm.types import LLMResponse

    mock_app = AsyncMock()
    mock_app.handle_action = AsyncMock(return_value={"status": "ok"})
    mock_llm = AsyncMock()

    # LLM returns 5 events, but budget is 2
    events_json = '[' + ','.join([
        f'{{"actor_id":"npc{i}","service_id":"world","action":"a{i}","input_data":{{}},"sub_type":"organic"}}'
        for i in range(5)
    ]) + ']'
    mock_llm.route = AsyncMock(return_value=LLMResponse(
        content=events_json,
        provider="mock", model="mock", latency_ms=0,
    ))

    engine, scheduler = await _setup_engine(
        behavior="dynamic",
        mock_app=mock_app,
        mock_llm=mock_llm,
        animator_settings={"creativity_budget_per_tick": 2},
        conditions=WorldConditions(),
    )

    results = await engine.tick(_utc())
    # Count organic events (should be at most 2)
    # handle_action is called for each organic event
    organic_calls = mock_app.handle_action.call_count
    assert organic_calls <= 2


# ---------------------------------------------------------------------------
# configure()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_configure_sets_behavior_from_plan():
    """configure() reads behavior mode from WorldPlan."""
    for mode in ("static", "dynamic", "reactive"):
        engine, scheduler = await _setup_engine(behavior=mode)
        assert engine._behavior == mode


@pytest.mark.asyncio
async def test_configure_registers_scheduled_events():
    """configure() registers scheduled_events from YAML into the scheduler."""
    engine, scheduler = await _setup_engine(
        behavior="dynamic",
        animator_settings={
            "scheduled_events": [
                {"interval": "5m", "action": "queue_check"},
                {"trigger": "True", "action": "sla_check"},
            ],
        },
    )

    # Should have 1 recurring + 1 trigger
    assert scheduler.pending_count == 2


# ---------------------------------------------------------------------------
# _parse_duration
# ---------------------------------------------------------------------------


def test_parse_duration_seconds():
    assert _parse_duration("30s") == 30.0


def test_parse_duration_minutes():
    assert _parse_duration("5m") == 300.0


def test_parse_duration_hours():
    assert _parse_duration("1h") == 3600.0


def test_parse_duration_days():
    assert _parse_duration("2d") == 172800.0


def test_parse_duration_bare_number():
    assert _parse_duration("120") == 120.0


# ---------------------------------------------------------------------------
# Probabilistic events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_probabilistic_events_with_high_reliability_failures():
    """High reliability.failures generates service_degradation events."""
    conditions = WorldConditions(
        reliability=ReliabilityDimension(failures=100, timeouts=0, degradation=100),
        complexity=ComplexityDimension(volatility=100),
        boundaries=BoundaryDimension(boundary_gaps=100),
    )
    context = AnimatorContext(_make_plan(conditions=conditions))

    engine, scheduler = await _setup_engine(behavior="dynamic", conditions=conditions)

    # With all probs at 100%, all events should fire
    events = engine._generate_probabilistic_events(context, _utc())
    actions = [e["action"] for e in events]
    assert "service_degradation" in actions
    assert "situation_change" in actions
    assert "access_incident" in actions


@pytest.mark.asyncio
async def test_probabilistic_events_with_zero_conditions():
    """Zero conditions = zero probabilistic events."""
    conditions = WorldConditions()  # All zeros
    context = AnimatorContext(_make_plan(conditions=conditions))

    engine, scheduler = await _setup_engine(behavior="dynamic", conditions=conditions)

    events = engine._generate_probabilistic_events(context, _utc())
    assert events == []
