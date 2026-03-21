"""Budget engine implementation.

Tracks per-actor resource budgets (API calls, LLM spend, world actions)
and enforces limits as a pipeline step.
"""

from __future__ import annotations

from typing import Any, ClassVar

from terrarium.core import (
    ActionContext,
    ActionCost,
    ActorId,
    BaseEngine,
    BudgetState,
    Event,
    PipelineStep,
    StepResult,
)


class BudgetEngine(BaseEngine):
    """Resource budget tracking and enforcement engine.

    Also acts as the ``budget`` pipeline step.
    """

    engine_name: ClassVar[str] = "budget"
    subscriptions: ClassVar[list[str]] = ["world"]
    dependencies: ClassVar[list[str]] = ["state"]

    # -- PipelineStep interface ------------------------------------------------

    @property
    def step_name(self) -> str:
        """Return the pipeline step name."""
        return "budget"

    async def execute(self, ctx: ActionContext) -> StepResult:
        """Execute the budget pipeline step."""
        ...

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Handle an inbound event from the bus."""
        ...

    # -- Budget operations -----------------------------------------------------

    async def check_budget(self, ctx: ActionContext) -> StepResult:
        """Check whether the actor's budget allows the proposed action."""
        ...

    async def deduct(self, actor_id: ActorId, cost: ActionCost) -> BudgetState:
        """Deduct resources from an actor's budget and return the new state."""
        ...

    async def get_remaining(self, actor_id: ActorId) -> BudgetState:
        """Return the actor's current remaining budget."""
        ...

    async def get_spend_curve(self, actor_id: ActorId) -> list[dict[str, Any]]:
        """Return a time-series of the actor's spend across budget dimensions."""
        ...
