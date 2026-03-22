"""Permission engine implementation.

Checks actor permissions, computes visibility scopes, and enforces
authority boundaries as a pipeline step.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from terrarium.core import (
    ActionContext,
    ActorId,
    BaseEngine,
    EntityId,
    Event,
    PipelineStep,
    StepResult,
    StepVerdict,
)

logger = logging.getLogger(__name__)


class PermissionEngine(BaseEngine):
    """PASS-THROUGH (Phase F2): Returns ALLOW without checks.

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
        """PASS-THROUGH (Phase F2): Returns ALLOW without checks.

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

    # -- Permission operations -------------------------------------------------

    async def check_permission(self, ctx: ActionContext) -> StepResult:
        """Stub -- Phase F2 implementation."""
        ...

    async def get_visible_entities(
        self, actor_id: ActorId, entity_type: str
    ) -> list[EntityId]:
        """Stub -- Phase F2 implementation."""
        ...

    async def get_actor_permissions(self, actor_id: ActorId) -> dict[str, Any]:
        """Stub -- Phase F2 implementation."""
        ...
