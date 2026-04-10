"""Base round evaluator — shared state I/O, ledger integration, player resolution.

Provides audited state writes (create/update with ledger entries) and
player ID resolution (game_owner_id + role-prefix fallback). Subclasses
implement game-type-specific logic in evaluate().
"""

from __future__ import annotations

import logging
from typing import Any

from volnix.core.types import EntityId

logger = logging.getLogger(__name__)


class BaseRoundEvaluator:
    """Shared functionality for all round evaluators.

    Subclasses call these helpers — they are NOT abstract methods.
    The RoundEvaluator Protocol defines the external contract; this
    class provides internal plumbing.
    """

    def __init__(self) -> None:
        self._store: Any = None
        self._ledger: Any = None
        self._state_engine: Any = None

    async def build_deliverable_extras(self, state_engine: Any) -> dict[str, Any]:
        """Default: no extras. Override in subclasses to contribute summary data.

        Called by the runner after ``complete_game()`` to collect game-type-
        specific data for the run deliverable (e.g., accepted deals, auction
        winners, debate verdicts). Returning an empty dict is a no-op — the
        deliverable keeps its standard scoreboard layout.
        """
        return {}

    def game_tools(self) -> list[Any]:
        """Default: no structured game-move tools.

        Override in subclasses to declare tools like ``negotiate_propose``,
        ``auction_bid``, ``debate_argue``. The runner registers these with
        the agency engine at game start so the LLM sees them as first-class
        structured tool calls, and the evaluator reads their committed
        events directly from ``round_events`` — no text parsing required.
        """
        return []

    def _init_state_access(self, state_engine: Any) -> bool:
        """Extract store and ledger from state engine. Returns False if unavailable."""
        if state_engine is None:
            return False
        self._state_engine = state_engine
        self._store = getattr(state_engine, "_store", None)
        self._ledger = getattr(state_engine, "_ledger", None)
        if self._store is None:
            logger.warning("No _store on state_engine — cannot update entities")
            return False
        return True

    # -- Audited state writes ----------------------------------------------

    async def _create_entity(
        self, entity_type: str, entity_id: str, fields: dict[str, Any]
    ) -> bool:
        """Create an entity with ledger audit trail. Returns True on success."""
        try:
            await self._store.create(entity_type, EntityId(entity_id), fields)
        except Exception as exc:
            logger.warning("Failed to create %s/%s: %s", entity_type, entity_id, exc)
            return False

        await self._record_mutation(entity_type, entity_id, "create", after=fields)
        return True

    async def _update_entity(
        self, entity_type: str, entity_id: str, fields: dict[str, Any]
    ) -> bool:
        """Update an entity with ledger audit trail. Returns True on success."""
        try:
            previous = await self._store.update(entity_type, EntityId(entity_id), fields)
        except Exception as exc:
            logger.warning("Failed to update %s/%s: %s", entity_type, entity_id, exc)
            return False

        await self._record_mutation(entity_type, entity_id, "update", before=previous, after=fields)
        return True

    async def _record_mutation(
        self,
        entity_type: str,
        entity_id: str,
        operation: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        """Append a StateMutationEntry to the ledger (if available)."""
        if self._ledger is None:
            return
        try:
            from volnix.ledger.entries import StateMutationEntry

            entry = StateMutationEntry(
                entity_type=entity_type,
                entity_id=EntityId(entity_id),
                operation=operation,
                before=before,
                after=after,
            )
            await self._ledger.append(entry)
        except Exception as exc:
            logger.debug("Ledger append failed for %s/%s: %s", entity_type, entity_id, exc)

    # -- Player ID resolution ----------------------------------------------

    @staticmethod
    def _resolve_player_for_entity(
        entity: dict[str, Any],
        player_ids: list[str],
    ) -> str:
        """Resolve which player an entity belongs to.

        Tries in order:
        1. entity.game_owner_id exact match in player_ids
        2. entity.game_owner_id as prefix of a player_id (e.g., "buyer" -> "buyer-abc123")
        3. Empty string if no match
        """
        owner = entity.get("game_owner_id", "")
        if not owner:
            return ""

        # Exact match
        if owner in player_ids:
            return owner

        # Prefix match (compiler may set "buyer", runtime ID is "buyer-abc123")
        for pid in player_ids:
            if pid.startswith(owner) or owner.startswith(pid):
                return pid

        return ""

    @staticmethod
    def _resolve_targets_via_deals(
        targets: list[dict[str, Any]],
        deals: list[dict[str, Any]],
        player_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Match targets to players using deal parties as the link.

        Tries game_owner_id exact match first. If that doesn't resolve all
        targets, falls back to matching via deal.parties[i] → player prefix.
        """
        result: dict[str, dict[str, Any]] = {}

        # Try game_owner_id first (works when compiler sets it correctly)
        for t in targets:
            owner = t.get("game_owner_id", "")
            if owner and owner in player_ids:
                result[owner] = t

        # If all targets resolved via game_owner_id, done
        if len(result) == len(targets):
            return result

        # Fallback: match via deal parties list
        result.clear()
        targets_by_deal: dict[str, list[dict[str, Any]]] = {}
        for t in targets:
            did = t.get("deal_id", "")
            if did:
                targets_by_deal.setdefault(did, []).append(t)

        for deal in deals:
            deal_id = deal.get("id", "")
            parties = deal.get("parties", [])
            deal_targets = targets_by_deal.get(deal_id, [])

            for i, party_role in enumerate(parties):
                matched_player = next(
                    (pid for pid in player_ids if pid.startswith(party_role)),
                    None,
                )
                if matched_player and i < len(deal_targets):
                    result[matched_player] = deal_targets[i]

        return result

        return ""
