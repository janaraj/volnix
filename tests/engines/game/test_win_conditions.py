"""Tests for WinConditionEvaluator."""

from __future__ import annotations

from volnix.engines.game.definition import PlayerScore, RoundState, WinCondition
from volnix.engines.game.win_conditions import WinConditionEvaluator


def _make_score(actor_id: str, total: float = 0.0, **metrics: float) -> PlayerScore:
    """Helper to build a PlayerScore with optional metrics."""
    return PlayerScore(actor_id=actor_id, metrics=dict(metrics), total_score=total)


class TestScoreThreshold:
    def test_score_threshold_met_returns_winner(self):
        condition = WinCondition(type="score_threshold", metric="points", threshold=100.0)
        evaluator = WinConditionEvaluator([condition])

        scores = {
            "p1": _make_score("p1", total=120.0, points=120.0),
            "p2": _make_score("p2", total=50.0, points=50.0),
        }
        round_state = RoundState(current_round=3, total_rounds=10)

        result = evaluator.evaluate(scores, round_state)

        assert result is not None
        assert result.winner == "p1"
        assert result.reason == "score_threshold"
        assert len(result.final_standings) == 2

    def test_score_threshold_not_met_returns_none(self):
        condition = WinCondition(type="score_threshold", metric="points", threshold=100.0)
        evaluator = WinConditionEvaluator([condition])

        scores = {
            "p1": _make_score("p1", total=50.0, points=50.0),
            "p2": _make_score("p2", total=30.0, points=30.0),
        }
        round_state = RoundState(current_round=3, total_rounds=10)

        result = evaluator.evaluate(scores, round_state)
        assert result is None

    def test_eliminated_player_excluded_from_threshold(self):
        condition = WinCondition(type="score_threshold", metric="points", threshold=100.0)
        evaluator = WinConditionEvaluator([condition])

        eliminated = _make_score("p1", total=200.0, points=200.0)
        eliminated.eliminated = True

        scores = {
            "p1": eliminated,
            "p2": _make_score("p2", total=50.0, points=50.0),
        }
        round_state = RoundState(current_round=3, total_rounds=10)

        result = evaluator.evaluate(scores, round_state)
        assert result is None

    def test_multiple_crossers_highest_wins(self):
        """When multiple players cross threshold, highest scorer wins.

        This is the fix for the negotiation-game bug where both parties
        to an accepted deal cross the threshold simultaneously but the
        old logic returned whoever was first in dict iteration order.
        """
        condition = WinCondition(type="score_threshold", metric="points", threshold=0.01)
        evaluator = WinConditionEvaluator([condition])

        # p1 crosses threshold with lower score; p2 with higher score
        scores = {
            "p1": _make_score("p1", total=41.2, points=41.2),
            "p2": _make_score("p2", total=107.0, points=107.0),
        }
        round_state = RoundState(current_round=3, total_rounds=8)

        result = evaluator.evaluate(scores, round_state)

        assert result is not None
        assert result.winner == "p2"  # p2 has higher score, not p1 (first in dict)

    def test_multiple_crossers_highest_wins_reverse_insertion(self):
        """Regression guard: insertion order of the lower scorer must not matter.

        If the old first-in-dict logic were still in place, this test would
        return the low scorer. The fix guarantees the highest scorer wins
        regardless of dict order.
        """
        condition = WinCondition(type="score_threshold", metric="points", threshold=0.01)
        evaluator = WinConditionEvaluator([condition])

        # Low scorer FIRST, high scorer SECOND — opposite of the bug report
        scores = {
            "low": _make_score("low", total=5.0, points=5.0),
            "high": _make_score("high", total=500.0, points=500.0),
        }
        round_state = RoundState(current_round=1, total_rounds=10)

        result = evaluator.evaluate(scores, round_state)

        assert result is not None
        assert result.winner == "high"

    def test_multiple_crossers_exact_tie_stable_first(self):
        """Exact-value ties fall back to dict insertion order (via `max` stability).

        This documents the tie-break semantics so future changes don't
        accidentally regress them.
        """
        condition = WinCondition(type="score_threshold", metric="points", threshold=0.01)
        evaluator = WinConditionEvaluator([condition])

        scores = {
            "first_inserted": _make_score("first_inserted", total=50.0, points=50.0),
            "second_inserted": _make_score("second_inserted", total=50.0, points=50.0),
        }
        round_state = RoundState(current_round=1, total_rounds=10)

        result = evaluator.evaluate(scores, round_state)

        assert result is not None
        assert result.winner == "first_inserted"

    def test_multiple_crossers_eliminated_players_excluded(self):
        """Eliminated players are excluded even in multi-crosser scenarios."""
        condition = WinCondition(type="score_threshold", metric="points", threshold=0.01)
        evaluator = WinConditionEvaluator([condition])

        eliminated_high = _make_score("elim", total=1000.0, points=1000.0)
        eliminated_high.eliminated = True

        scores = {
            "elim": eliminated_high,
            "alive_low": _make_score("alive_low", total=10.0, points=10.0),
        }
        round_state = RoundState(current_round=1, total_rounds=10)

        result = evaluator.evaluate(scores, round_state)

        assert result is not None
        assert result.winner == "alive_low"


