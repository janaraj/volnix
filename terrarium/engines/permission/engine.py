"""Permission engine implementation.

Checks actor permissions, computes visibility scopes, and enforces
authority boundaries as a pipeline step.
"""

from __future__ import annotations

from typing import Any, ClassVar

from terrarium.core import (
    ActionContext,
    ActorId,
    BaseEngine,
    EntityId,
    Event,
    PipelineStep,
    StepResult,
)


class PermissionEngine(BaseEngine):
    """RBAC / capability-based permission engine.

    Also acts as the ``permission`` pipeline step.
    """

    engine_name: ClassVar[str] = "permission"
    subscriptions: ClassVar[list[str]] = []
    dependencies: ClassVar[list[str]] = ["state"]

    # -- PipelineStep interface ------------------------------------------------

    @property
    def step_name(self) -> str:
        """Return the pipeline step name."""
        return "permission"

    async def execute(self, ctx: ActionContext) -> StepResult:
        """Execute the permission pipeline step."""
        ...

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Handle an inbound event from the bus."""
        ...

    # -- Permission operations -------------------------------------------------

    async def check_permission(self, ctx: ActionContext) -> StepResult:
        """Check whether the actor in *ctx* is permitted to perform the action."""
        ...

    async def get_visible_entities(
        self, actor_id: ActorId, entity_type: str
    ) -> list[EntityId]:
        """Return entity IDs visible to the given actor for a type."""
        ...

    async def get_actor_permissions(self, actor_id: ActorId) -> dict[str, Any]:
        """Return the full permission set for an actor."""
        ...
