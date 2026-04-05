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

from volnix.core.envelope import ActionEnvelope
from volnix.core.types import ActionSource, ActorId, EnvelopePriority, ServiceId
from volnix.simulation.config import SimulationRunnerConfig
from volnix.simulation.event_queue import EventQueue

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
    IDLE_STOP = "idle_stop"
    DELIVERABLE_PRODUCED = "deliverable_produced"
    TICK_LIMIT = "tick_limit"


class SimulationType(StrEnum):
    """Classification of simulation based on actor composition."""

    INTERNAL_ONLY = "internal_only"  # all actors are internal
    EXTERNAL_DRIVEN = "external_driven"  # any external actor present
    MIXED = "mixed"  # both internal and external actors


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
        actor_specs: list[dict[str, Any]] | None = None,
    ) -> None:
        self._queue = event_queue
        self._execute_pipeline = pipeline_executor
        self._agency = agency_engine
        # Wire pipeline executor into agency for inline tool execution
        if self._agency and hasattr(self._agency, "set_tool_executor"):
            self._agency.set_tool_executor(self._execute_pipeline)
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

        # Simulation type detection
        self._simulation_type = self._detect_simulation_type(actor_specs or [])

        # Internal-only world tracking
        self._consecutive_idle_ticks: int = 0
        self._deliverable_produced: bool = False
        self._deliverable_content: dict | None = None
        self._current_tick: int = 0
        # Animator tick gating: fire at most once per animator_tick_interval ticks.
        # Initial value ensures the first tick fires immediately.
        self._last_animator_tick: int = -(self._config.animator_tick_interval)
        self._organic_events_generated: int = 0  # Organic events (separate from agent budget)

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

    @property
    def simulation_type(self) -> SimulationType:
        """Classification of this simulation based on actor composition."""
        return self._simulation_type

    @property
    def deliverable_produced(self) -> bool:
        """Whether a deliverable has been produced."""
        return self._deliverable_produced

    @property
    def deliverable_content(self) -> dict | None:
        """The deliverable JSON content, if produced."""
        return self._deliverable_content

    @property
    def consecutive_idle_ticks(self) -> int:
        """Number of consecutive ticks where all actors did nothing."""
        return self._consecutive_idle_ticks

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

    def mark_deliverable_produced(self) -> None:
        """Mark that a deliverable has been produced (e.g. by the lead actor)."""
        self._deliverable_produced = True

    @staticmethod
    def _detect_simulation_type(
        actor_specs: list[dict[str, Any]],
    ) -> SimulationType:
        """Detect simulation type from actor specs.

        - internal_only: all actors are internal
        - external_driven: at least one external actor, no internal
        - mixed: both internal and external actors
        """
        has_internal = False
        has_external = False
        for spec in actor_specs:
            actor_type = spec.get("type", "external")
            if actor_type == "internal":
                has_internal = True
            else:
                has_external = True

        if has_internal and has_external:
            return SimulationType.MIXED
        if has_internal:
            return SimulationType.INTERNAL_ONLY
        return SimulationType.EXTERNAL_DRIVEN

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

        logger.info(
            "SimulationRunner starting: type=%s, mission=%s, queue_pending=%s",
            self._simulation_type, bool(self._mission), self._queue.has_pending(),
        )

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

            # Step 2: Animator scheduled events + organic tick
            if self._animator is not None:
                animator_envelopes = await self._animator.check_scheduled_events(
                    self._queue.current_time
                )
                for env in animator_envelopes or []:
                    self._queue.submit(env)

                # Organic events (Layer 2): LLM-generated contextual world events.
                # tick() fires at most once per animator_tick_interval ticks.
                # Prevents feedback loops where each organic event advances
                # time and re-triggers tick().
                from datetime import datetime, timezone
                current_tick = int(
                    self._queue.current_time / self._config.tick_interval_seconds
                )
                if current_tick >= self._last_animator_tick + self._config.animator_tick_interval:
                    self._last_animator_tick = current_tick
                    tick_time = datetime.fromtimestamp(
                        self._queue.current_time, tz=timezone.utc
                    ) if self._queue.current_time > 0 else datetime.now(timezone.utc)
                    tick_results = await self._animator.tick(tick_time)
                else:
                    tick_results = []
                if tick_results:
                    self._organic_events_generated += len(tick_results)
                    logger.info(
                        "[RUNNER] animator tick generated %d organic events",
                        len(tick_results),
                    )
                    # Notify agency of committed events so agents can react
                    if self._agency is not None:
                        for result in tick_results:
                            committed = result.get("_event") if isinstance(result, dict) else None
                            if committed:
                                response_envs = await self._agency.notify(committed)
                                for env in (response_envs or []):
                                    self._queue.submit(env)

            # Step 3: AgencyEngine scheduled actions
            if self._agency is not None:
                if hasattr(self._agency, "set_simulation_progress"):
                    self._agency.set_simulation_progress(
                        self._total_events_processed,
                        self._config.max_total_events,
                    )
                agency_envelopes = await self._agency.check_scheduled_actions(
                    self._queue.current_time
                )
                for env in agency_envelopes or []:
                    if env.action_type == "produce_deliverable":
                        # Deliverable: have the agency engine activate the
                        # lead actor to synthesize the collaboration via LLM.
                        # Processed immediately — meta-actions bypass the queue
                        # because they skip the governance pipeline.
                        deliverable_json = await self._agency.generate_deliverable(
                            env.actor_id, env.payload,
                        )
                        self._deliverable_content = deliverable_json
                        self._deliverable_produced = True
                        self._total_events_processed += 1
                        if self._simulation_type == SimulationType.INTERNAL_ONLY:
                            self._current_tick += 1
                            self._queue.current_time = (
                                float(self._current_tick)
                                * self._config.tick_interval_seconds
                            )
                        logger.info(
                            "[RUNNER] Deliverable produced by %s: %d bytes",
                            env.actor_id, len(str(deliverable_json)),
                        )
                    else:
                        self._queue.submit(env)

            # Step 4: Process next envelope
            envelope = self._queue.pop_next()
            if envelope is None:
                # Internal-only sims: fast-forward time to the next scheduled
                # action so it can fire.  Without this, time never advances
                # (it only advances on committed events) and scheduled work
                # that gates on a future tick is never reached.
                if self._simulation_type == SimulationType.INTERNAL_ONLY:
                    next_time = self._get_next_scheduled_time()
                    if next_time is not None and next_time > self._queue.current_time:
                        target_tick = int(next_time / self._config.tick_interval_seconds)
                        logger.info(
                            "[RUNNER] fast-forward: tick %d -> %d (time %.1f -> %.1f)",
                            self._current_tick, target_tick,
                            self._queue.current_time, next_time,
                        )
                        self._current_tick = target_tick
                        self._queue.current_time = next_time
                        continue  # next iteration fires the scheduled action
                await asyncio.sleep(0.01)
                continue

            logger.info(
                "[RUNNER] dequeued: actor=%s action=%s service=%s source=%s",
                envelope.actor_id, envelope.action_type,
                envelope.target_service, envelope.source,
            )

            # Runaway protection
            if not self._check_runaway_limits(envelope):
                logger.warning(
                    "[RUNNER] runaway protection: dropping %s from %s",
                    envelope.envelope_id, envelope.actor_id,
                )
                continue

            # Meta-action: produce_deliverable skips governance pipeline
            if envelope.action_type == "produce_deliverable":
                self._deliverable_content = envelope.payload
                self._deliverable_produced = True
                self._total_events_processed += 1
                if self._simulation_type == SimulationType.INTERNAL_ONLY:
                    self._current_tick += 1
                    self._queue.current_time = (
                        float(self._current_tick) * self._config.tick_interval_seconds
                    )
                logger.info(
                    "[RUNNER] Deliverable produced by %s: %d bytes",
                    envelope.actor_id,
                    len(str(envelope.payload)),
                )
                continue

            # Execute through pipeline
            committed_event = await self._execute_pipeline(envelope)
            logger.info(
                "[RUNNER] pipeline result: type=%s",
                type(committed_event).__name__,
            )
            if committed_event is None:
                continue

            self._total_events_processed += 1
            logger.info(
                "[RUNNER] event #%d processed, queue_pending=%s",
                self._total_events_processed, self._queue.has_pending(),
            )

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
                from volnix.actors.replay import ReplayEntry

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

            # Step 9: Track idle ticks for internal-only worlds
            self._track_idle_ticks(envelope)

            # Step 10: Advance tick for internal-only worlds.
            # Each committed event = 1 tick. This drives:
            # - check_scheduled_actions() firing at the right time
            # - max_ticks end condition
            # - Runaway window sliding forward
            if self._simulation_type == SimulationType.INTERNAL_ONLY:
                self._current_tick += 1
                self._queue.current_time = (
                    float(self._current_tick) * self._config.tick_interval_seconds
                )

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

        # 7. Loop breaker (skip for internal-only worlds where no external is expected)
        if (
            self._simulation_type != SimulationType.INTERNAL_ONLY
            and self._events_since_external >= self._config.loop_breaker_threshold
        ):
            return StopReason.LOOP_BREAKER

        # 8-10. Internal-only world end conditions
        if self._simulation_type == SimulationType.INTERNAL_ONLY:
            # 8. Deliverable produced
            if self._deliverable_produced:
                return StopReason.DELIVERABLE_PRODUCED

            # 9. Idle stop (all actors did nothing for N consecutive ticks)
            if self._consecutive_idle_ticks >= self._config.idle_stop_ticks:
                return StopReason.IDLE_STOP

            # 10. Hard tick limit
            if self._current_tick >= self._config.max_ticks:
                return StopReason.TICK_LIMIT

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

    def _track_idle_ticks(self, envelope: ActionEnvelope) -> None:
        """Track consecutive idle actions for internal-only world end conditions.

        Each committed event is one tick. If the action is a no-op (do_nothing,
        noop, idle, wait, pass), the consecutive idle counter increments.
        Any substantive action resets it to zero.
        """
        if self._simulation_type != SimulationType.INTERNAL_ONLY:
            return

        idle_actions = {"do_nothing", "noop", "idle", "wait", "pass"}
        if envelope.action_type in idle_actions:
            self._consecutive_idle_ticks += 1
        else:
            self._consecutive_idle_ticks = 0

    def _get_next_scheduled_time(self) -> float | None:
        """Earliest scheduled time across agency and animator, or None."""
        candidates: list[float] = []
        if self._agency is not None:
            t = getattr(self._agency, "next_scheduled_time", lambda: None)()
            if t is not None:
                candidates.append(t)
        if self._animator is not None:
            t = getattr(self._animator, "next_scheduled_time", lambda: None)()
            if t is not None:
                candidates.append(t)
        return min(candidates) if candidates else None