class TestRoundsComplete:
    def test_rounds_complete_highest_wins(self):
        condition = WinCondition(type="rounds_complete")
        evaluator = WinConditionEvaluator([condition])

        scores = {
            "p1": _make_score("p1", total=80.0, points=80.0),
            "p2": _make_score("p2", total=120.0, points=120.0),
        }
        round_state = RoundState(current_round=10, total_rounds=10)

        result = evaluator.evaluate(scores, round_state)

        assert result is not None
        assert result.winner == "p2"
        assert result.reason == "rounds_complete"

    def test_all_eliminated(self):
        condition = WinCondition(type="rounds_complete")
        evaluator = WinConditionEvaluator([condition])

        p1 = _make_score("p1", total=0.0)
        p1.eliminated = True
        p2 = _make_score("p2", total=0.0)
        p2.eliminated = True

        scores = {"p1": p1, "p2": p2}
        round_state = RoundState(current_round=10, total_rounds=10)

        result = evaluator.evaluate(scores, round_state)

        assert result is not None
        assert result.winner is None
        assert result.reason == "all_eliminated"


class TestElimination:
    def test_elimination_below_threshold(self):
        condition = WinCondition(type="elimination", metric="health", threshold=10.0, below=True)
        evaluator = WinConditionEvaluator([condition])

        scores = {
            "p1": _make_score("p1", total=50.0, health=50.0),
            "p2": _make_score("p2", total=5.0, health=5.0),
            "p3": _make_score("p3", total=30.0, health=30.0),
        }
        round_state = RoundState(current_round=3, total_rounds=10)

        result = evaluator.evaluate(scores, round_state)

        # p2 eliminated but 2 still alive, no winner yet
        assert result is None
        assert scores["p2"].eliminated is True

    def test_elimination_last_standing(self):
        condition = WinCondition(type="elimination", metric="health", threshold=10.0, below=True)
        evaluator = WinConditionEvaluator([condition])

        p2 = _make_score("p2", total=5.0, health=5.0)
        p2.eliminated = True

        scores = {
            "p1": _make_score("p1", total=50.0, health=50.0),
            "p2": p2,
            "p3": _make_score("p3", total=3.0, health=3.0),
        }
        round_state = RoundState(current_round=5, total_rounds=10)

        result = evaluator.evaluate(scores, round_state)

        assert result is not None
        assert result.winner == "p1"
        assert result.reason == "last_standing"

    def test_elimination_sets_elimination_round(self):
        """Elimination sets elimination_round on the PlayerScore."""
        condition = WinCondition(type="elimination", metric="health", threshold=10.0, below=True)
        evaluator = WinConditionEvaluator([condition])
        p1 = PlayerScore(actor_id="p1")
        p1.metrics = {"health": 50.0}
        p1.total_score = 50.0
        p2 = PlayerScore(actor_id="p2")
        p2.metrics = {"health": 5.0}
        p2.total_score = 5.0
        scores = {"p1": p1, "p2": p2}
        round_state = RoundState(current_round=7, total_rounds=10)
        evaluator.evaluate(scores, round_state)
        assert p2.eliminated is True
        assert p2.elimination_round == 7


