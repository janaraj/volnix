"""Tests for volnix/engines/game/definition.py — event-driven models.

Covers FlowConfig, GameEntitiesConfig, GameState, GameDefinition, and
the runtime helper types.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from volnix.engines.game.definition import (
    DealDecl,
    FlowConfig,
    GameDefinition,
    GameEntitiesConfig,
    GameResult,
    GameState,
    PlayerBriefDecl,
    PlayerScore,
    TargetTermsDecl,
    WinCondition,
)


class TestFlowConfig:
    """Event-driven flow configuration."""

    def test_defaults(self):
        """FlowConfig() has sensible event-driven defaults."""
        f = FlowConfig()
        assert f.type == "event_driven"
        assert f.max_wall_clock_seconds == 900
        assert f.max_events == 100
        assert f.stalemate_timeout_seconds == 180
        assert f.activation_mode == "serial"
        assert f.first_mover is None
        assert f.bonus_per_event == 0.14

    def test_custom_values_are_preserved(self):
        """Explicit values override defaults."""
        f = FlowConfig(
            max_wall_clock_seconds=600,
            max_events=50,
            stalemate_timeout_seconds=120,
            activation_mode="parallel",
            first_mover="nimbus_buyer",
            bonus_per_event=0.35,
        )
        assert f.max_wall_clock_seconds == 600
        assert f.max_events == 50
        assert f.activation_mode == "parallel"
        assert f.first_mover == "nimbus_buyer"
        assert f.bonus_per_event == 0.35

    def test_positive_validator_rejects_zero(self):
        """max_wall_clock_seconds / max_events / stalemate must be > 0."""
        with pytest.raises(ValidationError):
            FlowConfig(max_events=0)
        with pytest.raises(ValidationError):
            FlowConfig(max_wall_clock_seconds=0)
        with pytest.raises(ValidationError):
            FlowConfig(stalemate_timeout_seconds=0)

    def test_positive_validator_rejects_negative(self):
        """Negative timeouts rejected."""
        with pytest.raises(ValidationError):
            FlowConfig(max_events=-1)

    def test_frozen_model(self):
        """FlowConfig is frozen — mutation rejected."""
        f = FlowConfig()
        with pytest.raises(ValidationError):
            f.max_events = 50  # type: ignore[misc]


class TestGameEntitiesConfig:
    """Blueprint-declared game entities."""

    def test_empty_default(self):
        """GameEntitiesConfig() has empty lists for everything."""
        e = GameEntitiesConfig()
        assert e.deals == []
        assert e.player_briefs == []
        assert e.target_terms == []

    def test_deal_decl_requires_id(self):
        """DealDecl requires an id field."""
        with pytest.raises(ValidationError):
            DealDecl()  # type: ignore[call-arg]

    def test_deal_decl_defaults(self):
        """DealDecl has sensible defaults for non-id fields."""
        d = DealDecl(id="deal-1")
        assert d.status == "open"
        assert d.parties == []
        assert d.terms == {}
        assert d.consent_rule == "unanimous"

    def test_deal_decl_parties_populated(self):
        """DealDecl carries parties + consent_rule forward (P7-ready)."""
        d = DealDecl(
            id="deal-1",
            parties=["nimbus_buyer", "haiphong_supplier"],
            consent_rule="majority",
        )
        assert d.parties == ["nimbus_buyer", "haiphong_supplier"]
        assert d.consent_rule == "majority"

    def test_player_brief_decl_shape(self):
        """PlayerBriefDecl carries brief_content + mission + prohibited_actions."""
        b = PlayerBriefDecl(
            actor_role="dana",
            deal_id="deal-1",
            brief_content="You are Dana.",
            mission="Close the best deal.",
            prohibited_actions=["reveal_batna"],
        )
        assert b.actor_role == "dana"
        assert b.brief_content == "You are Dana."
        assert b.prohibited_actions == ["reveal_batna"]

    def test_target_terms_decl_competitive_fields(self):
        """TargetTermsDecl holds competitive scoring fields."""
        t = TargetTermsDecl(
            actor_role="dana",
            deal_id="deal-1",
            ideal_terms={"price": 25.0},
            term_weights={"price": 0.5},
            term_ranges={"price": [20.0, 30.0]},
            batna_score=30.0,
        )
        assert t.ideal_terms["price"] == 25.0
        assert t.term_ranges["price"] == [20.0, 30.0]
        assert t.batna_score == 30.0


class TestGameDefinition:
    """Top-level game configuration."""

    def test_disabled_by_default(self):
        """GameDefinition() is disabled by default."""
        g = GameDefinition()
        assert g.enabled is False

    def test_behavioral_is_default_scoring_mode(self):
        """scoring_mode defaults to behavioral (not competitive)."""
        g = GameDefinition()
        assert g.scoring_mode == "behavioral"

    def test_flow_default_is_event_driven(self):
        """flow defaults to event_driven with standard timeouts."""
        g = GameDefinition()
        assert g.flow.type == "event_driven"
        assert g.flow.max_events == 100

    def test_entities_empty_by_default(self):
        """entities is an empty GameEntitiesConfig by default."""
        g = GameDefinition()
        assert g.entities.deals == []
        assert g.entities.player_briefs == []

    def test_full_competitive_definition(self):
        """Full event-driven competitive GameDefinition loads from dict."""
        g = GameDefinition(
            enabled=True,
            mode="negotiation",
            scoring_mode="competitive",
            flow=FlowConfig(max_events=40, bonus_per_event=0.35, first_mover="buyer"),
            entities=GameEntitiesConfig(
                deals=[DealDecl(id="deal-q3", parties=["buyer", "supplier"])],
                player_briefs=[
                    PlayerBriefDecl(actor_role="buyer", deal_id="deal-q3", brief_content="..."),
                    PlayerBriefDecl(actor_role="supplier", deal_id="deal-q3", brief_content="..."),
                ],
                target_terms=[
                    TargetTermsDecl(
                        actor_role="buyer",
                        deal_id="deal-q3",
                        ideal_terms={"price": 85.0},
                        term_weights={"price": 0.5},
                        batna_score=40.0,
                    ),
                ],
            ),
            win_conditions=[
                WinCondition(type="deal_closed"),
                WinCondition(type="max_events_exceeded"),
            ],
        )
        assert g.enabled is True
        assert g.scoring_mode == "competitive"
        assert g.flow.first_mover == "buyer"
        assert len(g.entities.deals) == 1
        assert len(g.entities.player_briefs) == 2
        assert len(g.entities.target_terms) == 1
        assert len(g.win_conditions) == 2

    def test_behavioral_definition_no_target_terms(self):
        """Behavioral definitions don't need target_terms (empty list)."""
        g = GameDefinition(
            enabled=True,
            scoring_mode="behavioral",
            entities=GameEntitiesConfig(
                deals=[DealDecl(id="deal-1")],
                player_briefs=[
                    PlayerBriefDecl(actor_role="a", deal_id="deal-1", brief_content="x"),
                    PlayerBriefDecl(actor_role="b", deal_id="deal-1", brief_content="y"),
                ],
                # target_terms empty — behavioral mode
            ),
        )
        assert g.scoring_mode == "behavioral"
        assert g.entities.target_terms == []


