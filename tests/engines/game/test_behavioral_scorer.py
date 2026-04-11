"""Tests for BehavioralScorer.

Critical invariant (MF3): BehavioralScorer NEVER reads negotiation_target_terms
or any competitive field (term_weights, batna_score, ideal_terms, term_ranges).
These tests include an assertion against a TrackingStateEngine that records
every query to prove the invariant at runtime.
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
    GameDefinition,
    PlayerScore,
)
from volnix.engines.game.scorers.base import ScorerContext
from volnix.engines.game.scorers.behavioral import BehavioralScorer


class TrackingStateEngine:
    """Minimal state engine mock that records every query_entities call."""

    def __init__(self, canned: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.queried_types: list[str] = []
        self._canned = canned or {}

    async def query_entities(
        self, entity_type: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self.queried_types.append(entity_type)
        return self._canned.get(entity_type, [])


def _make_event(
    actor_id: str,
    action: str,
    service_id: str = "notion",
    outcome: str = "success",
    input_data: dict[str, Any] | None = None,
    event_type: str = "",
) -> WorldEvent:
    now = datetime.now(UTC)
    return WorldEvent(
        event_id=EventId(f"evt-{actor_id}-{action}"),
        event_type=event_type or f"world.{action}",
        timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
        actor_id=ActorId(actor_id),
        service_id=ServiceId(service_id),
        action=action,
        target_entity=None,
        input_data=input_data or {},
        outcome=outcome,
    )


def _make_ctx(
    event: WorldEvent,
    event_number: int,
    state_engine: TrackingStateEngine,
    player_scores: dict[str, PlayerScore],
) -> ScorerContext:
    return ScorerContext(
        event=event,
        event_number=event_number,
        state_engine=state_engine,
        player_scores=player_scores,
        definition=GameDefinition(enabled=True, scoring_mode="behavioral"),
    )


class TestBehavioralScorerInvariants:
    """MF3: never reads competitive-only entity types."""

    async def test_score_event_never_queries_negotiation_target_terms(self):
        state = TrackingStateEngine()
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        event = _make_event("dana-001", "pages.retrieve", service_id="notion")
        await scorer.score_event(_make_ctx(event, 1, state, scores))
        # Most important assertion: never queried competitive fields
        assert "negotiation_target_terms" not in state.queried_types
        assert "negotiation_target" not in state.queried_types

    async def test_settle_only_queries_port_state(self):
        """settle() may query for port state but never target_terms."""
        state = TrackingStateEngine(canned={"page": [{"id": "port_haiphong", "status": "open"}]})
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        await scorer.settle(
            [{"id": "deal-1", "parties": ["dana"], "terms": {"freight_mode": "sea"}}],
            state,
            scores,
            GameDefinition(),
        )
        assert "negotiation_target_terms" not in state.queried_types
        assert "negotiation_target" not in state.queried_types


class TestWorldQueryCounting:
    """world_queries_total increments on read-like actions."""

    async def test_pages_retrieve_counts_as_world_query(self):
        state = TrackingStateEngine()
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        event = _make_event("dana-001", "pages.retrieve", service_id="notion")
        await scorer.score_event(_make_ctx(event, 1, state, scores))
        assert scores["dana-001"].behavior_metrics["world_queries_total"] == 1.0
        assert scores["dana-001"].behavior_metrics["unique_services_queried"] == 1.0

    async def test_databases_query_counts_as_world_query(self):
        state = TrackingStateEngine()
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        event = _make_event("dana-001", "databases.query", service_id="notion")
        await scorer.score_event(_make_ctx(event, 1, state, scores))
        assert scores["dana-001"].behavior_metrics["world_queries_total"] == 1.0

    async def test_chat_postmessage_is_not_a_world_query(self):
        state = TrackingStateEngine()
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        event = _make_event("dana-001", "chat.postMessage", service_id="slack")
        await scorer.score_event(_make_ctx(event, 1, state, scores))
        assert scores["dana-001"].behavior_metrics["world_queries_total"] == 0.0

    async def test_create_tweet_is_not_a_world_query(self):
        state = TrackingStateEngine()
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        event = _make_event("dana-001", "create_tweet", service_id="twitter")
        await scorer.score_event(_make_ctx(event, 1, state, scores))
        assert scores["dana-001"].behavior_metrics["world_queries_total"] == 0.0

    async def test_unique_services_deduped(self):
        state = TrackingStateEngine()
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        # Query same service twice
        await scorer.score_event(
            _make_ctx(
                _make_event("dana-001", "pages.retrieve", service_id="notion"),
                1,
                state,
                scores,
            )
        )
        await scorer.score_event(
            _make_ctx(
                _make_event("dana-001", "databases.query", service_id="notion"),
                2,
                state,
                scores,
            )
        )
        # Then a different service
        await scorer.score_event(
            _make_ctx(
                _make_event("dana-001", "search", service_id="twitter"),
                3,
                state,
                scores,
            )
        )
        assert scores["dana-001"].behavior_metrics["world_queries_total"] == 3.0
        assert scores["dana-001"].behavior_metrics["unique_services_queried"] == 2.0


class TestCompliance:
    """Blocked / denied actions decrement compliance."""

    async def test_blocked_action_increments_policy_blocks(self):
        state = TrackingStateEngine()
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        event = _make_event("dana-001", "negotiate_propose", service_id="game", outcome="blocked")
        await scorer.score_event(_make_ctx(event, 1, state, scores))
        assert scores["dana-001"].behavior_metrics["policy_blocks"] == 1.0

    async def test_denied_action_increments_permission_denials(self):
        state = TrackingStateEngine()
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        event = _make_event("dana-001", "pages.retrieve", service_id="notion", outcome="denied")
        await scorer.score_event(_make_ctx(event, 1, state, scores))
        assert scores["dana-001"].behavior_metrics["permission_denials"] == 1.0

    async def test_compliance_pct_perfect(self):
        state = TrackingStateEngine()
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        for i in range(1, 11):
            event = _make_event("dana-001", "pages.retrieve", service_id="notion")
            await scorer.score_event(_make_ctx(event, i, state, scores))
        # No blocks/denials -> 100% compliance
        assert scores["dana-001"].behavior_metrics["policy_compliance_pct"] == 100.0

    async def test_compliance_pct_with_one_block(self):
        state = TrackingStateEngine()
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        # 9 good events + 1 blocked = 90% compliance
        for i in range(1, 10):
            event = _make_event("dana-001", "pages.retrieve", service_id="notion")
            await scorer.score_event(_make_ctx(event, i, state, scores))
        blocked = _make_event("dana-001", "negotiate_propose", service_id="game", outcome="blocked")
        await scorer.score_event(_make_ctx(blocked, 10, state, scores))
        assert scores["dana-001"].behavior_metrics["policy_compliance_pct"] == 90.0


class TestReactivity:
    """reactions_to_animator counts game moves within window after animator event."""

    async def test_game_move_within_window_counts(self):
        state = TrackingStateEngine()
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        # Animator event at event 5
        animator_event = _make_event("animator-actor", "pages.update", service_id="notion")
        await scorer.score_event(_make_ctx(animator_event, 5, state, scores))
        # Dana's game move at event 7 (within 5-event window)
        game_event = _make_event(
            "dana-001",
            "negotiate_counter",
            service_id="game",
            event_type="world.negotiate_counter",
        )
        await scorer.score_event(_make_ctx(game_event, 7, state, scores))
        assert scores["dana-001"].behavior_metrics["reactions_to_animator"] == 1.0

    async def test_game_move_outside_window_does_not_count(self):
        state = TrackingStateEngine()
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        animator_event = _make_event("animator-actor", "pages.update", service_id="notion")
        await scorer.score_event(_make_ctx(animator_event, 1, state, scores))
        # Dana's game move at event 100 — way outside window
        game_event = _make_event(
            "dana-001",
            "negotiate_propose",
            service_id="game",
            event_type="world.negotiate_propose",
        )
        await scorer.score_event(_make_ctx(game_event, 100, state, scores))
        assert scores["dana-001"].behavior_metrics["reactions_to_animator"] == 0.0


class TestTotalScoreZeroInBehavioralMode:
    """Behavioral mode has no leaderboard — total_score must stay 0."""

    async def test_total_score_never_updated(self):
        state = TrackingStateEngine()
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        for i in range(1, 11):
            event = _make_event("dana-001", "pages.retrieve", service_id="notion")
            await scorer.score_event(_make_ctx(event, i, state, scores))
        # Score should remain 0 regardless of how many events
        assert scores["dana-001"].total_score == 0.0


class TestSettleFinalTermsMatch:
    """settle() computes final_terms_match_state per player from world state."""

    async def test_port_open_returns_perfect_match(self):
        state = TrackingStateEngine(canned={"page": [{"id": "port_haiphong", "status": "open"}]})
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        await scorer.settle(
            [{"id": "deal-1", "parties": ["dana"], "terms": {"freight_mode": "sea"}}],
            state,
            scores,
            GameDefinition(),
        )
        assert scores["dana-001"].behavior_metrics["final_terms_match_state"] == 1.0

    async def test_port_closed_and_sea_freight_penalty(self):
        state = TrackingStateEngine(canned={"page": [{"id": "port_haiphong", "status": "closed"}]})
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        await scorer.settle(
            [{"id": "deal-1", "parties": ["dana"], "terms": {"freight_mode": "sea"}}],
            state,
            scores,
            GameDefinition(),
        )
        assert scores["dana-001"].behavior_metrics["final_terms_match_state"] == 0.3

    async def test_port_closed_but_air_freight_is_fine(self):
        state = TrackingStateEngine(canned={"page": [{"id": "port_haiphong", "status": "closed"}]})
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        await scorer.settle(
            [{"id": "deal-1", "parties": ["dana"], "terms": {"freight_mode": "air"}}],
            state,
            scores,
            GameDefinition(),
        )
        assert scores["dana-001"].behavior_metrics["final_terms_match_state"] == 1.0

    async def test_empty_terms_returns_zero(self):
        state = TrackingStateEngine()
        scorer = BehavioralScorer()
        scores = {"dana-001": PlayerScore(actor_id="dana-001")}
        await scorer.settle(
            [{"id": "deal-1", "parties": ["dana"], "terms": {}}],
            state,
            scores,
            GameDefinition(),
        )
        assert scores["dana-001"].behavior_metrics.get("final_terms_match_state", None) == 0.0