class TestEdgeCases:
    def test_no_conditions_returns_none(self):
        evaluator = WinConditionEvaluator([])
        scores = {"p1": _make_score("p1", total=100.0)}
        round_state = RoundState(current_round=5, total_rounds=10)

        result = evaluator.evaluate(scores, round_state)
        assert result is None


# ---------------------------------------------------------------------------
# Registry + extensibility tests
# ---------------------------------------------------------------------------

from volnix.engines.game.protocols import WinConditionContext
from volnix.engines.game.win_conditions import (
    WIN_CONDITION_HANDLER_REGISTRY,
    EliminationHandler,
    RoundsCompleteHandler,
    ScoreThresholdHandler,
    TimeLimitHandler,
    build_standings,
)


class TestWinConditionHandlerRegistry:
    def test_registry_contains_built_in_handlers(self):
        assert "score_threshold" in WIN_CONDITION_HANDLER_REGISTRY
        assert "rounds_complete" in WIN_CONDITION_HANDLER_REGISTRY
        assert "elimination" in WIN_CONDITION_HANDLER_REGISTRY
        assert "time_limit" in WIN_CONDITION_HANDLER_REGISTRY
        assert WIN_CONDITION_HANDLER_REGISTRY["score_threshold"] is ScoreThresholdHandler
        assert WIN_CONDITION_HANDLER_REGISTRY["rounds_complete"] is RoundsCompleteHandler
        assert WIN_CONDITION_HANDLER_REGISTRY["elimination"] is EliminationHandler
        assert WIN_CONDITION_HANDLER_REGISTRY["time_limit"] is TimeLimitHandler

    def test_default_evaluator_uses_registry(self):
        evaluator = WinConditionEvaluator([])
        assert "score_threshold" in evaluator._handlers
        assert "rounds_complete" in evaluator._handlers
        assert "elimination" in evaluator._handlers

    def test_unknown_condition_type_returns_none(self):
        condition = WinCondition(type="unknown_type")
        evaluator = WinConditionEvaluator([condition])
        scores = {"p1": _make_score("p1", total=100.0)}
        round_state = RoundState(current_round=5, total_rounds=10)
        result = evaluator.evaluate(scores, round_state)
        assert result is None


class TestCustomWinConditionHandler:
    def test_custom_handler_via_constructor(self):
        from volnix.engines.game.definition import WinResult

        class AlwaysWinHandler:
            def check(self, ctx: WinConditionContext) -> WinResult | None:
                return WinResult(winner="custom_winner", reason="custom_rule")

        condition = WinCondition(type="custom_win")
        evaluator = WinConditionEvaluator(
            [condition],
            handlers={"custom_win": AlwaysWinHandler()},
        )
        scores = {"p1": _make_score("p1")}
        round_state = RoundState(current_round=1, total_rounds=10)
        result = evaluator.evaluate(scores, round_state)
        assert result is not None
        assert result.winner == "custom_winner"
        assert result.reason == "custom_rule"

    def test_register_handler_at_runtime(self):
        from volnix.engines.game.definition import WinResult

        class LateHandler:
            def check(self, ctx: WinConditionContext) -> WinResult | None:
                return WinResult(winner="late", reason="registered_late")

        condition = WinCondition(type="late_type")
        evaluator = WinConditionEvaluator([condition])

        scores = {"p1": _make_score("p1")}
        round_state = RoundState(current_round=1, total_rounds=10)
        result = evaluator.evaluate(scores, round_state)
        assert result is None

        evaluator.register_handler("late_type", LateHandler())
        result = evaluator.evaluate(scores, round_state)
        assert result is not None
        assert result.winner == "late"


class TestBuildStandingsUtility:
    def test_build_standings_sorted_descending(self):
        scores = {
            "p1": _make_score("p1", total=50.0),
            "p2": _make_score("p2", total=150.0),
            "p3": _make_score("p3", total=100.0),
        }
        standings = build_standings(scores)
        assert standings[0]["actor_id"] == "p2"
        assert standings[0]["rank"] == 1
        assert standings[1]["actor_id"] == "p3"
        assert standings[2]["actor_id"] == "p1"
        assert standings[2]["rank"] == 3

    def test_build_standings_empty(self):
        standings = build_standings({})
        assert standings == []
