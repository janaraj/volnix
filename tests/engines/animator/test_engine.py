"""Tests for volnix.engines.animator.engine -- WorldAnimatorEngine.

Covers: static mode, dynamic mode, reactive mode, event execution,
        creativity budget, configure(), probabilistic events.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from volnix.engines.animator.context import AnimatorContext
from volnix.engines.animator.engine import WorldAnimatorEngine, _parse_duration
from volnix.engines.world_compiler.plan import WorldPlan
from volnix.reality.dimensions import (
    BoundaryDimension,
    ComplexityDimension,
    ReliabilityDimension,
    WorldConditions,
)
from volnix.scheduling.scheduler import WorldScheduler


def _utc(**kwargs):
    defaults = {"year": 2026, "month": 3, "day": 22, "hour": 12, "minute": 0, "second": 0}
    defaults.update(kwargs)
    return datetime(**defaults, tzinfo=UTC)


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
    scheduler.register_event(
        t,
        {
            "actor_id": "npc1",
            "service_id": "gmail",
            "action": "send_email",
            "input_data": {"subject": "test"},
        },
        source="test",
    )

    results = await engine.tick(t)
    assert len(results) >= 1
    mock_app.handle_action.assert_called()


@pytest.mark.asyncio
async def test_dynamic_mode_organic_events():
    """Dynamic mode: organic events from generator are returned (mocked LLM)."""
    from volnix.llm.types import LLMResponse

    mock_app = AsyncMock()
    mock_app.handle_action = AsyncMock(return_value={"status": "ok"})
    mock_llm = AsyncMock()
    mock_llm.route = AsyncMock(
        return_value=LLMResponse(
            content='[{"actor_id": "npc1", "service_id": "world", "action": "npc_action", "input_data": {}, "sub_type": "organic"}]',
            provider="mock",
            model="mock",
            latency_ms=0,
        )
    )

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
    from volnix.core.events import WorldEvent
    from volnix.core.types import ActorId, ServiceId, Timestamp
    from volnix.llm.types import LLMResponse

    mock_app = AsyncMock()
    mock_app.handle_action = AsyncMock(return_value={"status": "ok"})
    mock_llm = AsyncMock()
    mock_llm.route = AsyncMock(
        return_value=LLMResponse(
            content='[{"actor_id": "npc1", "service_id": "world", "action": "react", "input_data": {}, "sub_type": "organic"}]',
            provider="mock",
            model="mock",
            latency_ms=0,
        )
    )

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
    from volnix.core.events import AnimatorEvent

    assert isinstance(published, AnimatorEvent)
    assert published.sub_type == "scheduled"


# ---------------------------------------------------------------------------
# Creativity budget
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_creativity_budget_respected():
    """Organic events are capped at creativity_budget_per_tick."""
    from volnix.llm.types import LLMResponse

    mock_app = AsyncMock()
    mock_app.handle_action = AsyncMock(return_value={"status": "ok"})
    mock_llm = AsyncMock()

    # LLM returns 5 events, but budget is 2
    events_json = (
        "["
        + ",".join(
            [
                f'{{"actor_id":"npc{i}","service_id":"world","action":"a{i}","input_data":{{}},"sub_type":"organic"}}'
                for i in range(5)
            ]
        )
        + "]"
    )
    mock_llm.route = AsyncMock(
        return_value=LLMResponse(
            content=events_json,
            provider="mock",
            model="mock",
            latency_ms=0,
        )
    )

    engine, scheduler = await _setup_engine(
        behavior="dynamic",
        mock_app=mock_app,
        mock_llm=mock_llm,
        animator_settings={"creativity_budget_per_tick": 2},
        conditions=WorldConditions(),
    )

    await engine.tick(_utc())
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
async def test_dynamic_mode_without_llm_produces_no_events():
    """Dynamic mode without LLM router produces no events (organic generation requires LLM)."""
    conditions = WorldConditions(
        reliability=ReliabilityDimension(failures=100, timeouts=0, degradation=100),
        complexity=ComplexityDimension(volatility=100),
        boundaries=BoundaryDimension(boundary_gaps=100),
    )

    engine, scheduler = await _setup_engine(behavior="dynamic", conditions=conditions)

    # Without LLM, tick should produce no events (probabilistic path removed,
    # organic path requires LLM)
    results = await engine.tick(_utc())
    assert results == []


@pytest.mark.asyncio
async def test_probabilistic_events_with_zero_conditions():
    """Zero conditions = zero probabilistic events."""
    conditions = WorldConditions()  # All zeros
    context = AnimatorContext(_make_plan(conditions=conditions))

    engine, scheduler = await _setup_engine(behavior="dynamic", conditions=conditions)

    events = engine._generate_probabilistic_events(context, _utc())
    assert events == []


# ---------------------------------------------------------------------------
# _parse_at_time (P2 — one-shot scheduled event helper)
# ---------------------------------------------------------------------------


from volnix.engines.animator.engine import _parse_at_time  # noqa: E402


def test_parse_at_time_relative_seconds():
    now = datetime(2026, 4, 11, 12, 0, 0, tzinfo=UTC)
    result = _parse_at_time("60s", now=now)
    assert result == datetime(2026, 4, 11, 12, 1, 0, tzinfo=UTC)


def test_parse_at_time_relative_minutes():
    now = datetime(2026, 4, 11, 12, 0, 0, tzinfo=UTC)
    result = _parse_at_time("5m", now=now)
    assert result == datetime(2026, 4, 11, 12, 5, 0, tzinfo=UTC)


def test_parse_at_time_relative_hours():
    now = datetime(2026, 4, 11, 12, 0, 0, tzinfo=UTC)
    result = _parse_at_time("2h", now=now)
    assert result == datetime(2026, 4, 11, 14, 0, 0, tzinfo=UTC)


def test_parse_at_time_absolute_iso_with_z():
    """ISO-8601 with Z suffix is normalized to +00:00 and parsed."""
    result = _parse_at_time("2026-04-11T00:01:30Z")
    assert result == datetime(2026, 4, 11, 0, 1, 30, tzinfo=UTC)


def test_parse_at_time_absolute_iso_with_offset():
    """ISO-8601 with explicit UTC offset parses correctly."""
    result = _parse_at_time("2026-04-11T00:01:30+00:00")
    assert result == datetime(2026, 4, 11, 0, 1, 30, tzinfo=UTC)


def test_parse_at_time_invalid_returns_none():
    """Malformed strings return None instead of raising."""
    assert _parse_at_time("not a time") is None
    assert _parse_at_time("") is None
    # Dict or non-string input handled defensively
    assert _parse_at_time(None) is None  # type: ignore[arg-type]
    assert _parse_at_time(123) is None  # type: ignore[arg-type]


def test_parse_at_time_naive_iso_assumed_utc():
    """ISO-8601 without timezone info is treated as UTC."""
    result = _parse_at_time("2026-04-11T12:30:00")
    assert result == datetime(2026, 4, 11, 12, 30, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# at_time scheduled events (P2 — YAML integration)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_at_time_relative_duration_registers_one_shot():
    """YAML at_time with relative duration registers as a one-shot event.

    Uses approximately-now as the reference time and asserts the fire time
    lands ~60s in the future (with some tolerance for clock drift).
    """
    engine, scheduler = await _setup_engine(
        behavior="dynamic",
        animator_settings={
            "scheduled_events": [
                {
                    "at_time": "60s",
                    "actor_id": "test_actor",
                    "service_id": "notion",
                    "action": "pages.update",
                    "input_data": {"page_ref": "test"},
                },
            ],
        },
    )

    # Should have exactly 1 one-shot event registered, 0 recurring, 0 trigger.
    assert len(scheduler._one_shot) == 1
    assert len(scheduler._recurring) == 0
    assert len(scheduler._triggers) == 0

    # Fire time should be ~now + 60s (tolerate 5 seconds of test drift).
    now = datetime.now(tz=UTC)
    fire_time = scheduler._one_shot[0].fire_time
    delta_seconds = (fire_time - now).total_seconds()
    assert 55 <= delta_seconds <= 65, (
        f"Expected fire_time ~60s from now, got delta={delta_seconds}s"
    )


@pytest.mark.asyncio
async def test_at_time_absolute_iso_registers_one_shot():
    """YAML at_time with absolute ISO-8601 timestamp registers correctly."""
    future = "2030-01-01T00:00:00Z"
    engine, scheduler = await _setup_engine(
        behavior="dynamic",
        animator_settings={
            "scheduled_events": [
                {
                    "at_time": future,
                    "actor_id": "scheduler_test",
                    "service_id": "notion",
                    "action": "pages.update",
                    "input_data": {},
                },
            ],
        },
    )

    assert len(scheduler._one_shot) == 1
    fire_time = scheduler._one_shot[0].fire_time
    assert fire_time == datetime(2030, 1, 1, 0, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_at_time_invalid_format_logs_warning_and_skips(caplog):
    """Malformed at_time skips the event and logs a warning."""
    import logging

    with caplog.at_level(logging.WARNING, logger="volnix.engines.animator.engine"):
        engine, scheduler = await _setup_engine(
            behavior="dynamic",
            animator_settings={
                "scheduled_events": [
                    {
                        "at_time": "not a valid time",
                        "actor_id": "bad_actor",
                        "service_id": "notion",
                        "action": "pages.update",
                    },
                ],
            },
        )

    # No event registered
    assert len(scheduler._one_shot) == 0
    assert len(scheduler._recurring) == 0
    # Warning was logged explaining why
    warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("Invalid at_time" in msg for msg in warning_msgs), (
        f"Expected 'Invalid at_time' warning. Got: {warning_msgs}"
    )


@pytest.mark.asyncio
async def test_at_time_event_fires_once_then_is_removed():
    """An at_time event fires once when due, then is removed from the scheduler."""
    past = "2020-01-01T00:00:00Z"  # in the past — will be due immediately
    engine, scheduler = await _setup_engine(
        behavior="dynamic",
        animator_settings={
            "scheduled_events": [
                {
                    "at_time": past,
                    "actor_id": "past_event",
                    "service_id": "notion",
                    "action": "pages.update",
                    "input_data": {},
                },
            ],
        },
    )
    assert len(scheduler._one_shot) == 1

    # First call to get_due_events fires the event and removes it.
    due = await scheduler.get_due_events(_utc(), state_engine=None)
    assert len(due) == 1
    assert len(scheduler._one_shot) == 0

    # Second call returns nothing — one-shot events are truly one-shot.
    due_again = await scheduler.get_due_events(_utc(), state_engine=None)
    assert due_again == []


@pytest.mark.asyncio
async def test_mixed_interval_trigger_and_at_time_events():
    """All three scheduled-event formats can coexist in one blueprint."""
    engine, scheduler = await _setup_engine(
        behavior="dynamic",
        animator_settings={
            "scheduled_events": [
                {"interval": "5m", "action": "recurring_check"},
                {"trigger": "True", "action": "trigger_check"},
                {
                    "at_time": "60s",
                    "action": "one_shot_event",
                    "actor_id": "test",
                    "service_id": "notion",
                },
            ],
        },
    )

    # Each format ends up in its own scheduler bucket.
    assert len(scheduler._recurring) == 1
    assert len(scheduler._triggers) == 1
    assert len(scheduler._one_shot) == 1
    assert scheduler.pending_count == 3


@pytest.mark.asyncio
async def test_scheduled_event_with_no_timing_key_is_skipped(caplog):
    """An event with none of interval/trigger/at_time is skipped with a warning.

    Prevents silent drops that make blueprint debugging miserable.
    """
    import logging

    with caplog.at_level(logging.WARNING, logger="volnix.engines.animator.engine"):
        engine, scheduler = await _setup_engine(
            behavior="dynamic",
            animator_settings={
                "scheduled_events": [
                    {
                        "actor_id": "orphan",
                        "service_id": "notion",
                        "action": "pages.update",
                        # No interval, trigger, or at_time — orphan event
                    },
                ],
            },
        )

    # Nothing registered
    assert scheduler.pending_count == 0
    warning_msgs = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("no interval/trigger/at_time" in msg for msg in warning_msgs), (
        f"Expected warning about missing timing key. Got: {warning_msgs}"
    )


@pytest.mark.asyncio
async def test_at_time_static_mode_still_registers():
    """Scheduled events are registered regardless of behavior mode.

    Static mode affects the animator's tick() behavior (returns [] for
    organic generation), but the scheduler is a shared primitive and
    registration happens during configure() regardless of behavior. The
    event would only fire if something else polls the scheduler; for
    static mode the animator never does.

    This test documents the current behavior — if we later decide to
    skip registration in static mode, we'll update this test.
    """
    engine, scheduler = await _setup_engine(
        behavior="static",
        animator_settings={
            "scheduled_events": [
                {
                    "at_time": "60s",
                    "actor_id": "test",
                    "service_id": "notion",
                    "action": "pages.update",
                },
            ],
        },
    )
    # Event is registered even in static mode
    assert len(scheduler._one_shot) == 1
