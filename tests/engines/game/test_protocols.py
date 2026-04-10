"""Tests for game extension protocols and context models."""

from __future__ import annotations

import pytest

from volnix.engines.game.definition import (
    PlayerScore,
    RoundState,
    ScoringMetric,
    WinCondition,
)
from volnix.engines.game.protocols import (
    RoundEvaluator,
    ScoringContext,
    ScoringProvider,
    TurnProtocol,
    WinConditionContext,
    WinConditionHandler,
)


class TestScoringContext:
    def test_scoring_context_is_frozen(self):
        ctx = ScoringContext(
            player_id="p1",
            metric=ScoringMetric(name="test"),
        )
        assert ctx.player_id == "p1"
        with pytest.raises(Exception):
            ctx.player_id = "p2"  # type: ignore[misc]

    def test_scoring_context_defaults(self):
        ctx = ScoringContext(
            player_id="p1",
            metric=ScoringMetric(name="test"),
        )
        assert ctx.state_engine is None
        assert ctx.events == []
        assert ctx.resolved_entity_types == {}

    def test_scoring_context_with_all_fields(self):
        metric = ScoringMetric(name="val", source="state", entity_type="acct", field="eq")
        ctx = ScoringContext(
            player_id="p1",
            metric=metric,
            state_engine="mock_engine",
            events=["e1", "e2"],
            resolved_entity_types={"acct": "pack_acct"},
        )
        assert ctx.player_id == "p1"
        assert ctx.metric.name == "val"
        assert ctx.state_engine == "mock_engine"
        assert len(ctx.events) == 2
        assert ctx.resolved_entity_types == {"acct": "pack_acct"}


class TestWinConditionContext:
    def test_win_condition_context_is_frozen(self):
        ctx = WinConditionContext(
            condition=WinCondition(type="rounds_complete"),
        )
        assert ctx.condition.type == "rounds_complete"

    def test_win_condition_context_defaults(self):
        ctx = WinConditionContext(
            condition=WinCondition(),
        )
        assert ctx.scores == {}
        assert ctx.round_state.current_round == 0

    def test_win_condition_context_with_scores(self):
        scores = {"p1": PlayerScore(actor_id="p1", total_score=100.0)}
        ctx = WinConditionContext(
            condition=WinCondition(type="score_threshold", metric="pts", threshold=50.0),
            scores=scores,
            round_state=RoundState(current_round=5, total_rounds=10),
        )
        assert "p1" in ctx.scores
        assert ctx.round_state.current_round == 5


class TestProtocolsAreRuntimeCheckable:
    def test_scoring_provider_protocol(self):
        from volnix.engines.game.scorer import StateScoringProvider

        assert isinstance(StateScoringProvider(), ScoringProvider)

    def test_events_scoring_provider_protocol(self):
        from volnix.engines.game.scorer import EventsScoringProvider

        assert isinstance(EventsScoringProvider(), ScoringProvider)

    def test_budget_scoring_provider_protocol(self):
        from volnix.engines.game.scorer import BudgetScoringProvider

        assert isinstance(BudgetScoringProvider(), ScoringProvider)

    def test_win_condition_handler_protocol(self):
        from volnix.engines.game.win_conditions import ScoreThresholdHandler

        assert isinstance(ScoreThresholdHandler(), WinConditionHandler)

    def test_rounds_complete_handler_protocol(self):
        from volnix.engines.game.win_conditions import RoundsCompleteHandler

        assert isinstance(RoundsCompleteHandler(), WinConditionHandler)

    def test_elimination_handler_protocol(self):
        from volnix.engines.game.win_conditions import EliminationHandler

        assert isinstance(EliminationHandler(), WinConditionHandler)

    def test_turn_protocol(self):
        from volnix.game.runner import IndependentTurnProtocol

        assert isinstance(IndependentTurnProtocol(), TurnProtocol)

    def test_round_evaluator_protocol(self):
        """A minimal class implementing the protocol is recognized."""

        class StubEvaluator:
            async def evaluate(self, state_engine, round_events, round_state, player_scores):
                pass

            async def build_deliverable_extras(self, state_engine):
                return {}

        assert isinstance(StubEvaluator(), RoundEvaluator)

    def test_round_evaluator_protocol_requires_build_deliverable_extras(self):
        """A class missing build_deliverable_extras is NOT a RoundEvaluator."""

        class IncompleteEvaluator:
            async def evaluate(self, state_engine, round_events, round_state, player_scores):
                pass

        assert not isinstance(IncompleteEvaluator(), RoundEvaluator)

    def test_non_conforming_class_fails_protocol(self):
        """A class missing the required method is NOT a ScoringProvider."""

        class NotAProvider:
            pass

        assert not isinstance(NotAProvider(), ScoringProvider)
