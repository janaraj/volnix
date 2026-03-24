"""Tests for terrarium.simulation.runner.SimulationRunner."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from terrarium.core.envelope import ActionEnvelope
from terrarium.core.events import WorldEvent
from terrarium.core.types import (
    ActionSource,
    ActorId,
    EnvelopePriority,
    ServiceId,
    Timestamp,
)
from terrarium.simulation.config import SimulationRunnerConfig
from terrarium.simulation.event_queue import EventQueue
from terrarium.simulation.runner import SimulationRunner, SimulationStatus, StopReason

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_envelope(
    actor_id: str = "actor-1",
    logical_time: float = 0.0,
    source: ActionSource = ActionSource.EXTERNAL,
    priority: EnvelopePriority = EnvelopePriority.EXTERNAL,
    action_type: str = "test_action",
) -> ActionEnvelope:
    return ActionEnvelope(
        actor_id=ActorId(actor_id),
        source=source,
        action_type=action_type,
        target_service=ServiceId("svc"),
        logical_time=logical_time,
        priority=priority,
    )


def _make_world_event(actor_id: str = "actor-1") -> WorldEvent:
    now = datetime.now(UTC)
    return WorldEvent(
        event_type="world.test_action",
        timestamp=Timestamp(world_time=now, wall_time=now, tick=1),
        actor_id=ActorId(actor_id),
        service_id=ServiceId("svc"),
        action="test_action",
    )


def _make_runner(
    queue: EventQueue | None = None,
    pipeline_executor: AsyncMock | None = None,
    config: SimulationRunnerConfig | None = None,
    agency_engine: AsyncMock | None = None,
    animator: AsyncMock | None = None,
    budget_checker: AsyncMock | None = None,
) -> SimulationRunner:
    """Build a SimulationRunner with sensible defaults for testing."""
    q = queue or EventQueue()
    executor = pipeline_executor or AsyncMock(return_value=_make_world_event())
    cfg = config or SimulationRunnerConfig(stop_on_empty_queue=True)
    return SimulationRunner(
        event_queue=q,
        pipeline_executor=executor,
        agency_engine=agency_engine,
        animator=animator,
        budget_checker=budget_checker,
        config=cfg,
    )


# ---------------------------------------------------------------------------
# End-condition tests
# ---------------------------------------------------------------------------


class TestEndConditions:
    """Tests for simulation end conditions."""

    async def test_empty_queue_stops(self) -> None:
        """Runner stops with QUEUE_EMPTY when queue is empty and stop_on_empty_queue is True."""
        runner = _make_runner()
        reason = await runner.run()
        assert reason == StopReason.QUEUE_EMPTY
        assert runner.status == SimulationStatus.COMPLETED

    async def test_max_events_stops(self) -> None:
        """Runner stops after max_total_events are processed."""
        q = EventQueue()
        config = SimulationRunnerConfig(max_total_events=3, stop_on_empty_queue=False)

        # Pipeline returns a world event each time -> counts as processed
        executor = AsyncMock(return_value=_make_world_event())

        runner = _make_runner(queue=q, pipeline_executor=executor, config=config)

        # Submit enough envelopes to exceed the limit
        for i in range(10):
            q.submit(_make_envelope(logical_time=float(i)))

        reason = await runner.run()
        assert reason == StopReason.MAX_EVENTS_REACHED
        assert runner.total_events_processed == 3

    async def test_max_time_stops(self) -> None:
        """Runner stops when logical time exceeds max_logical_time."""
        q = EventQueue()
        config = SimulationRunnerConfig(max_logical_time=100.0, stop_on_empty_queue=False)

        executor = AsyncMock(return_value=_make_world_event())
        runner = _make_runner(queue=q, pipeline_executor=executor, config=config)

        # Submit an envelope at time 200 -- beyond the 100.0 limit
        q.submit(_make_envelope(logical_time=50.0))
        q.submit(_make_envelope(logical_time=200.0))

        reason = await runner.run()
        assert reason == StopReason.MAX_TIME_REACHED

    async def test_manual_stop(self) -> None:
        """Runner stops with MANUAL_STOP when stop() is called."""
        q = EventQueue()
        config = SimulationRunnerConfig(stop_on_empty_queue=False)
        executor = AsyncMock(return_value=_make_world_event())
        runner = _make_runner(queue=q, pipeline_executor=executor, config=config)

        # Submit some envelopes so the loop doesn't exit from empty queue
        for i in range(100):
            q.submit(_make_envelope(logical_time=float(i)))

        async def stop_after_delay() -> None:
            await asyncio.sleep(0.05)
            await runner.stop()

        # Run both concurrently
        stop_task = asyncio.create_task(stop_after_delay())
        reason = await runner.run()
        await stop_task

        assert reason == StopReason.MANUAL_STOP

    async def test_mission_completed_stops(self) -> None:
        """Runner stops with MISSION_COMPLETED when mission is marked complete."""
        q = EventQueue()
        config = SimulationRunnerConfig(stop_on_empty_queue=False)
        executor = AsyncMock(return_value=_make_world_event())
        runner = _make_runner(queue=q, pipeline_executor=executor, config=config)

        runner.set_mission("Complete the onboarding flow")

        # Submit envelopes
        for i in range(10):
            q.submit(_make_envelope(logical_time=float(i)))

        # Mark mission as complete before first iteration via pipeline side-effect
        call_count = 0

        async def mark_complete(env: ActionEnvelope) -> WorldEvent:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                runner.mark_mission_completed()
            return _make_world_event()

        executor.side_effect = mark_complete

        reason = await runner.run()
        assert reason == StopReason.MISSION_COMPLETED

    async def test_loop_breaker_stops(self) -> None:
        """Runner stops with LOOP_BREAKER after too many internal events without external."""
        q = EventQueue()
        config = SimulationRunnerConfig(
            loop_breaker_threshold=5,
            stop_on_empty_queue=False,
            max_actions_per_actor_per_window=1000,
        )
        executor = AsyncMock(return_value=_make_world_event())
        runner = _make_runner(queue=q, pipeline_executor=executor, config=config)

        # All envelopes are INTERNAL -- no external input
        for i in range(20):
            q.submit(
                _make_envelope(
                    logical_time=float(i),
                    source=ActionSource.INTERNAL,
                    priority=EnvelopePriority.INTERNAL,
                )
            )

        reason = await runner.run()
        assert reason == StopReason.LOOP_BREAKER


# ---------------------------------------------------------------------------
# Runaway protection tests
# ---------------------------------------------------------------------------


class TestRunawayProtection:
    """Tests for runaway loop protection."""

    async def test_runaway_actor_protection(self) -> None:
        """Envelopes from one actor exceeding window limit are dropped."""
        q = EventQueue()
        config = SimulationRunnerConfig(
            max_actions_per_actor_per_window=3,
            stop_on_empty_queue=True,
            tick_interval_seconds=60.0,
        )
        executor = AsyncMock(return_value=_make_world_event())
        runner = _make_runner(queue=q, pipeline_executor=executor, config=config)

        # Submit 10 envelopes from same actor, all at same logical time
        for _ in range(10):
            q.submit(
                _make_envelope(
                    actor_id="busy-actor",
                    logical_time=1.0,
                    source=ActionSource.INTERNAL,
                    priority=EnvelopePriority.INTERNAL,
                )
            )

        await runner.run()

        # Only max_actions_per_actor_per_window should have been processed
        assert runner.total_events_processed <= config.max_actions_per_actor_per_window

    async def test_runaway_environment_protection(self) -> None:
        """Environment reactions exceeding window limit are dropped."""
        q = EventQueue()
        config = SimulationRunnerConfig(
            max_environment_reactions_per_window=3,
            stop_on_empty_queue=True,
            tick_interval_seconds=60.0,
        )
        executor = AsyncMock(return_value=_make_world_event())
        runner = _make_runner(queue=q, pipeline_executor=executor, config=config)

        # Submit 10 ENVIRONMENT envelopes at same time
        for _ in range(10):
            q.submit(
                _make_envelope(
                    logical_time=1.0,
                    source=ActionSource.ENVIRONMENT,
                    priority=EnvelopePriority.ENVIRONMENT,
                )
            )

        await runner.run()

        assert runner.total_events_processed <= config.max_environment_reactions_per_window


# ---------------------------------------------------------------------------
# Agent connect/disconnect tests
# ---------------------------------------------------------------------------


class TestAgentConnectivity:
    """Tests for external agent tracking."""

    async def test_agent_connect_disconnect(self) -> None:
        """Agents can be connected and disconnected."""
        runner = _make_runner()
        agent = ActorId("agent-1")

        runner.connect_agent(agent)
        assert agent in runner._connected_agents

        runner.disconnect_agent(agent)
        assert agent not in runner._connected_agents

    async def test_disconnect_nonexistent_agent_is_safe(self) -> None:
        """Disconnecting an agent that was never connected does not raise."""
        runner = _make_runner()
        runner.disconnect_agent(ActorId("ghost"))  # should not raise


# ---------------------------------------------------------------------------
# Pipeline execution tests
# ---------------------------------------------------------------------------


class TestPipelineExecution:
    """Tests for the main loop processing path."""

    async def test_basic_loop_processes_envelope(self) -> None:
        """A single envelope is dequeued, executed through pipeline, and counted."""
        q = EventQueue()
        event = _make_world_event()
        executor = AsyncMock(return_value=event)

        runner = _make_runner(queue=q, pipeline_executor=executor)

        q.submit(_make_envelope(logical_time=1.0))
        reason = await runner.run()

        assert reason == StopReason.QUEUE_EMPTY
        assert runner.total_events_processed == 1
        executor.assert_called_once()

    async def test_pipeline_rejection_not_counted(self) -> None:
        """When pipeline returns None (rejection), the event is not counted."""
        q = EventQueue()
        executor = AsyncMock(return_value=None)

        runner = _make_runner(queue=q, pipeline_executor=executor)

        q.submit(_make_envelope(logical_time=1.0))
        reason = await runner.run()

        assert reason == StopReason.QUEUE_EMPTY
        assert runner.total_events_processed == 0

    async def test_agency_engine_notified_on_event(self) -> None:
        """AgencyEngine.notify is called after a successful pipeline execution."""
        q = EventQueue()
        event = _make_world_event()
        executor = AsyncMock(return_value=event)

        agency = AsyncMock()
        agency.notify = AsyncMock(return_value=[])
        agency.check_scheduled_actions = AsyncMock(return_value=[])
        agency.has_scheduled_actions = lambda: False

        runner = _make_runner(queue=q, pipeline_executor=executor, agency_engine=agency)
        q.submit(_make_envelope(logical_time=1.0))

        await runner.run()

        agency.notify.assert_called_once_with(event)

    async def test_animator_notified_on_event(self) -> None:
        """Animator.notify_event is called after a successful pipeline execution."""
        q = EventQueue()
        event = _make_world_event()
        executor = AsyncMock(return_value=event)

        animator = AsyncMock()
        animator.notify_event = AsyncMock(return_value=[])
        animator.check_scheduled_events = AsyncMock(return_value=[])
        animator.has_scheduled_events = lambda: False

        runner = _make_runner(queue=q, pipeline_executor=executor, animator=animator)
        q.submit(_make_envelope(logical_time=1.0))

        await runner.run()

        animator.notify_event.assert_called_once_with(event)

    async def test_max_envelopes_per_event_capped(self) -> None:
        """Agency engine response envelopes are capped at max_envelopes_per_event."""
        q = EventQueue()
        event = _make_world_event()
        executor = AsyncMock(return_value=event)

        config = SimulationRunnerConfig(
            max_envelopes_per_event=2,
            stop_on_empty_queue=True,
            max_total_events=100,
        )

        # Agency returns 10 response envelopes on first call, then empty
        response_envelopes = [_make_envelope(logical_time=float(i + 10)) for i in range(10)]
        call_count = 0

        async def notify_once(ev: WorldEvent) -> list[ActionEnvelope]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return response_envelopes
            return []

        agency = AsyncMock()
        agency.notify = AsyncMock(side_effect=notify_once)
        agency.check_scheduled_actions = AsyncMock(return_value=[])
        agency.has_scheduled_actions = lambda: False

        runner = _make_runner(
            queue=q, pipeline_executor=executor, config=config, agency_engine=agency
        )
        q.submit(_make_envelope(logical_time=1.0))

        await runner.run()

        # Initial envelope processed + 2 capped from agency = 3 total
        assert runner.total_events_processed == 3


class TestStatusTracking:
    """Tests for status and property tracking."""

    async def test_initial_status_is_idle(self) -> None:
        """Runner starts in IDLE status."""
        runner = _make_runner()
        assert runner.status == SimulationStatus.IDLE
        assert runner.stop_reason is None

    async def test_completed_status_after_run(self) -> None:
        """Runner is in COMPLETED status after normal termination."""
        runner = _make_runner()
        await runner.run()
        assert runner.status == SimulationStatus.COMPLETED

    async def test_stopped_status_after_manual_stop(self) -> None:
        """Runner is in STOPPED status after manual stop() call."""
        runner = _make_runner()
        await runner.stop()
        assert runner.status == SimulationStatus.STOPPED
        assert runner.stop_reason == StopReason.MANUAL_STOP


# ---------------------------------------------------------------------------
# Concurrency and integration tests
# ---------------------------------------------------------------------------


class TestBudgetAndDisconnect:
    """Tests for budget_checker and agent disconnect end conditions."""

    async def test_budget_checker_stops_simulation(self) -> None:
        """budget_checker callback returns True -> ALL_BUDGETS_EXHAUSTED."""
        q = EventQueue()
        executor = AsyncMock(return_value=_make_world_event())
        budget_checker = AsyncMock(return_value=True)
        config = SimulationRunnerConfig(stop_on_empty_queue=False)

        runner = _make_runner(
            queue=q,
            pipeline_executor=executor,
            budget_checker=budget_checker,
            config=config,
        )

        # Submit envelopes so the loop doesn't exit from empty queue
        for i in range(10):
            q.submit(_make_envelope(logical_time=float(i)))

        reason = await runner.run()

        assert reason == StopReason.ALL_BUDGETS_EXHAUSTED
        assert runner.status == SimulationStatus.COMPLETED
        budget_checker.assert_called()

    async def test_all_agents_disconnected_stops(self) -> None:
        """connect_agent -> disconnect_agent -> ALL_AGENTS_DISCONNECTED."""
        q = EventQueue()
        executor = AsyncMock(return_value=_make_world_event())
        config = SimulationRunnerConfig(stop_on_empty_queue=False)

        runner = _make_runner(queue=q, pipeline_executor=executor, config=config)

        agent = ActorId("agent-ext-1")
        runner.connect_agent(agent)
        assert agent in runner._connected_agents

        # Submit and process one envelope to advance the loop
        q.submit(_make_envelope(logical_time=1.0))

        # Disconnect agent after one event is processed
        call_count = 0

        async def exec_and_disconnect(env: ActionEnvelope):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                runner.disconnect_agent(agent)
            return _make_world_event()

        executor.side_effect = exec_and_disconnect

        reason = await runner.run()

        assert reason == StopReason.ALL_AGENTS_DISCONNECTED
        assert agent not in runner._connected_agents


class TestReplayLogAndActorState:
    """Tests for replay_log recording and actor state updates in the loop."""

    async def test_replay_log_records_entries(self) -> None:
        """Provide replay_log mock, verify record() called for each event."""
        q = EventQueue()
        event = _make_world_event()
        executor = AsyncMock(return_value=event)

        replay_log = AsyncMock()
        replay_log.record = AsyncMock()

        runner = SimulationRunner(
            event_queue=q,
            pipeline_executor=executor,
            config=SimulationRunnerConfig(stop_on_empty_queue=True),
            replay_log=replay_log,
        )

        q.submit(_make_envelope(logical_time=1.0))
        q.submit(_make_envelope(logical_time=2.0))
        q.submit(_make_envelope(logical_time=3.0))

        await runner.run()

        assert runner.total_events_processed == 3
        assert replay_log.record.call_count == 3

    async def test_actor_state_updated_in_loop(self) -> None:
        """Provide agency mock with update_states_for_event. Verify it's called."""
        q = EventQueue()
        event = _make_world_event()
        executor = AsyncMock(return_value=event)

        agency = AsyncMock()
        agency.notify = AsyncMock(return_value=[])
        agency.check_scheduled_actions = AsyncMock(return_value=[])
        agency.has_scheduled_actions = lambda: False
        agency.update_states_for_event = AsyncMock()

        runner = _make_runner(queue=q, pipeline_executor=executor, agency_engine=agency)
        q.submit(_make_envelope(logical_time=1.0))
        q.submit(_make_envelope(logical_time=2.0))

        await runner.run()

        assert runner.total_events_processed == 2
        assert agency.update_states_for_event.call_count == 2


