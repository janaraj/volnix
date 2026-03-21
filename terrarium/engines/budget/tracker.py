"""Budget tracker -- low-level budget bookkeeping."""

from __future__ import annotations

from typing import Any

from terrarium.core import ActionCost, ActorId, BudgetState, Event, StateEngineProtocol


class BudgetTracker:
    """Manages per-actor budget state and threshold checks."""

    def __init__(self, state: StateEngineProtocol) -> None:
        self._state = state

    async def initialize_budgets(self, actors: list[dict[str, Any]]) -> None:
        """Initialize budget records for a list of actors."""
        ...

    async def get_budget(self, actor_id: ActorId) -> BudgetState:
        """Retrieve the current budget state for an actor."""
        ...

    async def deduct(self, actor_id: ActorId, cost: ActionCost) -> BudgetState:
        """Deduct a cost and return the updated budget state."""
        ...

    async def check_thresholds(self, actor_id: ActorId) -> list[Event]:
        """Check budget thresholds and return warning/critical/exhausted events."""
        ...

    async def get_spend_history(self, actor_id: ActorId) -> list[dict[str, Any]]:
        """Return the chronological spend history for an actor."""
        ...
