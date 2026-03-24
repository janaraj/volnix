"""SimulationRunner -- drives the main simulation loop.

Coordinates EventQueue processing, Animator scheduled checks,
AgencyEngine scheduled checks, external agent input, and
simulation end conditions.
"""

from __future__ import annotations

import asyncio
import logging
from enum import StrEnum
from typing import Any

from terrarium.core.envelope import ActionEnvelope
from terrarium.core.types import ActionSource, ActorId
from terrarium.simulation.config import SimulationRunnerConfig
from terrarium.simulation.event_queue import EventQueue

logger = logging.getLogger(__name__)


class SimulationStatus(StrEnum):
    """Simulation lifecycle status."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    STOPPED = "stopped"


class StopReason(StrEnum):
    """Why the simulation stopped."""

    ALL_AGENTS_DISCONNECTED = "all_agents_disconnected"
    ALL_BUDGETS_EXHAUSTED = "all_budgets_exhausted"
    MISSION_COMPLETED = "mission_completed"
    MANUAL_STOP = "manual_stop"
    MAX_TIME_REACHED = "max_time_reached"
    QUEUE_EMPTY = "queue_empty"
    MAX_EVENTS_REACHED = "max_events_reached"
    LOOP_BREAKER = "loop_breaker"


class SimulationRunner:
    """Drives the simulation loop.

    Dependencies (injected, not imported):
    - event_queue: EventQueue
    - pipeline_executor: callable(ActionEnvelope) -> WorldEvent | None
    - agency_engine: AgencyEngineProtocol (notify, check_scheduled)
    - animator: AnimatorProtocol (notify, check_scheduled_events)
    - config: SimulationRunnerConfig
    """

    def __init__(
        self,
        event_queue: EventQueue,
        pipeline_executor: Any,  # async callable(ActionEnvelope) -> WorldEvent | None
        agency_engine: Any | None = None,  # AgencyEngineProtocol
        animator: Any | None = None,  # AnimatorProtocol
        budget_checker: Any | None = None,  # async callable() -> bool (all exhausted?)
        config: SimulationRunnerConfig | None = None,
        ledger: Any | None = None,
        replay_log: Any | None = None,
    ) -> None:
        self._queue = event_queue
        self._execute_pipeline = pipeline_executor
        self._agency = agency_engine
        self._animator = animator
        self._budget_checker = budget_checker
        self._config = config or SimulationRunnerConfig()
        self._ledger = ledger
        self._replay_log = replay_log

        self._status = SimulationStatus.IDLE
        self._stop_reason: StopReason | None = None
        self._total_events_processed: int = 0
        self._events_since_external: int = 0
        self._connected_agents: set[ActorId] = set()
        self._had_external_agents: bool = False
        self._mission: str | None = None
        self._mission_completed: bool = False

        # Runaway protection tracking
        self._actor_action_counts: dict[str, list[float]] = {}  # actor_id -> [logical_times]
        self._env_reaction_times: list[float] = []

    @property
    def status(self) -> SimulationStatus:
        """Current simulation status."""
        return self._status

    @property
    def stop_reason(self) -> StopReason | None:
        """Reason the simulation stopped, or None if still running."""
        return self._stop_reason

    @property
    def total_events_processed(self) -> int:
        """Total number of events that have been processed."""
        return self._total_events_processed

    def set_mission(self, mission: str) -> None:
        """Set the mission text for mission-complete detection."""
        self._mission = mission

    def connect_agent(self, actor_id: ActorId) -> None:
        """Register an external agent connection."""
        self._connected_agents.add(actor_id)
        self._had_external_agents = True

    def disconnect_agent(self, actor_id: ActorId) -> None:
        """Unregister an external agent connection."""
        self._connected_agents.discard(actor_id)

    def mark_mission_completed(self) -> None:
        """Mark the mission as completed (external signal)."""
        self._mission_completed = True

    async def stop(self) -> None:
        """Manual stop."""
        self._stop_reason = StopReason.MANUAL_STOP
        self._status = SimulationStatus.STOPPED

    async def run(self) -> StopReason:
        """Run the main simulation loop until an end condition is met.

        Loop:
        1. Check end conditions
        2. Animator checks for due environment events -> submit envelopes
        3. AgencyEngine checks for due scheduled actor actions -> submit envelopes
        4. Dequeue next envelope -> pipeline -> commit
        5. Notify AgencyEngine and Animator of committed event
        6. Update actor states
        7. Record to ReplayLog
        8. Repeat
        """
        self._status = SimulationStatus.RUNNING
        self._stop_reason = None

        while self._status == SimulationStatus.RUNNING:
            # Step 0: Async budget exhaustion check
            if self._budget_checker is not None:
                try:
                    all_exhausted = await self._budget_checker()
                    if all_exhausted:
                        self._stop_reason = StopReason.ALL_BUDGETS_EXHAUSTED
                        self._status = SimulationStatus.COMPLETED
                        break
                except Exception:
                    pass  # Budget check failure is non-fatal

            # Step 1: Check end conditions
            reason = self._check_end_conditions()
            if reason is not None:
                self._stop_reason = reason
                self._status = SimulationStatus.COMPLETED
                break

            # Step 2: Animator scheduled events
            if self._animator is not None:
                animator_envelopes = await self._animator.check_scheduled_events(
                    self._queue.current_time
                )
                for env in animator_envelopes or []:
                    self._queue.submit(env)

            # Step 3: AgencyEngine scheduled actions
            if self._agency is not None:
                agency_envelopes = await self._agency.check_scheduled_actions(
                    self._queue.current_time
                )
                for env in agency_envelopes or []:
                    self._queue.submit(env)

            # Step 4: Process next envelope
            envelope = self._queue.pop_next()
            if envelope is None:
                # Queue is empty -- yield control briefly, then re-check
                await asyncio.sleep(0.01)
                continue

            # Runaway protection
            if not self._check_runaway_limits(envelope):
                logger.warning(
                    "Runaway protection: dropping envelope %s from %s",
                    envelope.envelope_id,
                    envelope.actor_id,
                )
                continue

            # Execute through pipeline
            committed_event = await self._execute_pipeline(envelope)
            if committed_event is None:
                continue  # Pipeline rejected (short-circuited)

            self._total_events_processed += 1

            # Track external vs internal for loop breaker
            if envelope.source == ActionSource.EXTERNAL:
                self._events_since_external = 0
            else:
                self._events_since_external += 1

            # Step 5: Notify AgencyEngine
            if self._agency is not None:
                response_envelopes = await self._agency.notify(committed_event)
                count = 0
                for env in response_envelopes or []:
                    if count >= self._config.max_envelopes_per_event:
                        break
                    self._queue.submit(env)
                    count += 1

            # Step 6: Notify Animator
            if self._animator is not None:
                env_envelopes = await self._animator.notify_event(committed_event)
                count = 0
                for env in env_envelopes or []:
                    if count >= self._config.max_envelopes_per_event:
                        break
                    self._queue.submit(env)
                    count += 1

            # Step 7g: Actor states updated (deterministic, no LLM)
            if self._agency is not None and committed_event is not None:
                try:
                    await self._agency.update_states_for_event(committed_event)
                except Exception as exc:
                    logger.warning("Actor state update failed: %s", exc)

            # Step 8h: ReplayLog records
            if self._replay_log is not None and committed_event is not None:
                from terrarium.actors.replay import ReplayEntry

                entry = ReplayEntry(
                    logical_time=envelope.logical_time,
                    envelope_id=str(envelope.envelope_id),
                    actor_id=str(envelope.actor_id),
                    activation_reason=envelope.metadata.get(
                        "activation_reason", "external"
                    ),
                    activation_tier=envelope.metadata.get("activation_tier", 0),
                    pipeline_result_event_id=(
                        str(committed_event.event_id) if committed_event else None
                    ),
                )
                await self._replay_log.record(entry)

        return self._stop_reason  # type: ignore[return-value]

    def _check_end_conditions(self) -> StopReason | None:
        """Check all simulation end conditions plus safety limits."""
        # 1. Manual stop already requested
        if self._status == SimulationStatus.STOPPED:
            return StopReason.MANUAL_STOP

        # 2. Max total events
        if self._total_events_processed >= self._config.max_total_events:
            return StopReason.MAX_EVENTS_REACHED

        # 3. Max logical time
        if self._queue.current_time >= self._config.max_logical_time:
            return StopReason.MAX_TIME_REACHED

        # 4. Mission completed
        if self._mission_completed:
            return StopReason.MISSION_COMPLETED

        # 5. Queue empty and no scheduled future events
        if self._config.stop_on_empty_queue and not self._queue.has_pending():
            has_scheduled = False
            if self._agency is not None:
                has_scheduled = (
                    has_scheduled or getattr(self._agency, "has_scheduled_actions", lambda: False)()
                )
            if self._animator is not None:
                has_scheduled = (
                    has_scheduled
                    or getattr(self._animator, "has_scheduled_events", lambda: False)()
                )
            if not has_scheduled:
                return StopReason.QUEUE_EMPTY

        # 6. All external agents disconnected
        if (
            self._had_external_agents
            and not self._connected_agents
            and not self._queue.has_pending()
        ):
            return StopReason.ALL_AGENTS_DISCONNECTED

        # 7. Loop breaker
        if self._events_since_external >= self._config.loop_breaker_threshold:
            return StopReason.LOOP_BREAKER

        return None

    def _check_runaway_limits(self, envelope: ActionEnvelope) -> bool:
        """Return True if envelope passes runaway limits, False to drop it."""
        current_time = self._queue.current_time
        window = self._config.tick_interval_seconds

        actor_key = str(envelope.actor_id)
        if envelope.source == ActionSource.INTERNAL:
            times = self._actor_action_counts.setdefault(actor_key, [])
            times = [t for t in times if current_time - t < window]
            times.append(current_time)
            self._actor_action_counts[actor_key] = times
            if len(times) > self._config.max_actions_per_actor_per_window:
                return False

        if envelope.source == ActionSource.ENVIRONMENT:
            self._env_reaction_times = [
                t for t in self._env_reaction_times if current_time - t < window
            ]
            self._env_reaction_times.append(current_time)
            if len(self._env_reaction_times) > self._config.max_environment_reactions_per_window:
                return False

        return True
