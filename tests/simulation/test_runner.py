"""Tests for volnix.simulation.runner.SimulationRunner."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from volnix.core.envelope import ActionEnvelope
from volnix.core.events import WorldEvent
from volnix.core.types import (
    ActionSource,
    ActorId,
    EnvelopePriority,
    ServiceId,
    Timestamp,
)
from volnix.simulation.config import SimulationRunnerConfig
from volnix.simulation.event_queue import EventQueue
from volnix.simulation.runner import (
    SimulationRunner,
    SimulationStatus,
    SimulationType,
    StopReason,
)

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
    actor_specs: list[dict[str, str]] | None = None,
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
        actor_specs=actor_specs,
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
        config = SimulationRunnerConfig(stop_on_empty_queue=False, max_total_events=10000)
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
        big_response = [_make_envelope(logical_time=float(i + 10)) for i in range(100)]
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
            queue=q,
            pipeline_executor=executor,
            config=config,
            agency_engine=agency,
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
            queue=q,
            pipeline_executor=executor,
            config=config,
            animator=animator,
        )
        q.submit(_make_envelope(logical_time=1.0))

        await runner.run()

        # 1 initial + 3 capped from animator = 4 total
        assert runner.total_events_processed == 4


class TestTimeAdvancement:
    """Tests for time fast-forward when queue drains in internal-only sims."""

    async def test_internal_only_fast_forwards_to_scheduled_action(self) -> None:
        """Queue drains, scheduled action at tick 13 -> runner fast-forwards and fires it."""
        q = EventQueue()
        event = _make_world_event()
        executor = AsyncMock(return_value=event)

        # Agency mock: scheduled action at tick 13 (780.0s)
        scheduled_time = 780.0
        fired = False

        async def check_scheduled(current_time: float) -> list[ActionEnvelope]:
            nonlocal fired
            if not fired and current_time >= scheduled_time:
                fired = True
                return [
                    _make_envelope(
                        logical_time=current_time,
                        source=ActionSource.INTERNAL,
                        priority=EnvelopePriority.SYSTEM,
                    )
                ]
            return []

        agency = AsyncMock()
        agency.notify = AsyncMock(return_value=[])
        agency.check_scheduled_actions = AsyncMock(side_effect=check_scheduled)
        agency.has_scheduled_actions = lambda: not fired
        agency.next_scheduled_time = lambda: None if fired else scheduled_time
        agency.update_states_for_event = AsyncMock()

        config = SimulationRunnerConfig(
            stop_on_empty_queue=True,
            max_ticks=200,
            tick_interval_seconds=60.0,
        )

        runner = _make_runner(
            queue=q,
            pipeline_executor=executor,
            config=config,
            agency_engine=agency,
        )
        # Force internal-only detection
        runner._simulation_type = SimulationType.INTERNAL_ONLY

        # Submit one initial envelope to start the sim
        q.submit(_make_envelope(logical_time=0.0))

        reason = await runner.run()

        # The scheduled action should have fired and produced an event
        assert fired
        assert runner.total_events_processed >= 2  # initial + scheduled
        assert reason == StopReason.QUEUE_EMPTY

    async def test_internal_only_no_scheduled_actions_stops_cleanly(self) -> None:
        """Internal-only sim, queue drains, no scheduled actions -> QUEUE_EMPTY."""
        q = EventQueue()
        event = _make_world_event()
        executor = AsyncMock(return_value=event)

        agency = AsyncMock()
        agency.notify = AsyncMock(return_value=[])
        agency.check_scheduled_actions = AsyncMock(return_value=[])
        agency.has_scheduled_actions = lambda: False
        agency.next_scheduled_time = lambda: None
        agency.update_states_for_event = AsyncMock()

        runner = _make_runner(
            queue=q,
            pipeline_executor=executor,
            agency_engine=agency,
        )
        runner._simulation_type = SimulationType.INTERNAL_ONLY

        q.submit(_make_envelope(logical_time=0.0))
        reason = await runner.run()

        assert reason == StopReason.QUEUE_EMPTY

    async def test_fast_forward_respects_max_ticks(self) -> None:
        """Scheduled action at tick 100, max_ticks=15 -> TICK_LIMIT after fast-forward."""
        q = EventQueue()
        event = _make_world_event()
        executor = AsyncMock(return_value=event)

        agency = AsyncMock()
        agency.notify = AsyncMock(return_value=[])
        agency.check_scheduled_actions = AsyncMock(return_value=[])
        agency.has_scheduled_actions = lambda: True
        agency.next_scheduled_time = lambda: 6000.0  # tick 100
        agency.update_states_for_event = AsyncMock()

        config = SimulationRunnerConfig(
            stop_on_empty_queue=True,
            max_ticks=15,
            tick_interval_seconds=60.0,
        )

        runner = _make_runner(
            queue=q,
            pipeline_executor=executor,
            config=config,
            agency_engine=agency,
        )
        runner._simulation_type = SimulationType.INTERNAL_ONLY

        q.submit(_make_envelope(logical_time=0.0))
        reason = await runner.run()

        assert reason == StopReason.TICK_LIMIT

    async def test_external_driven_does_not_fast_forward(self) -> None:
        """External-driven sim with scheduled actions -> no fast-forward, QUEUE_EMPTY."""
        q = EventQueue()
        event = _make_world_event()
        executor = AsyncMock(return_value=event)

        agency = AsyncMock()
        agency.notify = AsyncMock(return_value=[])
        agency.check_scheduled_actions = AsyncMock(return_value=[])
        # Scheduled actions exist but should NOT cause fast-forward
        agency.has_scheduled_actions = lambda: False
        agency.next_scheduled_time = lambda: 780.0
        agency.update_states_for_event = AsyncMock()

        runner = _make_runner(
            queue=q,
            pipeline_executor=executor,
            agency_engine=agency,
        )
        # Default is EXTERNAL_DRIVEN (no actor_specs)
        assert runner._simulation_type == SimulationType.EXTERNAL_DRIVEN

        q.submit(_make_envelope(logical_time=0.0))
        reason = await runner.run()

        # Should stop normally, NOT fast-forward
        assert reason == StopReason.QUEUE_EMPTY
        assert q.current_time < 780.0  # time did not jump


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


# ---------------------------------------------------------------------------
# Animator gate tests
# ---------------------------------------------------------------------------


class TestAnimatorGate:
    """Tests for the animator tick interval gate that prevents feedback loops."""

    async def test_animator_respects_tick_interval(self) -> None:
        """tick() fires at most once per animator_tick_interval ticks.

        With interval=5 and 10 events (= 10 ticks in INTERNAL_ONLY),
        tick should fire at tick 0 and tick 5 = exactly 2 times.
        """
        q = EventQueue()
        config = SimulationRunnerConfig(
            max_total_events=10,
            stop_on_empty_queue=False,
            tick_interval_seconds=60.0,
            animator_tick_interval=5,
        )
        executor = AsyncMock(return_value=_make_world_event())

        animator = AsyncMock()
        animator.tick = AsyncMock(return_value=[])  # No organic events
        animator.check_scheduled_events = AsyncMock(return_value=[])
        animator.notify_event = AsyncMock(return_value=[])

        agency = AsyncMock()
        agency.check_scheduled_actions = AsyncMock(return_value=[])
        agency.notify = AsyncMock(return_value=[])
        agency.update_states_for_event = AsyncMock()
        agency.set_tool_executor = lambda ex: None

        runner = _make_runner(
            queue=q,
            pipeline_executor=executor,
            config=config,
            agency_engine=agency,
            animator=animator,
            actor_specs=[{"type": "internal"}],
        )

        # Submit 10 envelopes — each processes as 1 tick in INTERNAL_ONLY
        for i in range(10):
            q.submit(
                _make_envelope(
                    source=ActionSource.INTERNAL,
                    priority=EnvelopePriority.INTERNAL,
                )
            )

        await runner.run()

        # tick() fires at tick 0 (>= -5+5=0) and tick 5 (>= 0+5=5) = 2 calls
        assert animator.tick.call_count == 2
        assert runner.total_events_processed == 10

    async def test_organic_events_not_counted_in_total(self) -> None:
        """Organic events from tick() should not count toward total_events_processed."""
        q = EventQueue()
        # Use stop_on_empty_queue (external-driven) to avoid INTERNAL_ONLY
        # infinite loop.  Pre-submit 1 envelope to start the sim.
        config = SimulationRunnerConfig(
            max_total_events=20,
            stop_on_empty_queue=True,
            tick_interval_seconds=60.0,
        )
        executor = AsyncMock(return_value=_make_world_event())

        # Animator returns 3 organic events
        animator = AsyncMock()
        organic_event = _make_world_event(actor_id="npc-1")
        animator.tick = AsyncMock(
            return_value=[
                {"_event": organic_event},
                {"_event": organic_event},
                {"_event": organic_event},
            ]
        )
        animator.check_scheduled_events = AsyncMock(return_value=[])
        animator.notify_event = AsyncMock(return_value=[])
        animator.has_scheduled_events = lambda: False

        # Agency returns 1 response envelope per organic event notification,
        # but not for subsequent pipeline-committed events (to avoid cascading).
        notify_call_count = {"n": 0}

        async def _notify_side_effect(event: object) -> list[ActionEnvelope]:
            notify_call_count["n"] += 1
            if notify_call_count["n"] <= 3:
                return [
                    _make_envelope(
                        actor_id="agent-1",
                        source=ActionSource.INTERNAL,
                        priority=EnvelopePriority.INTERNAL,
                    ),
                ]
            return []

        agency = AsyncMock()
        agency.check_scheduled_actions = AsyncMock(return_value=[])
        agency.notify = AsyncMock(side_effect=_notify_side_effect)
        agency.update_states_for_event = AsyncMock()
        agency.set_tool_executor = lambda ex: None
        agency.has_scheduled_actions = lambda: False

        runner = _make_runner(
            queue=q,
            pipeline_executor=executor,
            config=config,
            agency_engine=agency,
            animator=animator,
        )

        # Submit 1 initial envelope to kick off processing
        q.submit(_make_envelope())

        await runner.run()

        # 3 organic events tracked separately (not in total_events_processed).
        # total = 1 initial + 3 from notify responses = 4 pipeline events.
        assert runner._organic_events_generated == 3
        assert runner.total_events_processed == 4
