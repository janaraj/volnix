"""GameOrchestrator — event-driven game engine.

A pure event-driven orchestrator that subscribes to committed game-tool
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
import uuid
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
    GameEngineErrorEvent,
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
from volnix.engines.game.win_conditions import WinConditionEvaluator

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


def _unique_suffix() -> str:
    """Short random suffix for collision-proof event IDs.

    Several orchestrator event IDs were previously deterministic
    (``evt-score-{counter}-{pid}``, ``evt-game-terminated-{run_id}``, etc).
    Any re-entry, replay, or rapid sequence of failsafes produced
    colliding IDs which the bus rejects. A 12-hex suffix gives us
    collision resistance without noisy IDs.
    """
    return uuid.uuid4().hex[:12]


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
        self._role_to_actor_id: dict[str, ActorId] = {}  # built in configure()
        self._run_id: str = ""
        self._scorer: GameScorer | None = None
        self._win_evaluator: WinConditionEvaluator | None = None

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

        # Bus subscription tokens (topic, callback) tuples registered in
        # _on_start; used by _on_stop to cleanly unsubscribe so re-start
        # within the same process doesn't double-register handlers.
        self._subscription_tokens: list[tuple[str, Any]] = []

    # ---------------------------------------------------------------
    # BaseEngine lifecycle hooks
    # ---------------------------------------------------------------

    async def _on_initialize(self) -> None:
        """Validate the bus and opportunistically resolve dependencies.

        When called through the standard ``wire_engines`` flow,
        ``_dependencies`` is empty at this point (it's populated by
        :func:`volnix.registry.wiring.inject_dependencies` AFTER
        ``_on_initialize`` returns). The dependency reads are therefore
        best-effort: they populate the cached ``_state`` and ``_agency``
        attributes if ``_dependencies`` is already set (as in tests that
        bypass wiring) and defer to ``_on_start`` otherwise.

        ``_on_start`` always re-resolves, so the two code paths end up
        in the same place.
        """
        if self._bus is None:
            raise RuntimeError("GameOrchestrator requires a bus (injected by initialize)")
        # Opportunistic resolve (safe to call with empty _dependencies)
        if self._dependencies.get("state") is not None:
            self._resolve_state_dependency()
        if self._dependencies.get("agency") is not None:
            self._resolve_agency_dependency()
        logger.info("GameOrchestrator initialized")

    def _resolve_state_dependency(self) -> None:
        """Read + validate the ``state`` dependency from ``_dependencies``.

        Called from ``_on_start`` (the earliest lifecycle point at which
        ``_dependencies`` is guaranteed populated) and from tests that
        bypass the wiring path and inject ``_dependencies`` directly.
        """
        self._state = self._dependencies.get("state")
        if self._state is None:
            raise RuntimeError("GameOrchestrator requires 'state' dependency")

    def _resolve_agency_dependency(self) -> None:
        """Read + validate the ``agency`` dependency from ``_dependencies``.

        Optional during wiring: composition root injects the agency in
        :meth:`app._inject_cross_engine_deps` AFTER ``wire_engines``
        runs, so agency may be absent during the initial ``_on_start``
        noop path (when no game is configured yet). The second
        ``_on_start`` call (from ``app.configure_game``) must succeed;
        at that point agency is guaranteed wired.
        """
        agency = self._dependencies.get("agency")
        if agency is None:
            logger.debug(
                "GameOrchestrator: 'agency' dependency not set yet; "
                "expected to be injected before configure()"
            )
            return
        if not isinstance(agency, AgencyActivationProtocol):
            raise RuntimeError(
                "GameOrchestrator: 'agency' dependency does not implement "
                "AgencyActivationProtocol (missing activate_for_event method)"
            )
        self._agency = agency

    async def _on_start(self) -> None:
        """Subscribe to bus, start failsafes, kickstart first mover.

        Only runs if ``configure()`` was called first — otherwise this is
        a no-op (engine not in use for this run).

        Called twice in the normal lifecycle:
        1. Once by ``wire_engines`` (``_definition is None`` → early noop)
        2. Once by :meth:`app._configure_event_driven_game` after
           ``configure()`` sets the definition; this is when the real
           subscribe + kickstart work happens.

        Dependencies are resolved here (not in ``_on_initialize``)
        because ``wire_engines`` populates ``_dependencies`` AFTER
        ``_on_initialize`` runs.
        """
        # Resolve deps on every _on_start call — cheap and idempotent
        if self._state is None:
            self._resolve_state_dependency()

        if self._definition is None:
            logger.info("GameOrchestrator._on_start: no definition, noop")
            return

        # Agency is required when a game is actually configured.
        self._resolve_agency_dependency()
        if self._agency is None:
            raise RuntimeError(
                "GameOrchestrator._on_start: agency dependency missing. "
                "Composition root must inject an AgencyActivationProtocol "
                "before configure()."
            )

        # 1. Subscribe to game tool committed events (one subscription per
        # event_type string — bus fanout keys exactly on event_type).
        # Track every subscription so _on_stop can unsubscribe cleanly and
        # restart-in-same-process doesn't accumulate duplicate handlers.
        self._subscription_tokens = []
        for event_type in GAME_TOOL_EVENT_TYPES:
            await self._bus.subscribe(event_type, self._handle_game_event)
            self._subscription_tokens.append((event_type, self._handle_game_event))

        # 2. Subscribe to budget.exhausted and our own game.timeout events
        await self._bus.subscribe("budget.exhausted", self._handle_budget_exhausted)
        self._subscription_tokens.append(("budget.exhausted", self._handle_budget_exhausted))
        await self._bus.subscribe("game.timeout", self._handle_timeout)
        self._subscription_tokens.append(("game.timeout", self._handle_timeout))

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
            event_id=EventId(f"evt-game-kickstart-{self._run_id}-{_unique_suffix()}"),
            event_type="game.kickstart",
            timestamp=_now_timestamp(),
            run_id=self._run_id,
            first_mover=str(first_mover) if first_mover else "",
            num_players=len(self._player_ids),
        )
        await self._bus.publish(kickstart_event)
        await self._record_lifecycle_entry(
            "started",
            {
                "run_id": self._run_id,
                "num_players": len(self._player_ids),
                "scoring_mode": self._definition.scoring_mode,
                "flow_type": self._definition.flow.type,
                "first_mover": str(first_mover) if first_mover else "",
            },
        )
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

        # Unsubscribe every handler we registered in _on_start. Without
        # this, a restart in the same process (composition root rewire,
        # test suite reuse, etc.) accumulates duplicate handlers and each
        # bus event fires _handle_game_event N times.
        for topic, callback in self._subscription_tokens:
            try:
                await self._bus.unsubscribe(topic, callback)
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "GameOrchestrator._on_stop: failed to unsubscribe %s: %s",
                    topic,
                    exc,
                )
        self._subscription_tokens = []
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

        # Build role → actor_id map for O(1) first-mover / next-player
        # resolution. Actor IDs follow the convention "{role}-{hash}", so
        # a role matches when an actor_id starts with "{role}-". Each role
        # maps to the first actor declared with that role; subsequent
        # actors with the same role are still reachable via the player_ids
        # list iteration in next-player routing.
        self._role_to_actor_id = {}
        for pid in self._player_ids:
            pid_str = str(pid)
            if "-" in pid_str:
                role = pid_str.rsplit("-", 1)[0]
                self._role_to_actor_id.setdefault(role, pid)
            # Also allow exact actor_id lookup
            self._role_to_actor_id.setdefault(pid_str, pid)

        # Select scorer by scoring_mode (the ONE place this dispatch happens)
        if definition.scoring_mode == "competitive":
            self._scorer = CompetitiveScorer(bonus_per_event=definition.flow.bonus_per_event)
        else:
            self._scorer = BehavioralScorer()

        # Filter win conditions to mode; drops score_threshold in behavioral
        self._win_evaluator = WinConditionEvaluator(
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

        # 1. Compute the tentative next event number BEFORE scoring. The
        # counter is only advanced after we've successfully scored — if
        # the scorer raises, the counter stays at N so the next event
        # gets number N+1 (not N+2). This protects competitive mode's
        # event-count-based efficiency bonus from drifting on transient
        # scoring failures.
        event_number = self._game_state.event_counter + 1

        # 2. Score the event (scorer reads state but never writes — MF1)
        ctx = ScorerContext(
            event=event,
            event_number=event_number,
            state_engine=self._state,
            player_scores=self._player_scores,
            definition=self._definition,
        )
        try:
            await self._scorer.score_event(ctx)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Scorer.score_event raised; skipping this event's scoring")
            await self._publish_engine_error(
                source="score_event",
                event_number=event_number,
                exc=exc,
            )

        # 3. Commit the counter advance + refresh stalemate deadline only
        # after scoring resolved (success or handled error). This keeps
        # event_number stable across successive events even on failures.
        self._game_state.event_counter = event_number
        self._refresh_stalemate_deadline()

        # 4. Publish incremental score updates. Append a UUID suffix to
        # every event_id so repeated or interleaved handler calls produce
        # unique IDs (the bus persists by ID and collisions would error).
        for pid, ps in self._player_scores.items():
            score_event = GameScoreUpdatedEvent(
                event_id=EventId(f"evt-score-{event_number}-{pid}-{_unique_suffix()}"),
                event_type="game.score_updated",
                timestamp=_now_timestamp(),
                actor_id=ActorId(pid),
                metric="total_score",
                value=ps.total_score,
            )
            await self._bus.publish(score_event)

        # 5. Check win conditions (Path A: natural win)
        try:
            win_result = await self._win_evaluator.check(
                scores=self._player_scores,
                game_state=self._game_state,
                state_engine=self._state,
                exhausted_players=self._exhausted_players,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Win condition check raised; game continues")
            win_result = None
            await self._publish_engine_error(
                source="win_check",
                event_number=event_number,
                exc=exc,
            )

        if win_result is not None:
            await self._terminate_natural(win_result)
            return

        # 6. Determine next player and re-activate (Option D: direct call)
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
                event_id=EventId(f"evt-all-budgets-{self._run_id}-{_unique_suffix()}"),
                event_type="game.timeout",
                timestamp=_now_timestamp(),
                reason="all_budgets",
                event_number=self._game_state.event_counter,
            )
            await self._bus.publish(timeout_event)

    async def _handle_timeout(self, event: Event) -> None:
        """Path B termination: settle open deals + publish game_terminated.

        M2 (B-cleanup.3): before committing to the Path B settlement
        flow, run the win evaluator one more time. If a natural win
        condition (e.g. ``deal_closed``) is satisfied at this moment —
        which can happen if a winning ``world.negotiate_accept`` event
        and a timeout event arrive on different bus consumer tasks in
        the same event-loop tick — delegate to :meth:`_terminate_natural`
        so the reported reason reflects the real outcome instead of the
        racing timer. Without this guard the game would misreport a
        legitimate ``deal_closed`` as ``wall_clock`` / ``stalemate``
        / etc. when the race happens.
        """
        if self._terminated:
            return
        if self._definition is None or self._scorer is None:
            return

        # M2: natural-win priority check. If a win condition is met
        # right now, the timeout lost the race — report the natural
        # outcome via _terminate_natural instead of settling.
        if self._win_evaluator is not None:
            try:
                natural_result = await self._win_evaluator.check(
                    scores=self._player_scores,
                    game_state=self._game_state,
                    state_engine=self._state,
                    exhausted_players=self._exhausted_players,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("Win check during timeout raised; proceeding with timeout path")
                natural_result = None
                await self._publish_engine_error(
                    source="win_check_on_timeout",
                    event_number=self._game_state.event_counter,
                    exc=exc,
                )
            if natural_result is not None:
                await self._terminate_natural(natural_result)
                return

        # Re-check after the await: a concurrent _handle_game_event on
        # a different bus consumer task may have set _terminated=True
        # (via _terminate_natural) during the win evaluator's await.
        # Without this re-check, both handlers would proceed to publish
        # their own GameTerminatedEvent — producing a double-publish.
        if self._terminated:
            return

        reason = str(getattr(event, "reason", "unknown"))
        self._terminated = True
        self._game_state.terminated = True
        self._cancel_failsafe_timers()

        # Query open deals for settlement. The query entity types come
        # from FlowConfig.state_summary_entity_types so future game types
        # can settle over their own entity shapes without code changes.
        open_deals: list[dict[str, Any]] = []
        entity_types = list(self._definition.flow.state_summary_entity_types)
        try:
            for entity_type in entity_types:
                try:
                    rows = await self._state.query_entities(entity_type)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Failed to query %s for settlement", entity_type)
                    await self._publish_engine_error(
                        source="state_query",
                        event_number=self._game_state.event_counter,
                        exc=exc,
                    )
                    continue
                open_deals.extend(
                    d
                    for d in rows
                    if str(d.get("status", "")).lower() in {"open", "proposed", "countered"}
                )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error in settlement query loop")
            await self._publish_engine_error(
                source="state_query",
                event_number=self._game_state.event_counter,
                exc=exc,
            )

        try:
            await self._scorer.settle(
                open_deals=open_deals,
                state_engine=self._state,
                player_scores=self._player_scores,
                definition=self._definition,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Scorer.settle raised; proceeding to termination")
            await self._publish_engine_error(
                source="settle",
                event_number=self._game_state.event_counter,
                exc=exc,
            )

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
        await self._record_lifecycle_entry(
            "timed_out",
            {
                "run_id": self._run_id,
                "reason": reason,
                "total_events": self._game_state.event_counter,
                "open_deals_settled": len(open_deals),
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
        await self._record_lifecycle_entry(
            "terminated",
            {
                "run_id": self._run_id,
                "path": "natural",
                "reason": win_result.reason,
                "winner": str(win_result.winner) if win_result.winner else None,
                "total_events": self._game_state.event_counter,
            },
        )
        await self._publish_terminated(win_result, reason=win_result.reason)

    async def _publish_terminated(self, win_result: WinResult, reason: str) -> None:
        """Publish ``GameTerminatedEvent`` and resolve the result future."""
        if self._definition is None:
            return
        wall_clock_s = self._elapsed_seconds()
        terminated_event = GameTerminatedEvent(
            event_id=EventId(f"evt-game-terminated-{self._run_id}-{_unique_suffix()}"),
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
        """Flip the ``game_active`` flag — direct call + bus publish.

        M3 (B-cleanup.3) defense-in-depth: this method flips the gate
        via TWO mechanisms to eliminate the FIFO-``_ready`` ordering
        dependency the audit flagged.

        1. **Direct call** (primary): calls ``gate.set_active(active)``
           on the :class:`GameActivePolicy` instance injected via
           ``_dependencies["game_active_gate"]`` by the composition
           root. This flips the flag *synchronously* inside this
           coroutine before any ``await`` yields control back to the
           event loop. Any activation task launched after this call
           will observe the new gate state.

        2. **Bus publish** (secondary): publishes
           :class:`GameActiveStateChangedEvent` so any OTHER subscriber
           (reporter, dashboard, test harness) also sees the flip.
           :class:`GameActivePolicy` is still subscribed to the bus
           event as a back-channel fallback — harmless because
           ``set_active`` is idempotent.
        """
        # Direct (primary): flip the gate synchronously.
        gate = self._dependencies.get("game_active_gate")
        if gate is not None:
            try:
                gate.set_active(active)
            except Exception:  # noqa: BLE001
                logger.exception("Direct gate.set_active failed; relying on bus delivery")

        # Bus publish (secondary): fan out to other subscribers.
        state_event = GameActiveStateChangedEvent(
            event_id=EventId(f"evt-game-active-{active}-{self._run_id}-{_unique_suffix()}"),
            event_type="game.active_state_changed",
            timestamp=_now_timestamp(),
            active=active,
            run_id=self._run_id,
        )
        await self._bus.publish(state_event)

    async def _publish_engine_error(
        self,
        source: str,
        event_number: int,
        exc: BaseException,
    ) -> None:
        """Publish a ``GameEngineErrorEvent`` for observability (M2 review).

        Called from every broad ``except Exception`` guard in the
        orchestrator. Keeps the continue-on-failure semantics (a single
        transient error shouldn't kill the game) but gives downstream
        subscribers (reporter, CLI, alerting) a bus signal to react to.
        """
        if self._bus is None:
            return
        try:
            err_event = GameEngineErrorEvent(
                event_id=EventId(f"evt-game-error-{source}-{_unique_suffix()}"),
                event_type="game.engine_error",
                timestamp=_now_timestamp(),
                source=source,
                event_number=event_number,
                message=str(exc),
                exception_type=type(exc).__name__,
                run_id=self._run_id,
            )
            await self._bus.publish(err_event)
        except Exception:  # noqa: BLE001
            # Error publication must never itself kill the orchestrator.
            logger.exception("Failed to publish GameEngineErrorEvent")

    async def _record_lifecycle_entry(
        self,
        event_type: str,
        details: dict[str, Any],
    ) -> None:
        """Append an :class:`EngineLifecycleEntry` to the ledger.

        Covers the M4 review finding (ledger writes missing for game
        lifecycle transitions). Uses the shared ledger entry type so we
        don't fork the ledger schema for a single engine.
        """
        ledger = self._config.get("_ledger") if self._config else None
        if ledger is None:
            return
        try:
            from volnix.ledger.entries import EngineLifecycleEntry

            entry = EngineLifecycleEntry(
                engine_name="game",
                event_type=event_type,
                details=details,
            )
            await ledger.append(entry)
        except Exception:  # noqa: BLE001
            logger.debug(
                "GameOrchestrator: ledger append failed for %s",
                event_type,
                exc_info=True,
            )

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
            event_id=EventId(f"evt-wall-clock-{self._run_id}-{_unique_suffix()}"),
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
            event_id=EventId(f"evt-stalemate-{self._run_id}-{_unique_suffix()}"),
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

        Uses the ``_role_to_actor_id`` map built in ``configure()`` for
        O(1) lookup (supports both role name ``"buyer"`` and exact
        actor_id ``"buyer-001"``). Falls back to the first player in
        the declared list when nothing matches.
        """
        if self._definition is None or not self._player_ids:
            return None
        first_mover = self._definition.flow.first_mover or ""
        if first_mover:
            resolved = self._role_to_actor_id.get(first_mover)
            if resolved is not None:
                return resolved
        return self._player_ids[0]

    def _next_player_for(self, event: WorldEvent) -> ActorId | None:
        """Given a just-committed event, return the actor to activate next.

        Serial mode: the first non-mover, non-eliminated player in
        registration order. None if there's no such player.

        Parallel mode: ``None`` (all players active concurrently; no
        re-activation needed — each acts on their own LLM loop).
        """
        if self._definition is None:
            return None
        if self._definition.flow.activation_mode == "parallel":
            return None
        mover = str(event.actor_id)
        for pid in self._player_ids:
            pid_str = str(pid)
            if pid_str == mover:
                continue
            score = self._player_scores.get(pid_str)
            if score is not None and score.eliminated:
                continue
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

        Entity types come from ``FlowConfig.state_summary_entity_types``
        so future game types (auction, debate) can opt in without
        touching this method.
        """
        if self._state is None or self._definition is None:
            return ""
        parts: list[str] = [f"Game state at event #{self._game_state.event_counter}:"]
        entity_types = list(self._definition.flow.state_summary_entity_types)
        for entity_type in entity_types:
            try:
                rows = await self._state.query_entities(entity_type)
            except Exception as exc:  # noqa: BLE001
                logger.exception("State summary query failed for entity_type=%s", entity_type)
                await self._publish_engine_error(
                    source="state_summary",
                    event_number=self._game_state.event_counter,
                    exc=exc,
                )
                continue
            for row in rows:
                # Generic rendering — show id + status + any top-level
                # scalar fields that look like game-state attributes.
                row_id = row.get("id", "?")
                status = row.get("status", "?")
                terms = row.get("terms") or {}
                last_by = row.get("last_proposed_by") or "?"
                parts.append(
                    f"- {entity_type} {row_id}: status={status}, "
                    f"last_proposed_by={last_by}, terms={terms}"
                )
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
