"""Tests for GameScorer."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from volnix.engines.game.definition import ScoringConfig, ScoringMetric
from volnix.engines.game.scorer import GameScorer


def _make_event(event_type: str, actor_id: str, **input_data) -> SimpleNamespace:
    """Build a lightweight event-like object for testing."""
    return SimpleNamespace(
        event_type=event_type,
        actor_id=actor_id,
        input_data=dict(input_data),
    )


class TestStateMetrics:
    async def test_from_state_none_engine_returns_zero(self):
        """state source with None state_engine returns 0."""
        config = ScoringConfig(
            metrics=[
                ScoringMetric(name="value", source="state", entity_type="account", field="equity"),
            ],
        )
        scorer = GameScorer(config)
        scores = await scorer.compute_scores(["p1"], None, [])
        assert scores["p1"]["value"] == 0.0

    async def test_from_state_query_failure_returns_zero(self):
        """state source that raises returns 0."""
        mock_state = AsyncMock()
        mock_state.query_entities = AsyncMock(side_effect=RuntimeError("db error"))
        config = ScoringConfig(
            metrics=[
                ScoringMetric(name="value", source="state", entity_type="account", field="equity"),
            ],
        )
        scorer = GameScorer(config)
        scores = await scorer.compute_scores(["p1"], mock_state, [])
        assert scores["p1"]["value"] == 0.0

    async def test_from_state_entity_found(self):
        """state source finds entity and extracts field."""
        mock_state = AsyncMock()
        mock_state.query_entities = AsyncMock(return_value=[{"id": "p1", "equity": 150000.0}])
        config = ScoringConfig(
            metrics=[
                ScoringMetric(name="value", source="state", entity_type="account", field="equity"),
            ],
        )
        scorer = GameScorer(config)
        scores = await scorer.compute_scores(["p1"], mock_state, [])
        assert scores["p1"]["value"] == 150000.0


class TestEventAggregations:
    async def test_event_count_aggregation(self):
        config = ScoringConfig(
            metrics=[
                ScoringMetric(
                    name="actions",
                    source="events",
                    event_type="world.email_send",
                    aggregation="count",
                ),
            ],
        )
        scorer = GameScorer(config)

        events = [
            _make_event("world.email_send", "p1"),
            _make_event("world.email_send", "p1"),
            _make_event("world.email_send", "p2"),
        ]

        result = await scorer.compute_scores(["p1", "p2"], None, events)

        assert result["p1"]["actions"] == 2.0
        assert result["p2"]["actions"] == 1.0

    async def test_event_sum_aggregation(self):
        config = ScoringConfig(
            metrics=[
                ScoringMetric(
                    name="spent",
                    source="events",
                    event_type="world.payment",
                    aggregation="sum",
                ),
            ],
        )
        scorer = GameScorer(config)

        events = [
            _make_event("world.payment", "p1", amount=100),
            _make_event("world.payment", "p1", amount=50),
            _make_event("world.payment", "p2", amount=200),
        ]

        result = await scorer.compute_scores(["p1", "p2"], None, events)

        assert result["p1"]["spent"] == 150.0
        assert result["p2"]["spent"] == 200.0

    async def test_empty_events_returns_zero(self):
        config = ScoringConfig(
            metrics=[
                ScoringMetric(
                    name="actions",
                    source="events",
                    event_type="world.email_send",
                    aggregation="count",
                ),
            ],
        )
        scorer = GameScorer(config)

        result = await scorer.compute_scores(["p1"], None, [])

        assert result["p1"]["actions"] == 0.0

    async def test_max_aggregation(self):
        """events source with max aggregation."""
        events = [
            _make_event("trade", "p1", amount=100),
            _make_event("trade", "p1", amount=500),
            _make_event("trade", "p1", amount=200),
        ]
        config = ScoringConfig(
            metrics=[
                ScoringMetric(
                    name="max_trade",
                    source="events",
                    event_type="trade",
                    field="amount",
                    aggregation="max",
                ),
            ],
        )
        scorer = GameScorer(config)
        scores = await scorer.compute_scores(["p1"], None, events)
        assert scores["p1"]["max_trade"] == 500.0

    async def test_min_aggregation(self):
        events = [
            _make_event("trade", "p1", amount=100),
            _make_event("trade", "p1", amount=500),
        ]
        config = ScoringConfig(
            metrics=[
                ScoringMetric(
                    name="min_trade",
                    source="events",
                    event_type="trade",
                    field="amount",
                    aggregation="min",
                ),
            ],
        )
        scorer = GameScorer(config)
        scores = await scorer.compute_scores(["p1"], None, events)
        assert scores["p1"]["min_trade"] == 100.0

    async def test_last_aggregation(self):
        events = [
            _make_event("trade", "p1", price=50),
            _make_event("trade", "p1", price=75),
        ]
        config = ScoringConfig(
            metrics=[
                ScoringMetric(
                    name="last_price",
                    source="events",
                    event_type="trade",
                    field="price",
                    aggregation="last",
                ),
            ],
        )
        scorer = GameScorer(config)
        scores = await scorer.compute_scores(["p1"], None, events)
        assert scores["p1"]["last_price"] == 75.0

    async def test_max_empty_matching_returns_zero(self):
        config = ScoringConfig(
            metrics=[
                ScoringMetric(
                    name="max_trade",
                    source="events",
                    event_type="trade",
                    field="amount",
                    aggregation="max",
                ),
            ],
        )
        scorer = GameScorer(config)
        scores = await scorer.compute_scores(["p1"], None, [])
        assert scores["p1"]["max_trade"] == 0.0


class TestBudgetMetrics:
    async def test_from_budget_returns_zero(self):
        """Budget source stub returns 0."""
        config = ScoringConfig(
            metrics=[
                ScoringMetric(name="spend", source="budget"),
            ],
        )
        scorer = GameScorer(config)
        scores = await scorer.compute_scores(["p1"], None, [])
        assert scores["p1"]["spend"] == 0.0


class TestGameOwnerIdScoring:
    async def test_from_state_with_game_owner_id(self):
        """Entities with game_owner_id are matched to the correct player."""
        mock_state = AsyncMock()
        mock_state.query_entities = AsyncMock(
            return_value=[
                {"id": "acct_01", "equity": 150000.0, "game_owner_id": "p1"},
                {"id": "acct_02", "equity": 100000.0, "game_owner_id": "p2"},
                {"id": "acct_03", "equity": 100000.0},  # no owner — ignored
            ]
        )
        config = ScoringConfig(
            metrics=[
                ScoringMetric(
                    name="value", source="state", entity_type="account", field="equity"
                ),
            ],
        )
        scorer = GameScorer(config)
        scores = await scorer.compute_scores(["p1", "p2"], mock_state, [])
        assert scores["p1"]["value"] == 150000.0
        assert scores["p2"]["value"] == 100000.0

    async def test_fallback_to_id_matching(self):
        """Without game_owner_id, falls back to id/owner_id matching."""
        mock_state = AsyncMock()
        mock_state.query_entities = AsyncMock(
            return_value=[{"id": "p1", "equity": 50000.0}]
        )
        config = ScoringConfig(
            metrics=[
                ScoringMetric(
                    name="value", source="state", entity_type="account", field="equity"
                ),
            ],
        )
        scorer = GameScorer(config)
        scores = await scorer.compute_scores(["p1"], mock_state, [])
        assert scores["p1"]["value"] == 50000.0

    async def test_zero_entities_returns_zero(self):
        """0 entities for a metric type returns 0."""
        mock_state = AsyncMock()
        mock_state.query_entities = AsyncMock(return_value=[])
        config = ScoringConfig(
            metrics=[
                ScoringMetric(
                    name="value",
                    source="state",
                    entity_type="missing_type",
                    field="equity",
                ),
            ],
        )
        scorer = GameScorer(config)
        scores = await scorer.compute_scores(["p1"], mock_state, [])
        assert scores["p1"]["value"] == 0.0

    async def test_resolved_entity_type(self):
        """resolved_entity_types remaps metric entity_type for query."""
        mock_state = AsyncMock()
        mock_state.query_entities = AsyncMock(
            return_value=[
                {"id": "acct_01", "equity": 200000.0, "game_owner_id": "p1"},
            ]
        )
        config = ScoringConfig(
            metrics=[
                ScoringMetric(
                    name="value", source="state", entity_type="account", field="equity"
                ),
            ],
        )
        scorer = GameScorer(config)
        scores = await scorer.compute_scores(
            ["p1"], mock_state, [],
            resolved_entity_types={"account": "alpaca_account"},
        )
        assert scores["p1"]["value"] == 200000.0
        # Verify query used resolved type
        mock_state.query_entities.assert_called_with(entity_type="alpaca_account")


class TestWeights:
    def test_weights_property(self):
        config = ScoringConfig(
            metrics=[
                ScoringMetric(name="speed", weight=2.0),
                ScoringMetric(name="accuracy", weight=3.0),
            ],
        )
        scorer = GameScorer(config)

        assert scorer.weights == {"speed": 2.0, "accuracy": 3.0}


# ---------------------------------------------------------------------------
# Registry + extensibility tests
# ---------------------------------------------------------------------------

from volnix.engines.game.protocols import ScoringContext
from volnix.engines.game.scorer import (
    SCORING_PROVIDER_REGISTRY,
    BudgetScoringProvider,
    EventsScoringProvider,
    StateScoringProvider,
)


class TestScoringProviderRegistry:
    def test_registry_contains_built_in_providers(self):
        assert "state" in SCORING_PROVIDER_REGISTRY
        assert "events" in SCORING_PROVIDER_REGISTRY
        assert "budget" in SCORING_PROVIDER_REGISTRY
        assert SCORING_PROVIDER_REGISTRY["state"] is StateScoringProvider
        assert SCORING_PROVIDER_REGISTRY["events"] is EventsScoringProvider
        assert SCORING_PROVIDER_REGISTRY["budget"] is BudgetScoringProvider

    def test_default_scorer_uses_registry(self):
        config = ScoringConfig(metrics=[])
        scorer = GameScorer(config)
        assert "state" in scorer._providers
        assert "events" in scorer._providers
        assert "budget" in scorer._providers

    async def test_unknown_source_returns_zero_with_warning(self, caplog):
        config = ScoringConfig(
            metrics=[ScoringMetric(name="mystery", source="unknown_source")],
        )
        scorer = GameScorer(config)
        import logging

        with caplog.at_level(logging.WARNING):
            scores = await scorer.compute_scores(["p1"], None, [])
        assert scores["p1"]["mystery"] == 0.0
        assert "No scoring provider registered for source 'unknown_source'" in caplog.text


class TestCustomScoringProvider:
    async def test_custom_provider_via_constructor(self):
        class FixedProvider:
            async def compute(self, ctx: ScoringContext) -> float:
                return 42.0

        config = ScoringConfig(
            metrics=[ScoringMetric(name="fixed", source="custom_src")],
        )
        scorer = GameScorer(config, providers={"custom_src": FixedProvider()})
        scores = await scorer.compute_scores(["p1"], None, [])
        assert scores["p1"]["fixed"] == 42.0

    async def test_register_provider_at_runtime(self):
        class LateProvider:
            async def compute(self, ctx: ScoringContext) -> float:
                return 99.0

        config = ScoringConfig(
            metrics=[ScoringMetric(name="late", source="late_src")],
        )
        scorer = GameScorer(config)
        scores = await scorer.compute_scores(["p1"], None, [])
        assert scores["p1"]["late"] == 0.0

        scorer.register_provider("late_src", LateProvider())
        scores = await scorer.compute_scores(["p1"], None, [])
        assert scores["p1"]["late"] == 99.0

    async def test_custom_provider_overrides_built_in(self):
        class OverrideState:
            async def compute(self, ctx: ScoringContext) -> float:
                return 999.0

        config = ScoringConfig(
            metrics=[ScoringMetric(name="val", source="state", entity_type="x", field="y")],
        )
        scorer = GameScorer(config, providers={"state": OverrideState()})
        scores = await scorer.compute_scores(["p1"], None, [])
        assert scores["p1"]["val"] == 999.0


class TestProviderReceivesCorrectContext:
    async def test_context_contains_all_fields(self):
        received_contexts: list[ScoringContext] = []

        class SpyProvider:
            async def compute(self, ctx: ScoringContext) -> float:
                received_contexts.append(ctx)
                return 1.0

        metric = ScoringMetric(name="spy", source="spy_src", entity_type="acct", field="bal")
        config = ScoringConfig(metrics=[metric])
        scorer = GameScorer(config, providers={"spy_src": SpyProvider()})

        mock_state = AsyncMock()
        events = [SimpleNamespace(event_type="x", actor_id="p1", input_data={})]
        resolved = {"acct": "pack_acct"}

        await scorer.compute_scores(["p1"], mock_state, events, resolved_entity_types=resolved)

        assert len(received_contexts) == 1
        ctx = received_contexts[0]
        assert ctx.player_id == "p1"
        assert ctx.metric.name == "spy"
        assert ctx.state_engine is mock_state
        assert len(ctx.events) == 1
        assert ctx.resolved_entity_types == {"acct": "pack_acct"}
