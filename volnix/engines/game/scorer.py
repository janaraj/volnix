"""Game scorer — computes game-specific metrics from state, events, and budgets.

Generic scorer that reads metric definitions from ScoringConfig and
evaluates them against world state and committed events.
"""

from __future__ import annotations

import logging
from typing import Any

from volnix.engines.game.definition import ScoringConfig, ScoringMetric

logger = logging.getLogger(__name__)


class GameScorer:
    """Computes game scores from state, events, and budgets."""

    def __init__(self, config: ScoringConfig) -> None:
        self._metrics = list(config.metrics)
        self._ranking = config.ranking
        self._weights = {m.name: m.weight for m in config.metrics}

    @property
    def weights(self) -> dict[str, float]:
        return dict(self._weights)

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
        if metric.source == "state":
            query_type = (resolved_entity_types or {}).get(
                metric.entity_type, metric.entity_type
            )
            return await self._from_state(metric, player_id, state_engine, query_type)
        elif metric.source == "events":
            return self._from_events(metric, player_id, events)
        elif metric.source == "budget":
            return await self._from_budget(metric, player_id, state_engine)
        return 0.0

    async def _from_state(
        self,
        metric: ScoringMetric,
        player_id: str,
        state_engine: Any,
        query_type: str | None = None,
    ) -> float:
        """Read metric value from entity state.

        Matches entities by ``game_owner_id`` (set at game start by
        GameEngine._assign_entity_ownership). Falls back to owner_id /
        actor_id / id fields for non-game contexts.
        """
        if state_engine is None:
            return 0.0
        try:
            entities = await state_engine.query_entities(
                entity_type=query_type or metric.entity_type,
            )
            if not entities:
                return 0.0

            # Primary: match by game_owner_id (set by game engine at start)
            player_entities = [
                e for e in entities if e.get("game_owner_id") == player_id
            ]

            # Fallback: check owner_id / actor_id / id fields
            if not player_entities:
                for entity in entities:
                    owner = entity.get(
                        "owner_id", entity.get("actor_id", entity.get("id", ""))
                    )
                    if owner == player_id or entity.get("id") == player_id:
                        player_entities.append(entity)

            if not player_entities:
                return 0.0

            values = []
            for entity in player_entities:
                val = entity.get(metric.field, 0.0)
                if val is not None:
                    values.append(float(val))

            if not values:
                return 0.0
            if metric.aggregation == "sum":
                return sum(values)
            elif metric.aggregation == "max":
                return max(values)
            elif metric.aggregation == "min":
                return min(values)
            return values[-1]  # "last" or default
        except Exception as exc:
            logger.debug("State query failed for %s: %s", metric.name, exc)
        return 0.0

    def _from_events(
        self,
        metric: ScoringMetric,
        player_id: str,
        events: list[Any],
    ) -> float:
        """Compute metric from committed events."""
        matching = [
            e
            for e in events
            if getattr(e, "event_type", "") == metric.event_type
            and str(getattr(e, "actor_id", "")) == player_id
        ]
        if metric.aggregation == "count":
            return float(len(matching))
        elif metric.aggregation == "sum":
            return sum(float(getattr(e, "input_data", {}).get("amount", 0) or 0) for e in matching)
        elif metric.aggregation == "max":
            vals = [float(getattr(e, "input_data", {}).get(metric.field, 0) or 0) for e in matching]
            return max(vals) if vals else 0.0
        elif metric.aggregation == "min":
            vals = [float(getattr(e, "input_data", {}).get(metric.field, 0) or 0) for e in matching]
            return min(vals) if vals else 0.0
        elif metric.aggregation == "last":
            if matching:
                return float(getattr(matching[-1], "input_data", {}).get(metric.field, 0) or 0)
        return 0.0

    async def _from_budget(
        self,
        metric: ScoringMetric,
        player_id: str,
        state_engine: Any,
    ) -> float:
        """Read metric from budget state (not implemented yet)."""
        return 0.0
