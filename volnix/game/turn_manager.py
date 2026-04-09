"""Turn manager — controls turn order for sequential games.

Supports fixed order, round-robin rotation, random shuffle,
and player elimination.
"""

from __future__ import annotations

import enum
import logging
import random as _random

logger = logging.getLogger(__name__)


class TurnOrder(enum.StrEnum):
    """Turn order strategy."""

    FIXED = "fixed"
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"


class TurnManager:
    """Manages turn order for sequential games."""

    def __init__(
        self,
        players: list[str],
        order: TurnOrder = TurnOrder.FIXED,
        seed: int | None = None,
    ) -> None:
        self._all_players = list(players)
        self._active_players = list(players)
        self._order = order
        self._current_index = 0
        self._rng = _random.Random(seed)

    @property
    def active_players(self) -> list[str]:
        return list(self._active_players)

    @property
    def player_count(self) -> int:
        return len(self._active_players)

    def get_order(self) -> list[str]:
        """Return player order for this round."""
        if not self._active_players:
            return []
        if self._order == TurnOrder.FIXED:
            return list(self._active_players)
        elif self._order == TurnOrder.ROUND_ROBIN:
            idx = self._current_index % len(self._active_players)
            order = self._active_players[idx:] + self._active_players[:idx]
            self._current_index = (self._current_index + 1) % max(1, len(self._active_players))
            return order
        elif self._order == TurnOrder.RANDOM:
            shuffled = list(self._active_players)
            self._rng.shuffle(shuffled)
            return shuffled
        return list(self._active_players)

    def eliminate(self, player_id: str) -> None:
        """Remove player from turn order."""
        self._active_players = [p for p in self._active_players if p != player_id]
        logger.info(
            "Player %s eliminated. %d remaining.",
            player_id,
            len(self._active_players),
        )

    def is_eliminated(self, player_id: str) -> bool:
        """Check if player has been eliminated."""
        return player_id not in self._active_players

    def reset(self) -> None:
        """Reset to initial state."""
        self._active_players = list(self._all_players)
        self._current_index = 0
