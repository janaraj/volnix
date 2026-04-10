"""Negotiation evaluator — generic round evaluator for negotiation games.

Parses structured proposal messages from round events, tracks deal state,
computes deal scores using weighted distance from each player's ideal terms.
All configuration comes from state entities — zero hardcoded terms.

Entity types read from state:
- negotiation_deal: deal definition with terms_template, status, parties
- negotiation_target: per-player ideal terms, weights, ranges, batna_score
- negotiation_scorecard: per-player scoring entity (updated by this evaluator)

Entity types created by this evaluator:
- negotiation_proposal: individual proposals/counteroffers (audit trail)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from volnix.engines.game.definition import PlayerScore, RoundState
from volnix.game.evaluators.base import BaseRoundEvaluator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Message patterns — agents must use these exact formats
# ---------------------------------------------------------------------------

PROPOSAL_RE = re.compile(r"PROPOSAL:\s*(\{.*\})", re.DOTALL)
COUNTER_RE = re.compile(r"COUNTER:\s*(\{.*\})", re.DOTALL)
ACCEPT_RE = re.compile(r"ACCEPT:\s*([\w-]+)")
REJECT_RE = re.compile(r"REJECT:\s*([\w-]+)")

# Efficiency bonus: points per remaining round when deal is reached early
EFFICIENCY_BONUS_PER_ROUND = 2.0


# ---------------------------------------------------------------------------
# Parsed message types
# ---------------------------------------------------------------------------


class ParsedMessage:
    """A structured message extracted from a round event."""

    __slots__ = ("actor_id", "msg_type", "deal_id", "terms")

    def __init__(
        self,
        actor_id: str,
        msg_type: str,
        deal_id: str = "",
        terms: dict[str, Any] | None = None,
    ) -> None:
        self.actor_id = actor_id
        self.msg_type = msg_type  # "proposal", "counter", "accept", "reject"
        self.deal_id = deal_id
        self.terms = terms


# ---------------------------------------------------------------------------
# NegotiationEvaluator
# ---------------------------------------------------------------------------


class NegotiationEvaluator(BaseRoundEvaluator):
    """Generic negotiation round evaluator.

    Inherits from BaseRoundEvaluator for audited state writes, ledger
    integration, and player ID resolution. Implements the RoundEvaluator
    protocol. Called by GameRunner after player turns but before scoring.
    """

    def __init__(self) -> None:
        super().__init__()
        self._proposal_counter: int = 0  # per-round sequence counter

    async def evaluate(
        self,
        state_engine: Any,
        round_events: list[Any],
        round_state: RoundState,
        player_scores: dict[str, PlayerScore],
    ) -> None:
        """Parse round messages, update deal state, compute scores."""
        if not self._init_state_access(state_engine):
            return

        # Reset per-round counter
        self._proposal_counter = 0

        # 1. Parse structured messages from round events
        messages = self._parse_round_messages(round_events)
        if not messages:
            # Check if final round — apply BATNA for players with no deal
            if round_state.current_round >= round_state.total_rounds:
                await self._apply_batna_for_no_deal(player_scores)
            return

        # 2. Load deal state from entities
        try:
            deals = await self._state_engine.query_entities(entity_type="negotiation_deal")
        except Exception as exc:
            logger.warning("Failed to query negotiation_deal entities: %s", exc)
            return

        if not deals:
            logger.warning("No negotiation_deal entities found — skipping evaluation")
            return

        # 3. Two-pass processing: proposals/counters first (updates deal terms in DB),
        #    then reload deals, then accepts/rejects (read updated terms).
        for msg in messages:
            if msg.msg_type in ("proposal", "counter"):
                await self._process_proposal(msg, deals, round_state)

        # Reload deals to pick up term updates from proposals/counters
        try:
            deals = await self._state_engine.query_entities(
                entity_type="negotiation_deal"
            )
        except Exception as exc:
            logger.warning("Failed to reload deals after proposals: %s", exc)

        for msg in messages:
            if msg.msg_type == "accept":
                await self._process_accept(msg, deals, round_state, player_scores)
            elif msg.msg_type == "reject":
                await self._process_reject(msg, deals)

        # 4. Final round — apply BATNA for players with no accepted deal
        if round_state.current_round >= round_state.total_rounds:
            await self._apply_batna_for_no_deal(player_scores)

    # -- Message parsing ---------------------------------------------------

    def _parse_round_messages(self, round_events: list[Any]) -> list[ParsedMessage]:
        """Extract structured messages from round events."""
        messages: list[ParsedMessage] = []

        for event in round_events:
            event_type = getattr(event, "event_type", "")
            if event_type != "world.chat.postMessage":
                continue

            actor_id = str(getattr(event, "actor_id", ""))
            input_data = getattr(event, "input_data", {})
            text = input_data.get("text", "") if isinstance(input_data, dict) else ""

            if not text or not actor_id:
                continue

            parsed = self._parse_message_text(actor_id, text)
            if parsed is not None:
                messages.append(parsed)

        return messages

    def _parse_message_text(self, actor_id: str, text: str) -> ParsedMessage | None:
        """Try each pattern against message text. First match wins."""
        # PROPOSAL
        match = PROPOSAL_RE.search(text)
        if match:
            terms = self._safe_parse_json(match.group(1))
            if terms is not None:
                return ParsedMessage(actor_id, "proposal", terms=terms)
            return None

        # COUNTER
        match = COUNTER_RE.search(text)
        if match:
            terms = self._safe_parse_json(match.group(1))
            if terms is not None:
                return ParsedMessage(actor_id, "counter", terms=terms)
            return None

        # ACCEPT
        match = ACCEPT_RE.search(text)
        if match:
            return ParsedMessage(actor_id, "accept", deal_id=match.group(1))

        # REJECT
        match = REJECT_RE.search(text)
        if match:
            return ParsedMessage(actor_id, "reject", deal_id=match.group(1))

        logger.debug("No structured pattern in message from %s: %.80s", actor_id, text)
        return None

    @staticmethod
    def _safe_parse_json(raw: str) -> dict[str, Any] | None:
        """Parse JSON from message text, returning None on failure."""
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError) as exc:
            logger.debug("Failed to parse proposal JSON: %s — %.80s", exc, raw)
        return None

    # -- Proposal / Counter ------------------------------------------------

    async def _process_proposal(
        self,
        msg: ParsedMessage,
        deals: list[dict[str, Any]],
        round_state: RoundState,
    ) -> None:
        """Create proposal entity and update deal status."""
        deal = self._find_active_deal(deals, msg.actor_id)
        if deal is None:
            logger.warning("No active deal found for %s — skipping proposal", msg.actor_id)
            return

        deal_id = deal.get("id", "")
        new_status = "proposed" if msg.msg_type == "proposal" else "countered"
        self._proposal_counter += 1

        # Create proposal entity (audited)
        proposal_id = f"prop-{round_state.current_round:03d}-{self._proposal_counter:03d}"
        proposal_data = {
            "id": proposal_id,
            "deal_id": deal_id,
            "proposed_by": msg.actor_id,
            "round_number": round_state.current_round,
            "terms": msg.terms or {},
            "status": "pending",
            "msg_type": msg.msg_type,
        }

        await self._create_entity("negotiation_proposal", proposal_id, proposal_data)

        # Update deal status and current terms (audited)
        await self._update_entity(
            "negotiation_deal",
            deal_id,
            {"status": new_status, "terms": msg.terms, "last_proposed_by": msg.actor_id},
        )

        logger.info(
            "[NEGOTIATION] %s %s on deal %s: %s",
            msg.actor_id,
            msg.msg_type,
            deal_id,
            msg.terms,
        )

    # -- Accept ------------------------------------------------------------

    async def _process_accept(
        self,
        msg: ParsedMessage,
        deals: list[dict[str, Any]],
        round_state: RoundState,
        player_scores: dict[str, PlayerScore],
    ) -> None:
        """Accept a deal: update deal status, compute scores for both parties."""
        deal = self._find_deal_by_id(deals, msg.deal_id)
        if deal is None:
            deal = self._find_active_deal(deals, msg.actor_id)
        if deal is None:
            logger.warning(
                "No deal found for ACCEPT from %s (deal_id=%s)", msg.actor_id, msg.deal_id
            )
            return

        deal_id = deal.get("id", "")
        agreed_terms = deal.get("terms", {})

        if not agreed_terms:
            logger.warning("Deal %s has no terms — cannot compute scores", deal_id)
            return

        # Update deal status (audited)
        success = await self._update_entity(
            "negotiation_deal",
            deal_id,
            {
                "status": "accepted",
                "accepted_by": msg.actor_id,
                "accepted_round": round_state.current_round,
            },
        )
        if not success:
            return

        # Load targets for both parties
        try:
            targets = await self._state_engine.query_entities(
                entity_type="negotiation_target"
            )
        except Exception as exc:
            logger.warning("Failed to query negotiation_target entities: %s", exc)
            return

        deal_targets = [t for t in targets if t.get("deal_id") == deal_id]

        # Compute and apply scores for each party
        efficiency_bonus = max(
            0.0,
            (round_state.total_rounds - round_state.current_round) * EFFICIENCY_BONUS_PER_ROUND,
        )

        all_player_ids = list(player_scores.keys())
        target_player_map = self._resolve_targets_via_deals(
            deal_targets, [deal], all_player_ids
        )
        for player_id, target in target_player_map.items():
            deal_score = self._compute_deal_score(agreed_terms, target)
            total_points = deal_score + efficiency_bonus

            await self._update_scorecard(
                player_id,
                deal_score=deal_score,
                efficiency_bonus=efficiency_bonus,
                total_points=total_points,
                deals_closed=1,
            )

            logger.info(
                "[NEGOTIATION] %s scored %.1f (deal=%.1f + bonus=%.1f) on deal %s",
                player_id,
                total_points,
                deal_score,
                efficiency_bonus,
                deal_id,
            )

    # -- Reject ------------------------------------------------------------

    async def _process_reject(
        self,
        msg: ParsedMessage,
        deals: list[dict[str, Any]],
    ) -> None:
        """Reject a deal: update deal status."""
        deal = self._find_deal_by_id(deals, msg.deal_id)
        if deal is None:
            deal = self._find_active_deal(deals, msg.actor_id)
        if deal is None:
            logger.warning("No deal found for REJECT from %s", msg.actor_id)
            return

        deal_id = deal.get("id", "")
        await self._update_entity(
            "negotiation_deal",
            deal_id,
            {"status": "rejected", "rejected_by": msg.actor_id},
        )

        logger.info("[NEGOTIATION] %s rejected deal %s", msg.actor_id, deal_id)

    # -- BATNA (final round, no deal) -------------------------------------

    async def _apply_batna_for_no_deal(
        self,
        player_scores: dict[str, PlayerScore],
    ) -> None:
        """On final round, set BATNA score for players who didn't close a deal."""
        try:
            scorecards = await self._state_engine.query_entities(
                entity_type="negotiation_scorecard"
            )
        except Exception:
            return

        try:
            targets = await self._state_engine.query_entities(
                entity_type="negotiation_target"
            )
        except Exception:
            return

        # Resolve targets to players via deal parties fallback
        all_player_ids = list(player_scores.keys())
        try:
            deals = await self._state_engine.query_entities(
                entity_type="negotiation_deal"
            )
        except Exception:
            deals = []
        target_map = self._resolve_targets_via_deals(targets, deals, all_player_ids)

        if not target_map:
            logger.warning(
                "[NEGOTIATION] Cannot resolve targets to players — BATNA not applied. "
                "Ensure negotiation_target entities have game_owner_id matching player roles, "
                "or that deal parties match player role prefixes."
            )
            return

        for sc in scorecards:
            player_id = self._resolve_player_for_entity(sc, all_player_ids)
            deals_closed = sc.get("deals_closed", 0)
            if deals_closed > 0 or not player_id:
                continue

            # No deal reached — apply BATNA score
            target = target_map.get(player_id, {})
            batna = float(target.get("batna_score", 0.0))
            if batna > 0:
                await self._update_scorecard(
                    player_id,
                    total_points=batna,
                    batna_applied=True,
                )
                logger.info(
                    "[NEGOTIATION] %s gets BATNA score %.1f (no deal)", player_id, batna
                )

    # -- Deal score computation --------------------------------------------

    @staticmethod
    def _compute_deal_score(
        actual_terms: dict[str, Any], target: dict[str, Any]
    ) -> float:
        """Compute how close agreed terms are to a player's ideal.

        Returns 0-100. Uses weighted distance normalized by term ranges.
        All config comes from the target entity — zero hardcoded terms.
        """
        ideal = target.get("ideal_terms", {})
        weights = target.get("term_weights", {})
        ranges = target.get("term_ranges", {})

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
            bounds = ranges.get(term_name, [0, ideal_f * 2])
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

    # -- Scorecard update --------------------------------------------------

    async def _update_scorecard(self, player_id: str, **fields: Any) -> None:
        """Update a player's negotiation_scorecard entity (audited)."""
        try:
            scorecards = await self._state_engine.query_entities(
                entity_type="negotiation_scorecard"
            )
        except Exception as exc:
            logger.warning("Failed to query scorecards: %s", exc)
            return

        sc = next(
            (
                s
                for s in scorecards
                if self._resolve_player_for_entity(s, [player_id]) == player_id
            ),
            None,
        )
        if sc is None:
            logger.warning("No scorecard found for player %s", player_id)
            return

        await self._update_entity("negotiation_scorecard", sc.get("id", ""), fields)

    # -- Deal lookup helpers -----------------------------------------------

    @staticmethod
    def _find_active_deal(
        deals: list[dict[str, Any]], actor_id: str
    ) -> dict[str, Any] | None:
        """Find the active (non-terminal) deal involving this actor."""
        terminal = {"accepted", "rejected", "expired"}
        for deal in deals:
            status = deal.get("status", "")
            if status in terminal:
                continue
            parties = deal.get("parties", [])
            for party in parties:
                if party == actor_id or actor_id.startswith(party):
                    return deal
        # Fallback: return the first non-terminal deal
        for deal in deals:
            if deal.get("status", "") not in terminal:
                return deal
        return None

    @staticmethod
    def _find_deal_by_id(
        deals: list[dict[str, Any]], deal_id: str
    ) -> dict[str, Any] | None:
        """Find a deal by its ID."""
        if not deal_id:
            return None
        for deal in deals:
            if deal.get("id") == deal_id:
                return deal
        return None

    # -- Deliverable summary -----------------------------------------------

    async def build_deliverable_extras(
        self, state_engine: Any
    ) -> dict[str, Any]:
        """Summarize negotiation deals for the run deliverable.

        Emits a ``deals`` array of flat-primitive objects so the frontend
        renders them as a compact card list under a single ``Deals``
        section. Each entry contains the deal title, status (uppercased),
        the acting party (accepted_by / rejected_by / last_proposed_by),
        the round it was decided, and the terms as a comma-separated
        string. Array length implicitly conveys the total and accepted
        counts — no redundant scalar counters.
        """
        if state_engine is None:
            return {}
        try:
            deals = await state_engine.query_entities(
                entity_type="negotiation_deal"
            )
        except Exception as exc:
            logger.warning("build_deliverable_extras: query failed — %s", exc)
            return {}
        if not deals:
            return {}

        deals_list: list[dict[str, Any]] = []
        for deal in deals:
            deal_id = deal.get("id", "deal")
            title = deal.get("title") or deal_id
            status = (deal.get("status") or "unknown").upper()
            terms = deal.get("terms") or {}
            terms_str = (
                ", ".join(f"{k}={v}" for k, v in terms.items())
                if terms
                else "no terms proposed"
            )

            entry: dict[str, Any] = {
                "title": title,
                "status": status,
            }

            if status == "ACCEPTED":
                accepted_by_raw = deal.get("accepted_by") or "?"
                entry["round"] = deal.get("accepted_round", "?")
                entry["accepted_by"] = accepted_by_raw.split("-")[0]
                entry["terms"] = terms_str
            elif status == "REJECTED":
                rejected_by_raw = deal.get("rejected_by") or "?"
                entry["rejected_by"] = rejected_by_raw.split("-")[0]
                entry["terms"] = terms_str
            else:
                last_by_raw = deal.get("last_proposed_by") or "?"
                entry["last_proposed_by"] = last_by_raw.split("-")[0]
                entry["terms"] = terms_str

            deals_list.append(entry)

        return {"deals": deals_list}
