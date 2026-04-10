"""Win condition evaluator — pluggable handlers for game end conditions.

Handlers are registered in WIN_CONDITION_HANDLER_REGISTRY by condition type.
Built-in handlers: score_threshold, rounds_complete, elimination, time_limit.
Custom handlers can be registered at runtime via
WinConditionEvaluator.register_handler() or by passing a handlers dict
to the constructor.
"""

from __future__ import annotations

import logging
from typing import Any

from volnix.engines.game.definition import PlayerScore, RoundState, WinCondition, WinResult
from volnix.engines.game.protocols import WinConditionContext, WinConditionHandler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared utility
# ---------------------------------------------------------------------------


def build_standings(scores: dict[str, PlayerScore]) -> list[dict[str, Any]]:
    """Build sorted standings list. Shared by multiple handlers."""
    sorted_players = sorted(
        scores.values(),
        key=lambda s: s.total_score,
        reverse=True,
    )
    return [
        {
            "actor_id": s.actor_id,
            "total_score": s.total_score,
            "metrics": dict(s.metrics),
            "eliminated": s.eliminated,
            "rank": i + 1,
        }
        for i, s in enumerate(sorted_players)
    ]


# ---------------------------------------------------------------------------
# Built-in win condition handlers
# ---------------------------------------------------------------------------


class ScoreThresholdHandler:
    """A player wins when their metric meets the threshold.

    If multiple players cross the threshold in the same evaluation (e.g.,
    both sides scored simultaneously when a negotiation deal is accepted),
    the player with the highest metric value is declared the winner.
    Exact-value ties are broken by dict insertion order, matching Python's
    ``max`` stability, which preserves legacy single-crosser behavior.
    """

    def check(self, ctx: WinConditionContext) -> WinResult | None:
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
            winner=winner_pid,
            reason="score_threshold",
            final_standings=build_standings(ctx.scores),
        )


class RoundsCompleteHandler:
    """After all rounds, highest score wins."""

    def check(self, ctx: WinConditionContext) -> WinResult | None:
        if ctx.round_state.current_round >= ctx.round_state.total_rounds:
            alive = {pid: s for pid, s in ctx.scores.items() if not s.eliminated}
            if not alive:
                return WinResult(
                    winner=None,
                    reason="all_eliminated",
                    final_standings=build_standings(ctx.scores),
                )
            top_pid = max(alive, key=lambda pid: alive[pid].total_score)
            return WinResult(
                winner=top_pid,
                reason="rounds_complete",
                final_standings=build_standings(ctx.scores),
            )
        return None


class EliminationHandler:
    """Eliminate players below metric threshold. Last standing wins."""

    def check(self, ctx: WinConditionContext) -> WinResult | None:
        for pid, score in ctx.scores.items():
            if score.eliminated:
                continue
            val = score.get_metric(ctx.condition.metric)
            if ctx.condition.below and val < ctx.condition.threshold:
                score.eliminated = True
                score.elimination_round = ctx.round_state.current_round

        alive = [pid for pid, s in ctx.scores.items() if not s.eliminated]
        if len(alive) == 1:
            return WinResult(
                winner=alive[0],
                reason="last_standing",
                final_standings=build_standings(ctx.scores),
            )
        if len(alive) == 0:
            return WinResult(
                winner=None,
                reason="all_eliminated",
                final_standings=build_standings(ctx.scores),
            )
        return None


class TimeLimitHandler:
    """Time limit — handled by runner, not evaluator."""

    def check(self, ctx: WinConditionContext) -> WinResult | None:
        return None


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

WIN_CONDITION_HANDLER_REGISTRY: dict[str, type[WinConditionHandler]] = {
    "score_threshold": ScoreThresholdHandler,
    "rounds_complete": RoundsCompleteHandler,
    "elimination": EliminationHandler,
    "time_limit": TimeLimitHandler,
}


# ---------------------------------------------------------------------------
# WinConditionEvaluator
# ---------------------------------------------------------------------------


class WinConditionEvaluator:
    """Generic evaluator using pluggable handlers."""

    def __init__(
        self,
        conditions: list[WinCondition],
        handlers: dict[str, WinConditionHandler] | None = None,
    ) -> None:
        self._conditions = list(conditions)
        if handlers is not None:
            self._handlers: dict[str, WinConditionHandler] = dict(handlers)
        else:
            self._handlers = {name: cls() for name, cls in WIN_CONDITION_HANDLER_REGISTRY.items()}

    def register_handler(self, name: str, handler: WinConditionHandler) -> None:
        """Register a custom win condition handler at runtime."""
        self._handlers[name] = handler

    def evaluate(
        self,
        scores: dict[str, PlayerScore],
        round_state: RoundState,
    ) -> WinResult | None:
        """Check all conditions. Returns WinResult if any met, None otherwise."""
        for condition in self._conditions:
            result = self._check_condition(condition, scores, round_state)
            if result is not None:
                return result
        return None

    def _check_condition(
        self,
        condition: WinCondition,
        scores: dict[str, PlayerScore],
        round_state: RoundState,
    ) -> WinResult | None:
        handler = self._handlers.get(condition.type)
        if handler is None:
            logger.warning("No handler registered for condition type '%s'", condition.type)
            return None
        ctx = WinConditionContext(
            condition=condition,
            scores=scores,
            round_state=round_state,
        )
        return handler.check(ctx)
