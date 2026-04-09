"""Configuration model for the game engine."""

from __future__ import annotations

from pydantic import BaseModel


class GameConfig(BaseModel):
    """Configuration for the game engine."""

    enabled: bool = True
    max_rounds: int = 100
    max_players: int = 20
    default_actions_per_turn: int = 5
    announce_interval: int = 1  # Announce standings every N rounds
