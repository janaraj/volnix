"""Game definition models — frozen Pydantic models for game configuration.

Parsed from the `game:` section of blueprint YAML.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RoundConfig(BaseModel, frozen=True):
    """Round/turn configuration."""

    count: int = 10
    actions_per_turn: int = 5
    simultaneous: bool = False


class ScoringMetric(BaseModel, frozen=True):
    """A single scoring metric definition."""

    name: str
    source: str = "state"
    entity_type: str = ""
    field: str = ""
    event_type: str = ""
    aggregation: str = "last"
    weight: float = 1.0


class ScoringConfig(BaseModel, frozen=True):
    """Scoring configuration."""

    metrics: list[ScoringMetric] = Field(default_factory=list)
    ranking: str = "descending"


class WinCondition(BaseModel, frozen=True):
    """A win/loss condition."""

    type: str = "rounds_complete"
    metric: str = ""
    threshold: float = 0.0
    below: bool = False
    type_config: dict[str, Any] = Field(default_factory=dict)


class ResourceReset(BaseModel, frozen=True):
    """Per-round resource regeneration."""

    api_calls: int = 0
    world_actions: int = 0
    spend_usd: float = 0.0


class BetweenRoundsConfig(BaseModel, frozen=True):
    """Between-round hook configuration."""

    animator_tick: bool = True
    announce_scores: bool = True
    evaluator: str = ""


class GameDefinition(BaseModel, frozen=True):
    """Complete game configuration from blueprint YAML."""

    enabled: bool = False
    mode: str = "competition"
    turn_protocol: str = "independent"
    type_config: dict[str, Any] = Field(default_factory=dict)
    rounds: RoundConfig = Field(default_factory=RoundConfig)
    resource_reset_per_round: ResourceReset = Field(default_factory=ResourceReset)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    win_conditions: list[WinCondition] = Field(default_factory=list)
    between_rounds: BetweenRoundsConfig = Field(default_factory=BetweenRoundsConfig)


# ---------------------------------------------------------------------------
# Runtime state models (mutable, not frozen)
# ---------------------------------------------------------------------------


class PlayerScore(BaseModel):
    """Mutable per-player score tracking."""

    # actor_id is a plain str for dict-key compatibility; ActorId is a
    # NewType(str) so they are interchangeable at runtime.
    actor_id: str
    metrics: dict[str, float] = Field(default_factory=dict)
    total_score: float = 0.0
    eliminated: bool = False
    elimination_round: int | None = None

    def get_metric(self, name: str) -> float:
        """Return the value of a named metric, defaulting to 0.0."""
        return self.metrics.get(name, 0.0)

    def update_metrics(self, new_metrics: dict[str, float], weights: dict[str, float]) -> None:
        """Update metrics and recompute the weighted total score."""
        self.metrics.update(new_metrics)
        self.total_score = sum(
            self.metrics.get(name, 0.0) * weights.get(name, 1.0) for name in self.metrics
        )


class RoundState(BaseModel, frozen=True):
    """Immutable snapshot of current round state."""

    current_round: int = 0
    total_rounds: int = 10
    phase: str = "not_started"  # not_started, in_progress, between_rounds, completed

    def advance(self) -> RoundState:
        """Return a new state with the round counter incremented."""
        return RoundState(
            current_round=self.current_round + 1,
            total_rounds=self.total_rounds,
            phase="in_progress",
        )

    def end_round(self) -> RoundState:
        """Return a new state marking the current round as ended."""
        return RoundState(
            current_round=self.current_round,
            total_rounds=self.total_rounds,
            phase="between_rounds",
        )

    def complete(self) -> RoundState:
        """Return a new state marking the game as completed."""
        return RoundState(
            current_round=self.current_round,
            total_rounds=self.total_rounds,
            phase="completed",
        )


class WinResult(BaseModel, frozen=True):
    """Result of a win condition evaluation."""

    winner: str | None = None
    reason: str = ""
    final_standings: list[dict[str, Any]] = Field(default_factory=list)


class GameResult(BaseModel, frozen=True):
    """Final game result."""

    winner: str | None = None
    reason: str = ""
    total_rounds_played: int = 0
    final_standings: list[dict[str, Any]] = Field(default_factory=list)
    game_mode: str = "competition"
