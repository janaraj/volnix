"""GameOrchestrator — event-driven game engine.

Replaces the round-based :class:`volnix.game.runner.GameRunner` with a
pure event-driven orchestrator that subscribes to committed game-tool
events on the bus, runs the scorer incrementally, checks win
conditions, re-activates the next player via
:class:`volnix.core.protocols.AgencyActivationProtocol`, and manages
termination (Path A natural win / Path B timeout settlement).

Lifecycle:

1. ``_on_initialize``: wire bus + state engine + agency (from
   ``_dependencies``). Validate agency against
   ``AgencyActivationProtocol``.
2. ``configure(definition, player_actor_ids, run_id)``: called
   explicitly by the composition root (Cycle B.9). Binds scorer +
   win-condition evaluator + player scores.
3. ``_on_start``: subscribes to bus topics (game tool events, budget
   exhausted, game timeout); schedules failsafe timers; publishes
   ``GameActiveStateChangedEvent(active=True)`` + ``GameKickstartEvent``;
   activates the first mover (serial mode) or all players (parallel
   mode).
4. ``_handle_game_event``: on each committed game tool event, scores
   it, checks win conditions, and either terminates (Path A) or
   re-activates the next player.
5. ``_handle_budget_exhausted``: tracks per-actor budget exhaustion;
   when all players are out, publishes ``GameTimeoutEvent(reason="all_budgets")``.
6. ``_handle_timeout``: Path B termination — settles open deals
   (BATNA for competitive; behavioral no-op), publishes
   ``GameTerminatedEvent``.
7. ``_on_stop``: cancels failsafe timers, drains in-flight activation
   tasks, unsubscribes, resolves the result Future if still pending.

This engine is the SINGLE orchestrator for all game lifecycle state.
It does NOT write entity state — the game service responder pack
(``volnix/packs/verified/game``) is the sole writer, which guarantees
atomicity via the pipeline commit step (MF1).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, ClassVar

from volnix.core.engine import BaseEngine
from volnix.core.events import Event, WorldEvent
from volnix.core.protocols import AgencyActivationProtocol
from volnix.core.types import ActorId, EventId, Timestamp
from volnix.engines.game.definition import (
    GameDefinition,
    GameResult,
    GameState,
    PlayerScore,
    WinResult,
)
from volnix.engines.game.events import (
    GameActiveStateChangedEvent,
    GameKickstartEvent,
    GameScoreUpdatedEvent,
    GameTerminatedEvent,
    GameTimeoutEvent,
)
from volnix.engines.game.scorers import (
    BehavioralScorer,
    CompetitiveScorer,
    GameScorer,
    ScorerContext,
)
from volnix.engines.game.win_conditions_v2 import EventDrivenWinConditionEvaluator

logger = logging.getLogger(__name__)


# Bus topics the orchestrator subscribes to for committed game tool events.
# These are the exact event_type strings the DAG stamps on committed events
# for game service actions.
GAME_TOOL_EVENT_TYPES: tuple[str, ...] = (
    "world.negotiate_propose",
    "world.negotiate_counter",
    "world.negotiate_accept",
    "world.negotiate_reject",
)


def _now_timestamp() -> Timestamp:
    """Build a Timestamp stamped at UTC now."""
    now = datetime.now(UTC)
    return Timestamp(world_time=now, wall_time=now, tick=0)


class GameOrchestrator(BaseEngine):
    """Event-driven game orchestrator. The Cycle B keystone.

    Inherits from :class:`BaseEngine` for lifecycle + bus integration
    but uses manual topic subscriptions in ``_on_start`` (rather than
    the ``subscriptions`` ClassVar) because each topic has its own
    dedicated handler method with a different signature.
    """

    engine_name: ClassVar[str] = "game"
    # No auto-subscriptions — we subscribe manually per-topic in _on_start
    # because different topics dispatch to different handlers.
    subscriptions: ClassVar[list[str]] = []
    dependencies: ClassVar[list[str]] = ["state", "budget"]

    def __init__(self) -> None:
        super().__init__()
        # Dependencies injected in _on_initialize from self._config / self._dependencies
        self._state: Any = None
        self._agency: AgencyActivationProtocol | None = None

        # Game config (set in configure)
        self._definition: GameDefinition | None = None
        self._player_ids: list[ActorId] = []
        self._run_id: str = ""
        self._scorer: GameScorer | None = None
        self._win_evaluator: EventDrivenWinConditionEvaluator | None = None

        # Runtime mutable state
        self._player_scores: dict[str, PlayerScore] = {}
        self._game_state: GameState = GameState()
        self._terminated: bool = False
        self._exhausted_players: set[str] = set()
        self._result_future: asyncio.Future[GameResult] | None = None

        # Failsafe timer tasks (cancelled on termination)
        self._wall_clock_task: asyncio.Task[None] | None = None
        self._stalemate_task: asyncio.Task[None] | None = None

        # Activation tasks (fire-and-forget asyncio.create_task; collected
        # for graceful shutdown)
        self._activation_tasks: set[asyncio.Task[Any]] = set()

    # ---------------------------------------------------------------
    # BaseEngine lifecycle hooks
    # ---------------------------------------------------------------

    async def _on_initialize(self) -> None:
        """Wire state + agency dependencies. Bus is injected by ``initialize``."""
        if self._bus is None:
            raise RuntimeError("GameOrchestrator requires a bus (injected by initialize)")
        self._state = self._dependencies.get("state")
        if self._state is None:
            raise RuntimeError("GameOrchestrator requires 'state' dependency")
        agency = self._dependencies.get("agency")
        if agency is None:
            # agency may be injected later by the composition root in B.9
            # (we don't fail hard here — configure() is the latest reasonable point)
            logger.debug(
                "GameOrchestrator: 'agency' dependency not set at _on_initialize; "
                "expected to be injected before configure()"
            )
        elif not isinstance(agency, AgencyActivationProtocol):
            raise RuntimeError(
                "GameOrchestrator: 'agency' dependency does not implement "
                "AgencyActivationProtocol (missing activate_for_event method)"
            )
        else:
            self._agency = agency
        logger.info("GameOrchestrator initialized")

    async def _on_start(self) -> None:
        """Subscribe to bus, start failsafes, kickstart first mover.

        Only runs if ``configure()`` was called first — otherwise this is
        a no-op (engine not in use for this run).
        """
        if self._definition is None:
            logger.info("GameOrchestrator._on_start: no definition, noop")
            return
        if self._agency is None:
            # Agency must be wired by now via self._dependencies["agency"]
            agency = self._dependencies.get("agency")
            if agency is None or not isinstance(agency, AgencyActivationProtocol):
                raise RuntimeError(
                    "GameOrchestrator._on_start: agency dependency missing. "
                    "Composition root must inject an AgencyActivationProtocol."
                )
            self._agency = agency

        # 1. Subscribe to game tool committed events (one subscription per
        # event_type string — bus fanout keys exactly on event_type).
        for event_type in GAME_TOOL_EVENT_TYPES:
            await self._bus.subscribe(event_type, self._handle_game_event)

        # 2. Subscribe to budget.exhausted and our own game.timeout events
        await self._bus.subscribe("budget.exhausted", self._handle_budget_exhausted)
        await self._bus.subscribe("game.timeout", self._handle_timeout)

        # 3. Mark game start time + result future
        self._game_state = GameState(started_at=datetime.now(UTC))
        self._result_future = asyncio.get_event_loop().create_future()

        # 4. Flip game_active = True (for GameActivePolicy)
        await self._publish_active_state(active=True)

        # 5. Schedule failsafe timers
        self._wall_clock_task = asyncio.create_task(
            self._wall_clock_watcher(),
            name="game_wall_clock_watcher",
        )
        self._stalemate_task = asyncio.create_task(
            self._stalemate_watcher(),
            name="game_stalemate_watcher",
        )
        self._refresh_stalemate_deadline()

        # 6. Publish kickstart event + activate first mover
        first_mover = self._resolve_first_mover()
        kickstart_event = GameKickstartEvent(
            event_id=EventId(f"evt-game-kickstart-{self._run_id}"),
            event_type="game.kickstart",
            timestamp=_now_timestamp(),
            run_id=self._run_id,
            first_mover=str(first_mover) if first_mover else "",
            num_players=len(self._player_ids),
        )
        await self._bus.publish(kickstart_event)
        logger.info(
            "GameOrchestrator started: run_id=%s players=%s scoring=%s flow=%s",
            self._run_id,
            [str(p) for p in self._player_ids],
            self._definition.scoring_mode,
            self._definition.flow.type,
        )

        # 7. Kickstart activation
        if self._definition.flow.activation_mode == "parallel":
            for pid in self._player_ids:
                self._launch_activation(pid, reason="game_kickstart", trigger_event=None)
        else:
            # serial mode: activate only the first mover; the orchestrator
            # activates the next player on each commit
            if first_mover is not None:
                self._launch_activation(first_mover, reason="game_kickstart", trigger_event=None)

    async def _on_stop(self) -> None:
        """Graceful shutdown: cancel timers, drain tasks, unsubscribe."""
        self._terminated = True
        self._cancel_failsafe_timers()
        # Cancel in-flight activation tasks
        for task in list(self._activation_tasks):
            if not task.done():
                task.cancel()
        if self._activation_tasks:
            await asyncio.gather(*self._activation_tasks, return_exceptions=True)
            self._activation_tasks.clear()
        # Resolve result future if still pending (so CLI doesn't hang)
        if self._result_future is not None and not self._result_future.done():
            self._result_future.set_result(
                GameResult(
                    reason="stopped",
                    winner=None,
                    total_events=self._game_state.event_counter,
                    wall_clock_seconds=self._elapsed_seconds(),
                    scoring_mode=(
                        self._definition.scoring_mode if self._definition else "behavioral"
                    ),
                )
            )
        logger.info("GameOrchestrator stopped")

    async def _handle_event(self, event: Event) -> None:
        """BaseEngine abstract method — unused.

        All routing happens via the per-topic subscriptions set up in
        ``_on_start``. This method is required by :class:`BaseEngine`
        but is a no-op because the orchestrator does not have a
        default ``subscriptions`` list.
        """
        return None

    # ---------------------------------------------------------------
    # Public configure + result API
    # ---------------------------------------------------------------

    async def configure(
        self,
        definition: GameDefinition,
        player_actor_ids: list[str | ActorId],
        run_id: str,
    ) -> None:
        """Bind game definition, scorer, win-condition evaluator, player scores.

        Called by the composition root (Cycle B.9) after initialize
        but before start. If the definition is disabled, configure is
        a no-op.
        """
        if not definition.enabled:
            logger.info("GameOrchestrator.configure: definition disabled, noop")
            return
        self._definition = definition
        self._player_ids = [ActorId(str(pid)) for pid in player_actor_ids]
        self._run_id = run_id
        self._player_scores = {str(pid): PlayerScore(actor_id=pid) for pid in self._player_ids}
        self._game_state = GameState()
        self._terminated = False
        self._exhausted_players = set()

        # Select scorer by scoring_mode (the ONE place this dispatch happens)
        if definition.scoring_mode == "competitive":
            self._scorer = CompetitiveScorer(bonus_per_event=definition.flow.bonus_per_event)
        else:
            self._scorer = BehavioralScorer()

        # Filter win conditions to mode; drops score_threshold in behavioral
        self._win_evaluator = EventDrivenWinConditionEvaluator(
            conditions=list(definition.win_conditions),
            scoring_mode=definition.scoring_mode,
        )
        logger.info(
            "GameOrchestrator configured: run_id=%s mode=%s scoring_mode=%s players=%d",
            run_id,
            definition.mode,
            definition.scoring_mode,
            len(self._player_ids),
        )

    async def await_result(self) -> GameResult:
        """Block until ``game_terminated`` is published. Used by CLI ``volnix run``."""
        if self._result_future is None:
            raise RuntimeError(
                "GameOrchestrator.await_result called before _on_start (no result future)"
            )
        return await self._result_future

    # ---------------------------------------------------------------
    # Bus subscription handlers
    # ---------------------------------------------------------------

    async def _handle_game_event(self, event: Event) -> None:
        """Process one committed game tool event.

        This is the per-event scoring + win-check + next-player
        re-activation hot path. Called once per committed
        ``world.negotiate_*`` event on the orchestrator's consumer
        task.
        """
        if self._terminated:
            return
        if not isinstance(event, WorldEvent):
            return
        if str(event.service_id) != "game":
            return
        if self._definition is None or self._scorer is None or self._win_evaluator is None:
            return

        # 1. Advance counters
        self._game_state.event_counter += 1
        self._refresh_stalemate_deadline()

        # 2. Score the event (scorer reads state but never writes — MF1)
        ctx = ScorerContext(
            event=event,
            event_number=self._game_state.event_counter,
            state_engine=self._state,
            player_scores=self._player_scores,
            definition=self._definition,
        )
        try:
            await self._scorer.score_event(ctx)
        except Exception:
            logger.exception("Scorer.score_event raised; skipping this event's scoring")

        # 3. Publish incremental score updates
        for pid, ps in self._player_scores.items():
            score_event = GameScoreUpdatedEvent(
                event_id=EventId(f"evt-score-{self._game_state.event_counter}-{pid}"),
                event_type="game.score_updated",
                timestamp=_now_timestamp(),
                actor_id=ActorId(pid),
                metric="total_score",
                value=ps.total_score,
            )
            await self._bus.publish(score_event)

        # 4. Check win conditions (Path A: natural win)
        try:
            win_result = await self._win_evaluator.check(
                scores=self._player_scores,
                game_state=self._game_state,
                state_engine=self._state,
                exhausted_players=self._exhausted_players,
            )
        except Exception:
            logger.exception("Win condition check raised; game continues")
            win_result = None

        if win_result is not None:
            await self._terminate_natural(win_result)
            return

        # 5. Determine next player and re-activate (Option D: direct call)
        next_player = self._next_player_for(event)
        if next_player is not None:
            state_summary = await self._build_state_summary()
            self._launch_activation(
                next_player,
                reason="game_event",
                trigger_event=event,
                state_summary=state_summary,
            )

    async def _handle_budget_exhausted(self, event: Event) -> None:
        """Track per-actor budget exhaustion; fire all_budgets timeout when all done."""
        if self._terminated:
            return
        actor_id_attr = getattr(event, "actor_id", None)
        if actor_id_attr is None:
            return
        actor_id = str(actor_id_attr)
        if actor_id not in self._player_scores:
            return
        # Only count world_actions exhaustion for game elimination. Other
        # budget dimensions (llm_spend_usd, api_calls, time) don't signal
        # "out of the game" by themselves.
        budget_type = getattr(event, "budget_type", "")
        if budget_type != "world_actions":
            return
        self._exhausted_players.add(actor_id)
        ps = self._player_scores[actor_id]
        ps.eliminated = True
        ps.eliminated_at_event = self._game_state.event_counter
        logger.info(
            "GameOrchestrator: player %s eliminated (world_actions exhausted)",
            actor_id,
        )
        if len(self._exhausted_players) >= len(self._player_scores):
            # All players out — publish timeout
            timeout_event = GameTimeoutEvent(
                event_id=EventId(f"evt-all-budgets-{self._run_id}"),
                event_type="game.timeout",
                timestamp=_now_timestamp(),
                reason="all_budgets",
                event_number=self._game_state.event_counter,
            )
            await self._bus.publish(timeout_event)

    async def _handle_timeout(self, event: Event) -> None:
        """Path B termination: settle open deals + publish game_terminated."""
        if self._terminated:
            return
        if self._definition is None or self._scorer is None:
            return
        reason = str(getattr(event, "reason", "unknown"))
        self._terminated = True
        self._game_state.terminated = True
        self._cancel_failsafe_timers()

        # Query open deals for settlement
        open_deals: list[dict[str, Any]] = []
        try:
            all_deals = await self._state.query_entities("negotiation_deal")
            open_deals = [
                d
                for d in all_deals
                if str(d.get("status", "")).lower() in {"open", "proposed", "countered"}
            ]
        except Exception:
            logger.exception("Failed to query negotiation_deal for settlement")

        try:
            await self._scorer.settle(
                open_deals=open_deals,
                state_engine=self._state,
                player_scores=self._player_scores,
                definition=self._definition,
            )
        except Exception:
            logger.exception("Scorer.settle raised; proceeding to termination")

        # Flip game_active = False + publish terminated
        await self._publish_active_state(active=False)
        win_result = WinResult(
            winner=None,
            reason=reason,
            final_standings=_serialize_standings(self._player_scores),
            behavior_scores={
                pid: dict(s.behavior_metrics) for pid, s in self._player_scores.items()
            },
        )
        await self._publish_terminated(win_result, reason=reason)

    # ---------------------------------------------------------------
    # Path A termination (natural win — no settlement)
    # ---------------------------------------------------------------

    async def _terminate_natural(self, win_result: WinResult) -> None:
        """Path A: natural win. No BATNA, no settlement."""
        if self._terminated:
            return
        self._terminated = True
        self._game_state.terminated = True
        self._cancel_failsafe_timers()
        await self._publish_active_state(active=False)
        await self._publish_terminated(win_result, reason=win_result.reason)

    async def _publish_terminated(self, win_result: WinResult, reason: str) -> None:
        """Publish ``GameTerminatedEvent`` and resolve the result future."""
        if self._definition is None:
            return
        wall_clock_s = self._elapsed_seconds()
        terminated_event = GameTerminatedEvent(
            event_id=EventId(f"evt-game-terminated-{self._run_id}"),
            event_type="game.terminated",
            timestamp=_now_timestamp(),
            winner=win_result.winner,
            reason=reason,
            final_standings=list(win_result.final_standings),
            behavior_scores=dict(win_result.behavior_scores),
            total_events=self._game_state.event_counter,
            wall_clock_seconds=wall_clock_s,
            scoring_mode=self._definition.scoring_mode,
        )
        await self._bus.publish(terminated_event)
        result = GameResult(
            reason=reason,
            winner=win_result.winner,
            final_standings=list(win_result.final_standings),
            behavior_scores=dict(win_result.behavior_scores),
            total_events=self._game_state.event_counter,
            wall_clock_seconds=wall_clock_s,
            scoring_mode=self._definition.scoring_mode,
        )
        if self._result_future is not None and not self._result_future.done():
            self._result_future.set_result(result)
        logger.info(
            "GameOrchestrator: terminated (reason=%s winner=%s total_events=%d)",
            reason,
            win_result.winner,
            self._game_state.event_counter,
        )

    async def _publish_active_state(self, active: bool) -> None:
        """Flip the game_active flag via bus (read by GameActivePolicy)."""
        state_event = GameActiveStateChangedEvent(
            event_id=EventId(
                f"evt-game-active-{active}-{self._run_id}-{self._game_state.event_counter}"
            ),
            event_type="game.active_state_changed",
            timestamp=_now_timestamp(),
            active=active,
            run_id=self._run_id,
        )
        await self._bus.publish(state_event)

    # ---------------------------------------------------------------
    # Failsafe timer tasks
    # ---------------------------------------------------------------

    async def _wall_clock_watcher(self) -> None:
        """Sleep then publish ``GameTimeoutEvent(reason="wall_clock")``."""
        if self._definition is None:
            return
        try:
            await asyncio.sleep(self._definition.flow.max_wall_clock_seconds)
        except asyncio.CancelledError:
            return
        if self._terminated:
            return
        timeout_event = GameTimeoutEvent(
            event_id=EventId(f"evt-wall-clock-{self._run_id}"),
            event_type="game.timeout",
            timestamp=_now_timestamp(),
            reason="wall_clock",
            event_number=self._game_state.event_counter,
        )
        await self._bus.publish(timeout_event)

    async def _stalemate_watcher(self) -> None:
        """Poll the stalemate deadline; fire timeout if reached without reset."""
        if self._definition is None:
            return
        try:
            while not self._terminated:
                now = asyncio.get_event_loop().time()
                sleep_for = self._game_state.stalemate_deadline_tick - now
                if sleep_for <= 0:
                    break
                await asyncio.sleep(sleep_for)
        except asyncio.CancelledError:
            return
        if self._terminated:
            return
        timeout_event = GameTimeoutEvent(
            event_id=EventId(f"evt-stalemate-{self._run_id}"),
            event_type="game.timeout",
            timestamp=_now_timestamp(),
            reason="stalemate",
            event_number=self._game_state.event_counter,
        )
        await self._bus.publish(timeout_event)

    def _refresh_stalemate_deadline(self) -> None:
        """Push the stalemate deadline forward. Called on each game event."""
        if self._definition is None:
            return
        loop = asyncio.get_event_loop()
        self._game_state.stalemate_deadline_tick = (
            loop.time() + self._definition.flow.stalemate_timeout_seconds
        )

    def _cancel_failsafe_timers(self) -> None:
        """Cancel all failsafe tasks. Idempotent."""
        for task in (self._wall_clock_task, self._stalemate_task):
            if task is not None and not task.done():
                task.cancel()
        self._wall_clock_task = None
        self._stalemate_task = None

    # ---------------------------------------------------------------
    # Activation routing (Option D: direct call to agency)
    # ---------------------------------------------------------------

    def _resolve_first_mover(self) -> ActorId | None:
        """Resolve ``flow.first_mover`` (role or actor_id) to an ActorId.

        If ``first_mover`` is a role name (e.g. ``"buyer"``), matches
        the first player whose actor_id starts with ``"{role}-"``.
        Falls back to the first player in the list.
        """
        if self._definition is None or not self._player_ids:
            return None
        first_mover = self._definition.flow.first_mover or ""
        if first_mover:
            for pid in self._player_ids:
                pid_str = str(pid)
                if pid_str == first_mover or pid_str.startswith(first_mover + "-"):
                    return pid
        return self._player_ids[0]

    def _next_player_for(self, event: WorldEvent) -> ActorId | None:
        """Given a just-committed event, return the actor to activate next.

        Serial mode: the OTHER player (not the mover). None if there's
        no other player.

        Parallel mode: ``None`` (all players active concurrently; no
        re-activation needed — each acts on their own LLM loop).
        """
        if self._definition is None:
            return None
        if self._definition.flow.activation_mode == "parallel":
            return None
        mover = str(event.actor_id)
        for pid in self._player_ids:
            if (
                str(pid) != mover
                and not self._player_scores.get(str(pid), PlayerScore(actor_id=pid)).eliminated
            ):
                return pid
        return None

    def _launch_activation(
        self,
        actor_id: ActorId,
        reason: str,
        trigger_event: WorldEvent | None,
        state_summary: str | None = None,
    ) -> None:
        """Launch an activation as a fire-and-forget asyncio task.

        The task is added to ``self._activation_tasks`` so it can be
        cancelled on shutdown. Errors are logged via the done
        callback.
        """
        if self._agency is None:
            logger.warning("GameOrchestrator: no agency, cannot activate %s", actor_id)
            return
        task = asyncio.create_task(
            self._agency.activate_for_event(
                actor_id=actor_id,
                reason=reason,
                trigger_event=trigger_event,
                state_summary=state_summary,
            ),
            name=f"game_activation_{actor_id}_{reason}",
        )
        self._activation_tasks.add(task)
        task.add_done_callback(self._on_activation_done)

    def _on_activation_done(self, task: asyncio.Task[Any]) -> None:
        """Cleanup activation task; log errors."""
        self._activation_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.warning(
                "GameOrchestrator: activation task raised: %s",
                exc,
            )

    # ---------------------------------------------------------------
    # State summary helper (MF6 — injected on re-activation)
    # ---------------------------------------------------------------

    async def _build_state_summary(self) -> str:
        """Compact text snapshot of current game state.

        Rendered at the top of the agent's rolling conversation on
        re-activation so the LLM sees ground truth without replaying
        full history. Format is compact and human-readable.
        """
        if self._state is None:
            return ""
        parts: list[str] = [f"Game state at event #{self._game_state.event_counter}:"]
        try:
            deals = await self._state.query_entities("negotiation_deal")
            for deal in deals:
                status = deal.get("status", "?")
                terms = deal.get("terms") or {}
                last_by = deal.get("last_proposed_by") or "?"
                parts.append(
                    f"- deal {deal.get('id', '?')}: status={status}, "
                    f"last_proposed_by={last_by}, terms={terms}"
                )
        except Exception:
            logger.exception("State summary query failed")
        return "\n".join(parts)

    # ---------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------

    def _elapsed_seconds(self) -> float:
        """Wall-clock seconds since game start. Zero if not started."""
        if self._game_state.started_at is None:
            return 0.0
        return (datetime.now(UTC) - self._game_state.started_at).total_seconds()


def _serialize_standings(scores: dict[str, PlayerScore]) -> list[dict[str, Any]]:
    """Build a descending standings list from player scores."""
    return sorted(
        [
            {
                "actor_id": pid,
                "total_score": s.total_score,
                "metrics": dict(s.metrics),
                "behavior_metrics": dict(s.behavior_metrics),
                "eliminated": s.eliminated,
            }
            for pid, s in scores.items()
        ],
        key=lambda row: row["total_score"],
        reverse=True,
    )
