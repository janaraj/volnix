"""Event-driven win condition handlers.

Handlers for the GameOrchestrator event-driven flow. Each handler reads
:class:`GameState` (event_counter, terminated, started_at) and fires
either on committed game tool events (natural win path) or on timeout
events from the orchestrator's failsafe timers (timeout path). See
``volnix/engines/game/orchestrator.py`` for the calling contract.

Six primary handlers:

- ``DealClosedHandler``: any deal reaches status=accepted
- ``DealRejectedHandler``: any deal reaches status=rejected
- ``StalemateHandler``: stalemate timer fired (orchestrator-driven)
- ``WallClockElapsedHandler``: wall-clock timer fired
- ``MaxEventsExceededHandler``: event counter hit the cap
- ``AllBudgetsExhaustedHandler``: all game players eliminated

Two additional handlers:

- ``ScoreThresholdHandler``: competitive-mode only — filtered out
  of the evaluator chain when ``scoring_mode == "behavioral"``
- ``EliminationHandler``: eliminate below metric threshold
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from volnix.core.types import ActorId
from volnix.engines.game.definition import (
    GameState,
    PlayerScore,
    WinCondition,
    WinResult,
)

logger = logging.getLogger(__name__)


class WinConditionContext(BaseModel):
    """Context passed to event-driven win condition handlers.

    Frozen per DESIGN_PRINCIPLES.md: value objects passed to handlers are
    immutable. Mutable inner containers (``scores: dict``,
    ``exhausted_players: set``) are owned by the caller (orchestrator);
    handlers may read from them but must not replace them.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    condition: WinCondition
    scores: dict[str, PlayerScore]
    game_state: GameState
    state_engine: Any  # StateEngineProtocol
    exhausted_players: set[str]


@runtime_checkable
class WinConditionHandler(Protocol):
    """Protocol for event-driven win condition handlers."""

    async def check(self, ctx: WinConditionContext) -> WinResult | None:
        """Return ``WinResult`` if the condition is met, else ``None``."""
        ...


class DealClosedHandler:
    """Natural win: any deal reaches status=accepted.

    Queries ``negotiation_deal`` entities from state on each check.
    In competitive mode, the winner is the highest-scoring non-eliminated
    player. In behavioral mode, winner is ``None`` (no leaderboard);
    the game simply terminates.
    """

    async def check(self, ctx: WinConditionContext) -> WinResult | None:
        try:
            deals = await ctx.state_engine.query_entities("negotiation_deal")
        except Exception as exc:  # noqa: BLE001
            logger.warning("DealClosedHandler: failed to query deals: %s", exc)
            return None
        for deal in deals:
            if str(deal.get("status", "")).lower() == "accepted":
                winner = self._resolve_winner(ctx.scores)
                return WinResult(
                    winner=winner,
                    reason="deal_closed",
                    final_standings=_standings(ctx.scores),
                    behavior_scores={
                        pid: dict(s.behavior_metrics) for pid, s in ctx.scores.items()
                    },
                )
        return None

    @staticmethod
    def _resolve_winner(scores: dict[str, PlayerScore]) -> ActorId | None:
        alive = [(pid, s) for pid, s in scores.items() if not s.eliminated]
        if not alive:
            return None
        # Highest total_score wins. Ties broken by dict insertion order.
        top_pid, _ = max(alive, key=lambda pair: pair[1].total_score)
        return ActorId(top_pid)


class DealRejectedHandler:
    """Natural win: any deal reaches status=rejected.

    BATNA application is done by the scorer (in Path B settlement),
    not here. This handler just detects the state and fires termination.
    """

    async def check(self, ctx: WinConditionContext) -> WinResult | None:
        try:
            deals = await ctx.state_engine.query_entities("negotiation_deal")
        except Exception as exc:  # noqa: BLE001
            logger.warning("DealRejectedHandler: failed to query deals: %s", exc)
            return None
        for deal in deals:
            if str(deal.get("status", "")).lower() == "rejected":
                return WinResult(
                    winner=None,
                    reason="deal_rejected",
                    final_standings=_standings(ctx.scores),
                    behavior_scores={
                        pid: dict(s.behavior_metrics) for pid, s in ctx.scores.items()
                    },
                )
        return None


class StalemateHandler:
    """Timeout: stalemate timer fired.

    This handler is always a no-op on per-event checks. Stalemate
    detection is done by the orchestrator's stalemate watcher task,
    which publishes a ``GameTimeoutEvent(reason="stalemate")`` when the
    deadline elapses. The orchestrator handles the timeout directly
    (calls scorer.settle + publishes GameTerminatedEvent). This handler
    exists only so blueprints can declare ``type: stalemate_timeout``
    and the evaluator registry validates it.
    """

    async def check(self, ctx: WinConditionContext) -> WinResult | None:
        return None


class WallClockElapsedHandler:
    """Timeout: wall clock elapsed.

    Same as StalemateHandler — a no-op on per-event checks. The
    orchestrator's wall_clock task drives termination directly.
    """

    async def check(self, ctx: WinConditionContext) -> WinResult | None:
        return None


class MaxEventsExceededHandler:
    """Timeout: committed event counter reached the cap.

    Can fire on per-event checks (the orchestrator increments the
    counter before calling the evaluator). Reads ``max_events`` from
    the condition's ``type_config`` or falls back to zero (which
    effectively disables the handler).
    """

    async def check(self, ctx: WinConditionContext) -> WinResult | None:
        cap = int(ctx.condition.type_config.get("max_events", 0))
        if cap <= 0:
            return None
        if ctx.game_state.event_counter >= cap:
            return WinResult(
                winner=None,
                reason="max_events_exceeded",
                final_standings=_standings(ctx.scores),
                behavior_scores={pid: dict(s.behavior_metrics) for pid, s in ctx.scores.items()},
            )
        return None


