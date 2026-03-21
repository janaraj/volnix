"""Policy engine implementation.

Evaluates governance policies against action contexts, enforcing holds,
blocks, escalations, and logging as configured.
"""

from __future__ import annotations

from typing import Any, ClassVar

from terrarium.core import (
    ActionContext,
    ActorId,
    BaseEngine,
    Event,
    PipelineStep,
    PolicyId,
    StepResult,
)


class PolicyEngine(BaseEngine):
    """Governance policy evaluation and enforcement engine.

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
        """Execute the policy pipeline step."""
        ...

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Handle an inbound event from the bus."""
        ...

    # -- Policy operations -----------------------------------------------------

    async def evaluate(self, ctx: ActionContext) -> StepResult:
        """Evaluate all active policies against the action context."""
        ...

    async def get_active_policies(self) -> list[dict[str, Any]]:
        """Return all currently active policies."""
        ...

    async def resolve_hold(
        self, hold_id: str, approved: bool, approver: ActorId
    ) -> None:
        """Resolve a held action by approving or rejecting it."""
        ...

    async def add_policy(self, policy_def: dict[str, Any]) -> PolicyId:
        """Register a new policy at runtime."""
        ...

    async def remove_policy(self, policy_id: PolicyId) -> None:
        """Remove an active policy."""
        ...
