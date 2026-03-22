"""Budget engine implementation.

Tracks per-actor resource budgets (API calls, LLM spend, world actions)
and enforces limits as a pipeline step.
"""

from __future__ import annotations

import logging
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
    StepVerdict,
)

logger = logging.getLogger(__name__)


class BudgetEngine(BaseEngine):
    """PASS-THROUGH (Phase F2): Returns ALLOW without budget checks.

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
        """PASS-THROUGH (Phase F2): Returns ALLOW without budget checks.

        This is the correct Phase C behavior. When Phase F2 implements
        real governance, replace this method body with actual logic.
        The method signature and return type MUST NOT change.
        """
        logger.debug("%s: allowing action '%s' for actor '%s' (pass-through)",
                     self.step_name, ctx.action, ctx.actor_id)
        return StepResult(step_name=self.step_name, verdict=StepVerdict.ALLOW,
                          message="pass-through")

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """PASS-THROUGH (Phase F2): Logs event without processing."""
        logger.debug("%s: received event %s (pass-through)", self.engine_name, event.event_type)

    # -- Budget operations -----------------------------------------------------

    async def check_budget(self, ctx: ActionContext) -> StepResult:
        """Stub -- Phase F2 implementation."""
        ...

    async def deduct(self, actor_id: ActorId, cost: ActionCost) -> BudgetState:
        """Stub -- Phase F2 implementation."""
        ...

    async def get_remaining(self, actor_id: ActorId) -> BudgetState:
        """Stub -- Phase F2 implementation."""
        ...

    async def get_spend_curve(self, actor_id: ActorId) -> list[dict[str, Any]]:
        """Stub -- Phase F2 implementation."""
        ...
