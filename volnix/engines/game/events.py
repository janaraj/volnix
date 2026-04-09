"""Game-specific event types."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from volnix.core.events import Event
from volnix.core.types import ActorId


class GameStartedEvent(Event):
    """Game has started."""

    game_mode: str
    player_ids: list[str] = Field(default_factory=list)
    total_rounds: int = 0


class GameRoundStartedEvent(Event):
    """A new round has begun."""

    round_number: int
    total_rounds: int


class GameRoundEndedEvent(Event):
    """A round has ended with standings."""

    round_number: int
    standings: list[dict[str, Any]] = Field(default_factory=list)


class GameTurnEvent(Event):
    """A player's turn within a round."""

    round_number: int
    actor_id: ActorId
    actions_taken: int = 0
    actions_remaining: int = 0


class GameScoreUpdatedEvent(Event):
    """A player's score was updated."""

    actor_id: ActorId
    metric: str
    value: float = 0.0
    round_number: int = 0


class GameCompletedEvent(Event):
    """Game has finished."""

    winner: str | None = None
    final_standings: list[dict[str, Any]] = Field(default_factory=list)
    reason: str = ""
    total_rounds_played: int = 0


class GameEliminationEvent(Event):
    """A player was eliminated."""

    actor_id: ActorId
    reason: str = ""
    round_number: int = 0
