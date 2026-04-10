"""Game engine extension protocols — scoring providers, win condition handlers, turn protocols.

Defines the Protocol interfaces and context models for the game engine's
pluggable extension points. Implementations register in module-level
registries (scorer.py, win_conditions.py, runner.py).

These protocols are game-engine-internal contracts, not cross-engine
interfaces. They live here (not in core/protocols.py) because they import
game-specific types.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from volnix.engines.game.definition import (
    PlayerScore,
    RoundState,
    ScoringMetric,
    WinCondition,
    WinResult,
)

# ---------------------------------------------------------------------------
# Context models (frozen Pydantic — passed to providers/handlers)
# ---------------------------------------------------------------------------


class ScoringContext(BaseModel):
    """Context passed to scoring providers."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    player_id: str
    metric: ScoringMetric
    state_engine: Any = None  # StateEngineProtocol | None
    events: list[Any] = Field(default_factory=list)
    resolved_entity_types: dict[str, str] = Field(default_factory=dict)


class WinConditionContext(BaseModel):
    """Context passed to win condition handlers."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    condition: WinCondition
    scores: dict[str, PlayerScore] = Field(default_factory=dict)
    round_state: RoundState = Field(default_factory=RoundState)


# ---------------------------------------------------------------------------
# Extension protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class ScoringProvider(Protocol):
    """Protocol for scoring metric computation.

    Implementations compute a single metric value for a single player.
    Registered by source name (e.g., "state", "events", "judge").
    """

    async def compute(self, ctx: ScoringContext) -> float: ...


@runtime_checkable
class WinConditionHandler(Protocol):
    """Protocol for win condition evaluation.

    Implementations check one condition type against current scores.
    Registered by condition type (e.g., "score_threshold", "elimination").
    """

    def check(self, ctx: WinConditionContext) -> WinResult | None: ...


@runtime_checkable
class TurnProtocol(Protocol):
    """Protocol for round execution strategy.

    Controls how players are activated during a round (sequential, simultaneous,
    paired, phased, etc.). Registered by protocol name (e.g., "independent").
    """

    async def execute_round(
        self,
        active_players: list[str],
        actions_per_turn: int,
        activate_fn: Callable[[str, int], Awaitable[None]],
    ) -> None: ...


@runtime_checkable
class RoundEvaluator(Protocol):
    """Protocol for game-type-specific between-rounds evaluation.

    Runs after player turns but before scoring. Used by game types that need
    to parse/process turn results into scorable state (e.g., negotiation
    evaluator parses proposal messages into deal entities).
    """

    async def evaluate(
        self,
        state_engine: Any,
        round_events: list[Any],
        round_state: RoundState,
        player_scores: dict[str, PlayerScore],
    ) -> None: ...

    async def build_deliverable_extras(self, state_engine: Any) -> dict[str, Any]:
        """Return game-type-specific data to merge into the run deliverable.

        Called once by the runner after ``complete_game()``. Evaluators may
        query state entities to summarize outcomes (e.g., accepted deals,
        auction bids, debate verdicts). The returned dict is flat and merged
        into the deliverable alongside standings. Default implementation
        returns an empty dict; override in concrete evaluators that have
        meaningful per-game-type summaries.
        """
        return {}

    def game_tools(self) -> list[Any]:
        """Return the structured game-move tools for this game type.

        The runner registers these with the agency engine at game start so
        the LLM can call them as native structured tool calls. Each tool is
        a :class:`~volnix.llm.types.ToolDefinition` whose parameters define
        the move's JSON Schema — the LLM provider enforces validation so
        the evaluator never sees malformed data. Default: no tools (game
        types that rely only on chat / state changes).

        Typed as ``list[Any]`` at the Protocol boundary to avoid a forward
        import of ``ToolDefinition`` into ``engines/game/`` — concrete
        evaluators return properly typed ``list[ToolDefinition]``.
        """
        return []