class TestMaxEnvelopeCapping:
    """Tests for max_envelopes_per_event capping agency and animator outputs."""

    async def test_max_envelopes_per_event_caps_agency(self) -> None:
        """Agency returns 100 envelopes -> only max_envelopes_per_event submitted."""
        q = EventQueue()
        event = _make_world_event()
        executor = AsyncMock(return_value=event)

        config = SimulationRunnerConfig(
            max_envelopes_per_event=3,
            stop_on_empty_queue=True,
            max_total_events=200,
        )

        # Agency returns 100 response envelopes on first call, then empty
        big_response = [
            _make_envelope(logical_time=float(i + 10)) for i in range(100)
        ]
        call_count = 0

        async def notify_once(ev):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return big_response
            return []

        agency = AsyncMock()
        agency.notify = AsyncMock(side_effect=notify_once)
        agency.check_scheduled_actions = AsyncMock(return_value=[])
        agency.has_scheduled_actions = lambda: False
        agency.update_states_for_event = AsyncMock()

        runner = _make_runner(
            queue=q, pipeline_executor=executor, config=config, agency_engine=agency,
        )
        q.submit(_make_envelope(logical_time=1.0))

        await runner.run()

        # 1 initial + 3 capped from agency = 4 total
        assert runner.total_events_processed == 4

    async def test_max_envelopes_per_event_caps_animator(self) -> None:
        """Animator returns 100 envelopes -> only max_envelopes_per_event submitted."""
        q = EventQueue()
        event = _make_world_event()
        executor = AsyncMock(return_value=event)

        config = SimulationRunnerConfig(
            max_envelopes_per_event=3,
            stop_on_empty_queue=True,
            max_total_events=200,
        )

        big_response = [
            _make_envelope(
                logical_time=float(i + 10),
                source=ActionSource.ENVIRONMENT,
                priority=EnvelopePriority.ENVIRONMENT,
            )
            for i in range(100)
        ]
        call_count = 0

        async def notify_once(ev):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return big_response
            return []

        animator = AsyncMock()
        animator.notify_event = AsyncMock(side_effect=notify_once)
        animator.check_scheduled_events = AsyncMock(return_value=[])
        animator.has_scheduled_events = lambda: False

        runner = _make_runner(
            queue=q, pipeline_executor=executor, config=config, animator=animator,
        )
        q.submit(_make_envelope(logical_time=1.0))

        await runner.run()

        # 1 initial + 3 capped from animator = 4 total
        assert runner.total_events_processed == 4


