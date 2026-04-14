"""GameScorer protocol — strategy pattern for behavioral vs competitive scoring.

This is the only contract the orchestrator depends on. Concrete
implementations live in ``behavioral.py`` and ``competitive.py``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from volnix.core.events import WorldEvent
from volnix.engines.game.definition import PlayerScore


class ScorerContext(BaseModel):
    """Context passed to the scorer on each committed game event.

    Frozen per DESIGN_PRINCIPLES.md. Mutable inner containers
    (``player_scores``) are owned by the caller — scorers mutate their
    entries in place but must not reassign the dict reference.

    Attributes:
        event: The committed WorldEvent for a game tool call.
        event_number: Monotonic 1-indexed counter of committed game events
            (maintained by the orchestrator). Competitive scorer uses this
            for the efficiency bonus: ``bonus = (max_events - event_number)
            * bonus_per_event``.
        state_engine: The state engine (for read-only queries). Scorers
            MUST NOT mutate state through this — pack handlers are the
            sole writers (MF1).
        player_scores: Mutable dict of PlayerScore — the scorer updates
            per-player entries in place.
        definition: The full GameDefinition (for reading
            flow.max_events, flow.bonus_per_event, negotiation_fields,
            and other game-wide config).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    event: WorldEvent
    event_number: int
    state_engine: Any  # StateEngineProtocol
    player_scores: dict[str, PlayerScore]
    definition: Any  # GameDefinition — Any to avoid circular import


@runtime_checkable
class GameScorer(Protocol):
    """Strategy protocol: score a game event and optionally settle on timeout.

    Concrete implementations: :class:`BehavioralScorer`,
    :class:`CompetitiveScorer`. The orchestrator selects at configure
    time based on :attr:`GameDefinition.scoring_mode`.

    Contract (MF1):

    - ``score_event`` and ``settle`` MAY read from ``state_engine`` but
      MUST NOT write entity state through it. The game service
      responder pack is the sole writer to game state.
    - Both methods mutate ``player_scores`` in place (this is the
      orchestrator's mutable local state).
    - ``settle`` is invoked ONLY from the Path B timeout termination
      path (wall_clock / stalemate / max_events / all_budgets_exhausted).
      On Path A natural win, ``settle`` is never called — deal scores
      are already final from ``score_event`` on the closing event.
    """

    async def score_event(self, ctx: ScorerContext) -> None:
        """Update ``ctx.player_scores`` based on this single committed event.

        Called once per committed game tool event.
        """
        ...

    async def settle(
        self,
        open_deals: list[dict[str, Any]],
        state_engine: Any,
        player_scores: dict[str, PlayerScore],
        definition: Any,
    ) -> None:
        """Finalize scores when the game times out.

        Called from Path B termination only. Behavioral and competitive
        modes implement this differently:

        - Behavioral: compute ``final_terms_match_state`` per player
          from current world state, write into
          ``player_score.behavior_metrics``.
        - Competitive: apply BATNA scores from ``negotiation_target_terms``
          entities to any party whose deal didn't close.
        """
        ...
