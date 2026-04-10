"""Game scorer — computes game-specific metrics using pluggable scoring providers.

Providers are registered in SCORING_PROVIDER_REGISTRY by source name.
Built-in providers: state, events, budget. Custom providers can be
registered at runtime via GameScorer.register_provider() or by passing
a providers dict to the constructor.
"""

from __future__ import annotations

import logging
from typing import Any

from volnix.engines.game.definition import ScoringConfig, ScoringMetric
from volnix.engines.game.protocols import ScoringContext, ScoringProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Built-in scoring providers
# ---------------------------------------------------------------------------


class StateScoringProvider:
    """Reads metric values from entity state, matched by game_owner_id."""

    async def compute(self, ctx: ScoringContext) -> float:
        if ctx.state_engine is None:
            return 0.0
        try:
            query_type = ctx.resolved_entity_types.get(
                ctx.metric.entity_type, ctx.metric.entity_type
            )
            entities = await ctx.state_engine.query_entities(
                entity_type=query_type,
            )
            if not entities:
                return 0.0

            # Primary: match by game_owner_id (set by game engine at start)
            player_entities = [e for e in entities if e.get("game_owner_id") == ctx.player_id]

            # Fallback: check owner_id / actor_id / id fields
            if not player_entities:
                for entity in entities:
                    owner = entity.get("owner_id", entity.get("actor_id", entity.get("id", "")))
                    if owner == ctx.player_id or entity.get("id") == ctx.player_id:
                        player_entities.append(entity)

            if not player_entities:
                return 0.0

            values = []
            for entity in player_entities:
                val = entity.get(ctx.metric.field, 0.0)
                if val is not None:
                    values.append(float(val))

            if not values:
                return 0.0
            if ctx.metric.aggregation == "sum":
                return sum(values)
            elif ctx.metric.aggregation == "max":
                return max(values)
            elif ctx.metric.aggregation == "min":
                return min(values)
            return values[-1]  # "last" or default
        except Exception as exc:
            logger.debug("State query failed for %s: %s", ctx.metric.name, exc)
        return 0.0


class EventsScoringProvider:
    """Computes metrics from committed events."""

    async def compute(self, ctx: ScoringContext) -> float:
        matching = [
            e
            for e in ctx.events
            if getattr(e, "event_type", "") == ctx.metric.event_type
            and str(getattr(e, "actor_id", "")) == ctx.player_id
        ]
        if ctx.metric.aggregation == "count":
            return float(len(matching))
        elif ctx.metric.aggregation == "sum":
            return sum(float(getattr(e, "input_data", {}).get("amount", 0) or 0) for e in matching)
        elif ctx.metric.aggregation == "max":
            vals = [
                float(getattr(e, "input_data", {}).get(ctx.metric.field, 0) or 0) for e in matching
            ]
            return max(vals) if vals else 0.0
        elif ctx.metric.aggregation == "min":
            vals = [
                float(getattr(e, "input_data", {}).get(ctx.metric.field, 0) or 0) for e in matching
            ]
            return min(vals) if vals else 0.0
        elif ctx.metric.aggregation == "last":
            if matching:
                return float(getattr(matching[-1], "input_data", {}).get(ctx.metric.field, 0) or 0)
        return 0.0


class BudgetScoringProvider:
    """Reads metrics from budget state (stub — returns 0.0)."""

    async def compute(self, ctx: ScoringContext) -> float:
        return 0.0


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

SCORING_PROVIDER_REGISTRY: dict[str, type[ScoringProvider]] = {
    "state": StateScoringProvider,
    "events": EventsScoringProvider,
    "budget": BudgetScoringProvider,
}


# ---------------------------------------------------------------------------
# GameScorer
# ---------------------------------------------------------------------------


class GameScorer:
    """Computes game scores using pluggable scoring providers."""

    def __init__(
        self,
        config: ScoringConfig,
        providers: dict[str, ScoringProvider] | None = None,
    ) -> None:
        self._metrics = list(config.metrics)
        self._ranking = config.ranking
        self._weights = {m.name: m.weight for m in config.metrics}
        # Use provided providers, or instantiate defaults from registry
        if providers is not None:
            self._providers: dict[str, ScoringProvider] = dict(providers)
        else:
            self._providers = {name: cls() for name, cls in SCORING_PROVIDER_REGISTRY.items()}

    @property
    def weights(self) -> dict[str, float]:
        return dict(self._weights)

    def register_provider(self, name: str, provider: ScoringProvider) -> None:
        """Register a custom scoring provider at runtime."""
        self._providers[name] = provider

    async def compute_scores(
        self,
        player_ids: list[str],
        state_engine: Any,  # StateEngineProtocol
        events: list[Any],  # list[Event]
        resolved_entity_types: dict[str, str] | None = None,
    ) -> dict[str, dict[str, float]]:
        """Compute all metrics for all players."""
        scores: dict[str, dict[str, float]] = {}
        for player_id in player_ids:
            player_scores: dict[str, float] = {}
            for metric in self._metrics:
                try:
                    value = await self._compute_metric(
                        metric, player_id, state_engine, events, resolved_entity_types
                    )
                    player_scores[metric.name] = value
                except Exception as exc:
                    logger.warning(
                        "Failed to compute metric %s for %s: %s",
                        metric.name,
                        player_id,
                        exc,
                    )
                    player_scores[metric.name] = 0.0
            scores[player_id] = player_scores
        return scores

    async def _compute_metric(
        self,
        metric: ScoringMetric,
        player_id: str,
        state_engine: Any,
        events: list[Any],
        resolved_entity_types: dict[str, str] | None = None,
    ) -> float:
        provider = self._providers.get(metric.source)
        if provider is None:
            logger.warning("No scoring provider registered for source '%s'", metric.source)
            return 0.0
        ctx = ScoringContext(
            player_id=player_id,
            metric=metric,
            state_engine=state_engine,
            events=events,
            resolved_entity_types=resolved_entity_types or {},
        )
        return await provider.compute(ctx)
