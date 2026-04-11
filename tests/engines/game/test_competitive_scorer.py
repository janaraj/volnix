"""Tests for CompetitiveScorer.

Covers:
- _compute_deal_score algorithm (exact match, edge of range, weighted)
- score_event on negotiate_accept with efficiency_bonus
- efficiency_bonus is event-count based (MF4)
- score_event on negotiate_reject (BATNA applied)
- settle on open deals (BATNA applied to non-closers)
- _resolve_player_by_role
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from volnix.core.events import WorldEvent
from volnix.core.types import (
    ActorId,
    EventId,
    ServiceId,
    Timestamp,
)
from volnix.engines.game.definition import (
    FlowConfig,
    GameDefinition,
    PlayerScore,
)
from volnix.engines.game.scorers.base import ScorerContext
from volnix.engines.game.scorers.competitive import CompetitiveScorer


class CannedStateEngine:
    def __init__(self, canned: dict[str, list[dict[str, Any]]]) -> None:
        self._canned = canned

    async def query_entities(
        self, entity_type: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        result = self._canned.get(entity_type, [])
        if filters:

            def matches(row: dict[str, Any]) -> bool:
                for k, v in filters.items():
                    if row.get(k) != v:
                        return False
                return True

            result = [r for r in result if matches(r)]
        return result


def _make_event(
    actor_id: str, action: str, deal_id: str = "deal-q3", input_data: dict[str, Any] | None = None
) -> WorldEvent:
    now = datetime.now(UTC)
    return WorldEvent(
        event_id=EventId(f"evt-{actor_id}-{action}"),
        event_type=f"world.{action}",
        timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
        actor_id=ActorId(actor_id),
        service_id=ServiceId("game"),
        action=action,
        input_data=input_data or {"deal_id": deal_id},
    )


def _make_ctx(
    event: WorldEvent,
    event_number: int,
    state_engine: Any,
    player_scores: dict[str, PlayerScore],
    max_events: int = 100,
) -> ScorerContext:
    return ScorerContext(
        event=event,
        event_number=event_number,
        state_engine=state_engine,
        player_scores=player_scores,
        definition=GameDefinition(
            enabled=True,
            scoring_mode="competitive",
            flow=FlowConfig(max_events=max_events, bonus_per_event=0.14),
        ),
    )


class TestComputeDealScore:
    """The _compute_deal_score static method — pure algorithm."""

    def test_exact_match_returns_100(self):
        actual = {"price": 85}
        target = {
            "ideal_terms": {"price": 85},
            "term_weights": {"price": 1.0},
            "term_ranges": {"price": [80, 120]},
        }
        score = CompetitiveScorer._compute_deal_score(actual, target)
        assert score == 100.0

    def test_edge_of_range_near_zero(self):
        actual = {"price": 120}
        target = {
            "ideal_terms": {"price": 80},
            "term_weights": {"price": 1.0},
            "term_ranges": {"price": [80, 120]},
        }
        score = CompetitiveScorer._compute_deal_score(actual, target)
        assert score == 0.0  # max distance

    def test_mid_range_partial_score(self):
        actual = {"price": 100}
        target = {
            "ideal_terms": {"price": 80},
            "term_weights": {"price": 1.0},
            "term_ranges": {"price": [80, 120]},
        }
        score = CompetitiveScorer._compute_deal_score(actual, target)
        # distance = 20/40 = 0.5, score = (1 - 0.5) * 100 = 50
        assert score == 50.0

    def test_weighted_multi_term(self):
        actual = {"price": 85, "delivery_weeks": 4}
        target = {
            "ideal_terms": {"price": 85, "delivery_weeks": 3},
            "term_weights": {"price": 0.75, "delivery_weeks": 0.25},
            "term_ranges": {"price": [80, 120], "delivery_weeks": [2, 8]},
        }
        score = CompetitiveScorer._compute_deal_score(actual, target)
        # price: 100 (exact match) * 0.75 = 75
        # delivery: (1 - 1/6) * 100 = 83.33 * 0.25 = 20.83
        # weighted avg: (75 + 20.83) / 1.0 = 95.83
        assert 95.0 < score < 96.0

    def test_zero_span_exact_match(self):
        actual = {"price": 100}
        target = {
            "ideal_terms": {"price": 100},
            "term_weights": {"price": 1.0},
            "term_ranges": {"price": [100, 100]},  # zero span
        }
        score = CompetitiveScorer._compute_deal_score(actual, target)
        assert score == 100.0

    def test_zero_span_non_match(self):
        actual = {"price": 90}
        target = {
            "ideal_terms": {"price": 100},
            "term_weights": {"price": 1.0},
            "term_ranges": {"price": [100, 100]},
        }
        score = CompetitiveScorer._compute_deal_score(actual, target)
        assert score == 0.0

    def test_missing_actual_term_skipped(self):
        actual = {"price": 85}  # delivery_weeks missing
        target = {
            "ideal_terms": {"price": 85, "delivery_weeks": 3},
            "term_weights": {"price": 1.0, "delivery_weeks": 1.0},
            "term_ranges": {"price": [80, 120], "delivery_weeks": [2, 8]},
        }
        score = CompetitiveScorer._compute_deal_score(actual, target)
        # Only price counted, which is perfect
        assert score == 100.0

    def test_empty_target_returns_zero(self):
        actual = {"price": 85}
        target: dict[str, Any] = {}
        score = CompetitiveScorer._compute_deal_score(actual, target)
        assert score == 0.0


class TestEfficiencyBonusEventCount:
    """MF4: efficiency_bonus is event-count based, not wall-clock."""

    async def test_accept_at_event_1_gives_near_max_bonus(self):
        """With max_events=100, bonus_per_event=0.14: accepting at event 1
        gives bonus = (100 - 1) * 0.14 = 13.86.
        """
        state = CannedStateEngine(
            {
                "negotiation_deal": [
                    {
                        "id": "deal-q3",
                        "status": "accepted",
                        "terms": {"price": 85},
                        "parties": ["buyer", "supplier"],
                    }
                ],
                "negotiation_target_terms": [
                    {
                        "actor_role": "buyer",
                        "deal_id": "deal-q3",
                        "ideal_terms": {"price": 85},
                        "term_weights": {"price": 1.0},
                        "term_ranges": {"price": [80, 120]},
                        "batna_score": 40.0,
                    },
                ],
            }
        )
        scorer = CompetitiveScorer(bonus_per_event=0.14)
        scores = {"buyer-001": PlayerScore(actor_id="buyer-001")}
        ctx = _make_ctx(
            _make_event("buyer-001", "negotiate_accept"), 1, state, scores, max_events=100
        )
        await scorer.score_event(ctx)
        assert scores["buyer-001"].metrics["efficiency_bonus"] == 99 * 0.14
        assert scores["buyer-001"].metrics["deal_score"] == 100.0
        assert scores["buyer-001"].metrics["total_points"] == 100.0 + 99 * 0.14

    async def test_accept_at_event_99_gives_near_zero_bonus(self):
        """Accepting at event 99 of 100 gives bonus = 1 * 0.14 = 0.14."""
        state = CannedStateEngine(
            {
                "negotiation_deal": [
                    {
                        "id": "deal-q3",
                        "status": "accepted",
                        "terms": {"price": 85},
                        "parties": ["buyer"],
                    }
                ],
                "negotiation_target_terms": [
                    {
                        "actor_role": "buyer",
                        "deal_id": "deal-q3",
                        "ideal_terms": {"price": 85},
                        "term_weights": {"price": 1.0},
                        "term_ranges": {"price": [80, 120]},
                    },
                ],
            }
        )
        scorer = CompetitiveScorer(bonus_per_event=0.14)
        scores = {"buyer-001": PlayerScore(actor_id="buyer-001")}
        ctx = _make_ctx(
            _make_event("buyer-001", "negotiate_accept"), 99, state, scores, max_events=100
        )
        await scorer.score_event(ctx)
        assert abs(scores["buyer-001"].metrics["efficiency_bonus"] - 1 * 0.14) < 1e-9

    async def test_accept_past_max_events_gives_zero_bonus(self):
        """Accepting after max_events still gives score, just zero bonus."""
        state = CannedStateEngine(
            {
                "negotiation_deal": [
                    {
                        "id": "deal-q3",
                        "status": "accepted",
                        "terms": {"price": 85},
                        "parties": ["buyer"],
                    }
                ],
                "negotiation_target_terms": [
                    {
                        "actor_role": "buyer",
                        "deal_id": "deal-q3",
                        "ideal_terms": {"price": 85},
                        "term_weights": {"price": 1.0},
                        "term_ranges": {"price": [80, 120]},
                    },
                ],
            }
        )
        scorer = CompetitiveScorer(bonus_per_event=0.14)
        scores = {"buyer-001": PlayerScore(actor_id="buyer-001")}
        ctx = _make_ctx(
            _make_event("buyer-001", "negotiate_accept"),
            150,
            state,
            scores,
            max_events=100,
        )
        await scorer.score_event(ctx)
        assert scores["buyer-001"].metrics["efficiency_bonus"] == 0.0
        assert scores["buyer-001"].metrics["deal_score"] == 100.0


class TestScoreEventBranching:
    """score_event routes by action type."""

    async def test_propose_does_not_score(self):
        state = CannedStateEngine({})
        scorer = CompetitiveScorer()
        scores = {"buyer-001": PlayerScore(actor_id="buyer-001")}
        ctx = _make_ctx(_make_event("buyer-001", "negotiate_propose"), 1, state, scores)
        await scorer.score_event(ctx)
        assert scores["buyer-001"].total_score == 0.0

    async def test_counter_does_not_score(self):
        state = CannedStateEngine({})
        scorer = CompetitiveScorer()
        scores = {"buyer-001": PlayerScore(actor_id="buyer-001")}
        ctx = _make_ctx(_make_event("buyer-001", "negotiate_counter"), 1, state, scores)
        await scorer.score_event(ctx)
        assert scores["buyer-001"].total_score == 0.0

    async def test_reject_applies_batna(self):
        state = CannedStateEngine(
            {
                "negotiation_target_terms": [
                    {
                        "actor_role": "buyer",
                        "deal_id": "deal-q3",
                        "batna_score": 45.0,
                    },
                ],
            }
        )
        scorer = CompetitiveScorer()
        scores = {"buyer-001": PlayerScore(actor_id="buyer-001")}
        ctx = _make_ctx(_make_event("buyer-001", "negotiate_reject"), 5, state, scores)
        await scorer.score_event(ctx)
        assert scores["buyer-001"].metrics["total_points"] == 45.0
        assert scores["buyer-001"].metrics["batna_applied"] == 1.0


class TestSettleBATNA:
    """settle() applies BATNA to any party whose deal didn't close."""

    async def test_settle_applies_batna_to_both_parties(self):
        state = CannedStateEngine(
            {
                "negotiation_target_terms": [
                    {
                        "actor_role": "buyer",
                        "deal_id": "deal-q3",
                        "batna_score": 45.0,
                    },
                    {
                        "actor_role": "supplier",
                        "deal_id": "deal-q3",
                        "batna_score": 35.0,
                    },
                ],
            }
        )
        scorer = CompetitiveScorer()
        scores = {
            "buyer-001": PlayerScore(actor_id="buyer-001"),
            "supplier-002": PlayerScore(actor_id="supplier-002"),
        }
        await scorer.settle(
            [{"id": "deal-q3", "parties": ["buyer", "supplier"]}],
            state,
            scores,
            GameDefinition(),
        )
        assert scores["buyer-001"].metrics["total_points"] == 45.0
        assert scores["supplier-002"].metrics["total_points"] == 35.0
        assert scores["buyer-001"].metrics["batna_applied"] == 1.0
        assert scores["supplier-002"].metrics["batna_applied"] == 1.0

    async def test_settle_skips_player_who_already_closed(self):
        state = CannedStateEngine(
            {
                "negotiation_target_terms": [
                    {
                        "actor_role": "buyer",
                        "deal_id": "deal-q3",
                        "batna_score": 45.0,
                    },
                ],
            }
        )
        scorer = CompetitiveScorer()
        buyer_ps = PlayerScore(actor_id="buyer-001")
        buyer_ps.metrics["deals_closed"] = 1.0
        buyer_ps.metrics["total_points"] = 92.0
        buyer_ps.total_score = 92.0
        scores = {"buyer-001": buyer_ps}
        await scorer.settle(
            [{"id": "deal-q3", "parties": ["buyer"]}],
            state,
            scores,
            GameDefinition(),
        )
        # total_points NOT overwritten
        assert scores["buyer-001"].metrics["total_points"] == 92.0


class TestResolvePlayerByRole:
    """Player resolution by role prefix."""

    def test_matches_role_prefix(self):
        scores = {
            "buyer-001": PlayerScore(actor_id="buyer-001"),
            "supplier-002": PlayerScore(actor_id="supplier-002"),
        }
        result = CompetitiveScorer._resolve_player_by_role("buyer", scores)
        assert result == "buyer-001"

    def test_no_match_returns_none(self):
        scores = {"buyer-001": PlayerScore(actor_id="buyer-001")}
        result = CompetitiveScorer._resolve_player_by_role("unknown", scores)
        assert result is None

    def test_role_without_dash_suffix_not_matched(self):
        """Avoid false positive: 'buyer' alone is not a prefix of 'buyer-xxx'
        unless we match the exact role-dash prefix."""
        scores = {"buyer_v2-001": PlayerScore(actor_id="buyer_v2-001")}
        result = CompetitiveScorer._resolve_player_by_role("buyer", scores)
        assert result is None
