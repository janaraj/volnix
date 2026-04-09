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