class TestGameState:
    """Mutable game lifecycle state."""

    def test_defaults(self):
        """GameState starts at zero, not terminated."""
        s = GameState()
        assert s.event_counter == 0
        assert s.started_at is None
        assert s.terminated is False
        assert s.stalemate_deadline_tick == 0.0

    def test_mutation_allowed(self):
        """GameState is mutable (not frozen)."""
        s = GameState()
        s.event_counter = 5
        s.terminated = True
        s.started_at = datetime.now(UTC)
        assert s.event_counter == 5
        assert s.terminated is True
        assert s.started_at is not None


class TestPlayerScoreWithBehaviorMetrics:
    """PlayerScore now carries behavior_metrics alongside competitive metrics."""

    def test_behavior_metrics_default_empty(self):
        """behavior_metrics defaults to empty dict."""
        ps = PlayerScore(actor_id="a")
        assert ps.behavior_metrics == {}

    def test_behavior_metrics_writable(self):
        """behavior_metrics can be populated directly."""
        ps = PlayerScore(actor_id="a")
        ps.behavior_metrics = {"query_quality": 85.0, "reactivity": 0.9}
        assert ps.behavior_metrics["query_quality"] == 85.0

    def test_update_metrics_still_works(self):
        """Existing update_metrics weighted sum still computes correctly."""
        ps = PlayerScore(actor_id="a")
        ps.update_metrics({"score": 50.0}, {"score": 1.5})
        assert ps.total_score == 75.0


class TestGameResult:
    """Final GameResult with behavioral + competitive fields."""

    def test_behavioral_result_shape(self):
        """Behavioral result: winner=None, behavior_scores populated."""
        r = GameResult(
            winner=None,
            reason="deal_closed",
            total_events=12,
            scoring_mode="behavioral",
            behavior_scores={"dana": {"query_quality": 85.0}},
        )
        assert r.winner is None
        assert r.behavior_scores["dana"]["query_quality"] == 85.0
        assert r.scoring_mode == "behavioral"
        assert r.total_events == 12

    def test_competitive_result_shape(self):
        """Competitive result: winner set, final_standings ordered."""
        r = GameResult(
            winner="buyer-001",
            reason="deal_closed",
            total_events=8,
            scoring_mode="competitive",
            final_standings=[
                {"actor_id": "buyer-001", "total_score": 95.0},
                {"actor_id": "supplier-002", "total_score": 85.0},
            ],
        )
        assert r.winner == "buyer-001"
        assert r.final_standings[0]["actor_id"] == "buyer-001"
        assert r.scoring_mode == "competitive"


class TestNoLegacyLeakage:
    """Legacy round-based types must not reappear in the definition module."""

    def test_round_types_are_not_importable(self):
        """RoundConfig/RoundState/BetweenRoundsConfig/ResourceReset are gone."""
        import volnix.engines.game.definition as d

        assert not hasattr(d, "RoundConfig")
        assert not hasattr(d, "RoundState")
        assert not hasattr(d, "BetweenRoundsConfig")
        assert not hasattr(d, "ResourceReset")

    def test_game_definition_has_no_legacy_fields(self):
        """GameDefinition no longer carries rounds/turn_protocol/between_rounds."""
        g = GameDefinition()
        assert not hasattr(g, "rounds")
        assert not hasattr(g, "turn_protocol")
        assert not hasattr(g, "between_rounds")
        assert not hasattr(g, "resource_reset_per_round")

    def test_player_score_has_no_elimination_round(self):
        """PlayerScore.elimination_round is gone; only eliminated_at_event remains."""
        ps = PlayerScore(actor_id="a-001")
        assert not hasattr(ps, "elimination_round")
        assert hasattr(ps, "eliminated_at_event")