class AllBudgetsExhaustedHandler:
    """Timeout: every game player's ``world_actions`` budget is exhausted.

    Tracked in the orchestrator as ``_exhausted_players: set[str]``,
    populated by subscribing to ``BudgetExhaustedEvent``. When the set
    size equals the total number of game players, this handler returns
    a terminal result. The orchestrator also publishes
    ``GameTimeoutEvent(reason="all_budgets")`` for Path B settlement.
    """

    async def check(self, ctx: WinConditionContext) -> WinResult | None:
        if not ctx.scores:
            return None
        if len(ctx.exhausted_players) >= len(ctx.scores):
            return WinResult(
                winner=None,
                reason="all_budgets_exhausted",
                final_standings=_standings(ctx.scores),
                behavior_scores={pid: dict(s.behavior_metrics) for pid, s in ctx.scores.items()},
            )
        return None


class ScoreThresholdHandler:
    """Competitive-mode-only: a player's metric meets a threshold.

    Filtered out of the evaluator chain at ``configure()`` time when
    ``GameDefinition.scoring_mode == "behavioral"`` — never executed.
    """

    async def check(self, ctx: WinConditionContext) -> WinResult | None:
        crossers: list[tuple[str, float]] = []
        for pid, score in ctx.scores.items():
            if score.eliminated:
                continue
            val = score.get_metric(ctx.condition.metric)
            if val >= ctx.condition.threshold:
                crossers.append((pid, val))
        if not crossers:
            return None
        winner_pid, _ = max(crossers, key=lambda pair: pair[1])
        return WinResult(
            winner=ActorId(winner_pid),
            reason="score_threshold",
            final_standings=_standings(ctx.scores),
            behavior_scores={pid: dict(s.behavior_metrics) for pid, s in ctx.scores.items()},
        )


class EliminationHandler:
    """Eliminate players below a metric threshold. Last standing wins.

    Marks eliminated players via ``eliminated_at_event`` (reads
    ``ctx.game_state.event_counter`` at mark time).
    """

    async def check(self, ctx: WinConditionContext) -> WinResult | None:
        threshold = ctx.condition.threshold
        metric = ctx.condition.metric
        for pid, score in ctx.scores.items():
            if score.eliminated:
                continue
            val = score.get_metric(metric)
            if ctx.condition.below and val < threshold:
                score.eliminated = True
                score.eliminated_at_event = ctx.game_state.event_counter
        alive = [pid for pid, s in ctx.scores.items() if not s.eliminated]
        if len(alive) == 1:
            return WinResult(
                winner=ActorId(alive[0]),
                reason="last_standing",
                final_standings=_standings(ctx.scores),
                behavior_scores={pid: dict(s.behavior_metrics) for pid, s in ctx.scores.items()},
            )
        if len(alive) == 0:
            return WinResult(
                winner=None,
                reason="all_eliminated",
                final_standings=_standings(ctx.scores),
                behavior_scores={pid: dict(s.behavior_metrics) for pid, s in ctx.scores.items()},
            )
        return None


WIN_CONDITION_HANDLER_REGISTRY: dict[str, type] = {
    "deal_closed": DealClosedHandler,
    "deal_rejected": DealRejectedHandler,
    "stalemate_timeout": StalemateHandler,
    "wall_clock_elapsed": WallClockElapsedHandler,
    "max_events_exceeded": MaxEventsExceededHandler,
    "all_budgets_exhausted": AllBudgetsExhaustedHandler,
    "score_threshold": ScoreThresholdHandler,
    "elimination": EliminationHandler,
}


class WinConditionEvaluator:
    """Runs all registered event-driven handlers and returns the first match.

    Filters out competitive-only conditions (``score_threshold``) when
    ``scoring_mode == "behavioral"`` at ``__init__`` time. This is the
    single place where the behavioral vs competitive routing affects
    win conditions — see plan section 5 'scoring mode routing'.
    """

    def __init__(
        self,
        conditions: list[WinCondition],
        scoring_mode: str,
    ) -> None:
        filtered: list[tuple[WinCondition, WinConditionHandler]] = []
        for cond in conditions:
            handler_cls = WIN_CONDITION_HANDLER_REGISTRY.get(cond.type)
            if handler_cls is None:
                logger.warning(
                    "WinConditionEvaluator: unknown win condition type %r — skipping",
                    cond.type,
                )
                continue
            if scoring_mode == "behavioral" and cond.type == "score_threshold":
                logger.info(
                    "WinConditionEvaluator: filtering out "
                    "score_threshold condition in behavioral mode"
                )
                continue
            filtered.append((cond, handler_cls()))
        self._handlers = filtered

    async def check(
        self,
        scores: dict[str, PlayerScore],
        game_state: GameState,
        state_engine: Any,
        exhausted_players: set[str] | None = None,
    ) -> WinResult | None:
        """Run handlers in declared order; return the first WinResult."""
        exhausted = exhausted_players or set()
        for cond, handler in self._handlers:
            ctx = WinConditionContext(
                condition=cond,
                scores=scores,
                game_state=game_state,
                state_engine=state_engine,
                exhausted_players=exhausted,
            )
            result = await handler.check(ctx)
            if result is not None:
                return result
        return None


def _standings(scores: dict[str, PlayerScore]) -> list[dict[str, Any]]:
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
