"""Win condition evaluator — generic DSL for game end conditions.

Evaluates a list of WinCondition rules against current player scores
and round state. Returns WinResult when any condition is met.
"""

from __future__ import annotations

import logging
from typing import Any

from volnix.engines.game.definition import PlayerScore, RoundState, WinCondition, WinResult

logger = logging.getLogger(__name__)


class WinConditionEvaluator:
    """Generic evaluator for game win/loss conditions."""

    def __init__(self, conditions: list[WinCondition]) -> None:
        self._conditions = list(conditions)

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
        if condition.type == "score_threshold":
            return self._check_score_threshold(condition, scores)
        elif condition.type == "rounds_complete":
            return self._check_rounds_complete(condition, scores, round_state)
        elif condition.type == "elimination":
            return self._check_elimination(condition, scores, round_state)
        elif condition.type == "time_limit":
            # Time limit handled by runner, not evaluator
            return None
        return None

    def _check_score_threshold(
        self,
        condition: WinCondition,
        scores: dict[str, PlayerScore],
    ) -> WinResult | None:
        """First player to reach threshold wins."""
        for pid, score in scores.items():
            if score.eliminated:
                continue
            val = score.get_metric(condition.metric)
            if val >= condition.threshold:
                standings = self._build_standings(scores)
                return WinResult(
                    winner=pid,
                    reason="score_threshold",
                    final_standings=standings,
                )
        return None

    def _check_rounds_complete(
        self,
        condition: WinCondition,
        scores: dict[str, PlayerScore],
        round_state: RoundState,
    ) -> WinResult | None:
        """After all rounds, highest score wins."""
        if round_state.current_round >= round_state.total_rounds:
            alive = {pid: s for pid, s in scores.items() if not s.eliminated}
            if not alive:
                return WinResult(
                    winner=None,
                    reason="all_eliminated",
                    final_standings=self._build_standings(scores),
                )
            top_pid = max(alive, key=lambda pid: alive[pid].total_score)
            return WinResult(
                winner=top_pid,
                reason="rounds_complete",
                final_standings=self._build_standings(scores),
            )
        return None

    def _check_elimination(
        self,
        condition: WinCondition,
        scores: dict[str, PlayerScore],
        round_state: RoundState,
    ) -> WinResult | None:
        """Eliminate players below threshold. Last one standing wins."""
        for pid, score in scores.items():
            if score.eliminated:
                continue
            val = score.get_metric(condition.metric)
            if condition.below and val < condition.threshold:
                score.eliminated = True
                score.elimination_round = round_state.current_round

        alive = [pid for pid, s in scores.items() if not s.eliminated]
        if len(alive) == 1:
            return WinResult(
                winner=alive[0],
                reason="last_standing",
                final_standings=self._build_standings(scores),
            )
        if len(alive) == 0:
            return WinResult(
                winner=None,
                reason="all_eliminated",
                final_standings=self._build_standings(scores),
            )
        return None

    @staticmethod
    def _build_standings(scores: dict[str, PlayerScore]) -> list[dict[str, Any]]:
        """Build sorted standings list."""
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
