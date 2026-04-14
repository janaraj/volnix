"""CompetitiveScorer — zero-sum leaderboard with BATNA settlement.

Owns the ``_compute_deal_score`` algorithm moved from the legacy
``volnix/game/evaluators/negotiation.py``. Reads ``negotiation_target_terms``
entities (materialized only in competitive mode) and never reads
behavior metrics.

Key Cycle B change: efficiency_bonus is event-count based (MF4):

``efficiency_bonus = max(0, (max_events - event_number) * bonus_per_event)``

This replaces the legacy round-based formula
``(total_rounds - current_round) * EFFICIENCY_BONUS_PER_ROUND``.
For Q3 Steel with ``max_events=8`` and ``bonus_per_event=1.75``, the
curves are equivalent to the legacy ``max_bonus=14`` anchor — new
blueprints set these values to match their desired semantic shape.
Documented in CHANGELOG.
"""

from __future__ import annotations

import logging
from typing import Any

from volnix.engines.game.definition import PlayerScore
from volnix.engines.game.scorers.base import GameScorer, ScorerContext

logger = logging.getLogger(__name__)


class CompetitiveScorer(GameScorer):
    """Leaderboard scorer for competitive negotiation scenarios.

    Reads ``negotiation_target_terms`` entities for ideal_terms,
    term_weights, term_ranges, batna_score. Computes deal_score on
    accept and applies BATNA on reject/timeout settlement.

    Never reads ``behavior_metrics`` — they belong to BehavioralScorer.
    """

    def __init__(self, bonus_per_event: float = 0.14) -> None:
        """Initialize with the per-event bonus multiplier.

        Args:
            bonus_per_event: The efficiency_bonus multiplier. A higher
                value makes early closing more valuable. Default 0.14
                (tuned so a 100-event game has max bonus ~14, matching
                the legacy Q3 Steel 14-point anchor).
        """
        self._bonus_per_event = bonus_per_event

    async def score_event(self, ctx: ScorerContext) -> None:
        """Score a single committed game event.

        - ``negotiate_propose`` / ``negotiate_counter``: no score change;
          state mutation is done by the game pack handler.
        - ``negotiate_accept``: compute final deal_score per party using
          ``_compute_deal_score`` + efficiency_bonus.
        - ``negotiate_reject``: apply BATNA to the rejecter.
        """
        event = ctx.event
        action = str(event.action)

        if action == "negotiate_accept":
            await self._score_accept(ctx)
        elif action == "negotiate_reject":
            await self._score_reject(ctx)
        # propose/counter: no score change

    async def _score_accept(self, ctx: ScorerContext) -> None:
        deal_id = str(ctx.event.input_data.get("deal_id", ""))
        if not deal_id:
            return
        deals = await ctx.state_engine.query_entities("negotiation_deal", {"id": deal_id})
        if not deals:
            logger.warning("CompetitiveScorer: no deal found for id %s", deal_id)
            return
        deal = deals[0]
        agreed_terms: dict[str, Any] = deal.get("terms") or {}
        if not agreed_terms:
            logger.warning("CompetitiveScorer: deal %s has empty terms, skipping score", deal_id)
            return

        targets = await ctx.state_engine.query_entities(
            "negotiation_target_terms", {"deal_id": deal_id}
        )
        max_events = ctx.definition.flow.max_events
        efficiency_bonus = max(
            0.0,
            (max_events - ctx.event_number) * self._bonus_per_event,
        )

        for target in targets:
            actor_role = str(target.get("actor_role", ""))
            player_id = self._resolve_player_by_role(actor_role, ctx.player_scores)
            if player_id is None:
                continue
            deal_score = self._compute_deal_score(agreed_terms, target)
            total = deal_score + efficiency_bonus
            ps = ctx.player_scores[player_id]
            ps.metrics["deal_score"] = deal_score
            ps.metrics["efficiency_bonus"] = efficiency_bonus
            ps.metrics["total_points"] = total
            ps.metrics["deals_closed"] = 1.0
            ps.total_score = total
            logger.info(
                "CompetitiveScorer: %s scored %.1f on deal %s (deal=%.1f + bonus=%.1f at event %d)",
                player_id,
                total,
                deal_id,
                deal_score,
                efficiency_bonus,
                ctx.event_number,
            )

    async def _score_reject(self, ctx: ScorerContext) -> None:
        """Rejecting party gets BATNA."""
        actor_id = str(ctx.event.actor_id)
        actor_role = actor_id.rsplit("-", 1)[0] if "-" in actor_id else actor_id
        player_id = self._resolve_player_by_role(actor_role, ctx.player_scores)
        if player_id is None:
            return
        deal_id = str(ctx.event.input_data.get("deal_id", ""))
        targets = await ctx.state_engine.query_entities(
            "negotiation_target_terms", {"deal_id": deal_id, "actor_role": actor_role}
        )
        if not targets:
            return
        batna = float(targets[0].get("batna_score", 0.0))
        ps = ctx.player_scores[player_id]
        ps.metrics["total_points"] = batna
        ps.metrics["batna_applied"] = 1.0
        ps.total_score = batna

    async def settle(
        self,
        open_deals: list[dict[str, Any]],
        state_engine: Any,
        player_scores: dict[str, PlayerScore],
        definition: Any,
    ) -> None:
        """Apply BATNA to every player whose deal didn't close on timeout."""
        for deal in open_deals:
            deal_id = str(deal.get("id", ""))
            parties = deal.get("parties") or []
            targets = await state_engine.query_entities(
                "negotiation_target_terms", {"deal_id": deal_id}
            )
            targets_by_role = {str(t.get("actor_role", "")): t for t in targets}
            for actor_role in parties:
                player_id = self._resolve_player_by_role(actor_role, player_scores)
                if player_id is None:
                    continue
                ps = player_scores[player_id]
                if ps.metrics.get("deals_closed", 0.0) >= 1.0:
                    continue  # already closed, leave score alone
                target = targets_by_role.get(actor_role)
                batna = float(target.get("batna_score", 0.0)) if target else 0.0
                ps.metrics["total_points"] = batna
                ps.metrics["batna_applied"] = 1.0
                ps.total_score = batna
        logger.info(
            "CompetitiveScorer.settle: applied BATNA to %d open deals",
            len(open_deals),
        )

    @staticmethod
    def _resolve_player_by_role(
        actor_role: str, player_scores: dict[str, PlayerScore]
    ) -> str | None:
        """Find the player_id whose actor_id starts with actor_role.

        Role 'nimbus_buyer' matches player_id 'nimbus_buyer-ff6dd400'.
        """
        for pid, ps in player_scores.items():
            if pid.startswith(actor_role + "-") or ps.actor_id.startswith(actor_role + "-"):
                return pid
        return None

    @staticmethod
    def _compute_deal_score(actual_terms: dict[str, Any], target: dict[str, Any]) -> float:
        """Weighted distance-based scoring. Returns 0-100.

        Moved from volnix/game/evaluators/negotiation.py::_compute_deal_score.
        Zero semantic change — this is the EXACT same formula as the
        legacy competitive path.

        For each term:
        1. distance = |actual - ideal| / (range_hi - range_lo)
        2. term_score = max(0, (1 - distance) * 100)
        3. weight by term_weight
        Then return weighted average.
        """
        ideal = target.get("ideal_terms") or {}
        weights = target.get("term_weights") or {}
        ranges = target.get("term_ranges") or {}

        total_score = 0.0
        total_weight = 0.0

        for term_name, ideal_val in ideal.items():
            actual_val = actual_terms.get(term_name)
            if actual_val is None:
                continue
            try:
                ideal_f = float(ideal_val)
                actual_f = float(actual_val)
            except (ValueError, TypeError):
                continue

            w = float(weights.get(term_name, 1.0))
            bounds = ranges.get(term_name) or [0, ideal_f * 2]
            lo = float(bounds[0]) if len(bounds) > 0 else 0.0
            hi = float(bounds[1]) if len(bounds) > 1 else ideal_f * 2
            span = hi - lo

            if span == 0:
                term_score = 100.0 if actual_f == ideal_f else 0.0
            else:
                distance = abs(actual_f - ideal_f) / span
                term_score = max(0.0, (1.0 - distance) * 100.0)

            total_score += term_score * w
            total_weight += w

        return total_score / total_weight if total_weight > 0 else 0.0
