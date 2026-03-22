"""Policy engine implementation.

Evaluates governance policies against action contexts, enforcing holds,
blocks, escalations, and logging as configured.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from terrarium.core import (
    ActionContext,
    ActorId,
    BaseEngine,
    Event,
    PipelineStep,
    PolicyId,
    StepResult,
    StepVerdict,
)

logger = logging.getLogger(__name__)


class PolicyEngine(BaseEngine):
    """PASS-THROUGH (Phase F1): Returns ALLOW without policy evaluation.

    Also acts as the ``policy`` pipeline step.
    """

    engine_name: ClassVar[str] = "policy"
    subscriptions: ClassVar[list[str]] = ["approval"]
    dependencies: ClassVar[list[str]] = ["state"]

    # -- PipelineStep interface ------------------------------------------------

    @property
    def step_name(self) -> str:
        """Return the pipeline step name."""
        return "policy"

    async def execute(self, ctx: ActionContext) -> StepResult:
        """PASS-THROUGH (Phase F1): Returns ALLOW without policy evaluation.

        This is the correct Phase C behavior. When Phase F1 implements
        real governance, replace this method body with actual logic.
        The method signature and return type MUST NOT change.
        """
        logger.debug("%s: allowing action '%s' for actor '%s' (pass-through)",
                     self.step_name, ctx.action, ctx.actor_id)
        return StepResult(step_name=self.step_name, verdict=StepVerdict.ALLOW,
                          message="pass-through")

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """PASS-THROUGH (Phase F1): Logs event without processing."""
        logger.debug("%s: received event %s (pass-through)", self.engine_name, event.event_type)

    # -- Policy operations -----------------------------------------------------

    async def evaluate(self, ctx: ActionContext) -> StepResult:
        """Stub -- Phase F1 implementation."""
        ...

    async def get_active_policies(self) -> list[dict[str, Any]]:
        """Stub -- Phase F1 implementation."""
        ...

    async def resolve_hold(
        self, hold_id: str, approved: bool, approver: ActorId
    ) -> None:
        """Stub -- Phase F1 implementation."""
        ...

    async def add_policy(self, policy_def: dict[str, Any]) -> PolicyId:
        """Stub -- Phase F1 implementation."""
        ...

    async def remove_policy(self, policy_id: PolicyId) -> None:
        """Stub -- Phase F1 implementation."""
        ...