class TestRunawayProtectionFullLoop:
    """Tests for runaway protection with the full simulation loop."""

    async def test_runaway_actor_protection_in_full_loop(self) -> None:
        """One actor submits 10 actions in 60s window.

        max_actions_per_actor_per_window=5 -> actions 6-10 dropped.
        """
        q = EventQueue()
        event = _make_world_event()
        executor = AsyncMock(return_value=event)

        config = SimulationRunnerConfig(
            max_actions_per_actor_per_window=5,
            stop_on_empty_queue=True,
            tick_interval_seconds=60.0,
            loop_breaker_threshold=100,
        )

        runner = _make_runner(queue=q, pipeline_executor=executor, config=config)

        # All 10 envelopes from same actor, same logical time (within window)
        for _ in range(10):
            q.submit(
                _make_envelope(
                    actor_id="runaway-actor",
                    logical_time=5.0,
                    source=ActionSource.INTERNAL,
                    priority=EnvelopePriority.INTERNAL,
                )
            )

        await runner.run()

        # Only max_actions_per_actor_per_window should have been processed
        assert runner.total_events_processed <= 5

    async def test_runaway_environment_protection_in_full_loop(self) -> None:
        """Animator submits 15 events in 60s window.

        max_environment_reactions_per_window=10 -> events 11-15 dropped.
        """
        q = EventQueue()
        event = _make_world_event()
        executor = AsyncMock(return_value=event)

        config = SimulationRunnerConfig(
            max_environment_reactions_per_window=10,
            stop_on_empty_queue=True,
            tick_interval_seconds=60.0,
        )

        runner = _make_runner(queue=q, pipeline_executor=executor, config=config)

        # All 15 envelopes from environment, same logical time
        for _ in range(15):
            q.submit(
                _make_envelope(
                    logical_time=5.0,
                    source=ActionSource.ENVIRONMENT,
                    priority=EnvelopePriority.ENVIRONMENT,
                )
            )

        await runner.run()

        # Only max_environment_reactions_per_window should have been processed
        assert runner.total_events_processed <= 10
