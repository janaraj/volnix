"""Agent adapter engine implementation.

Translates between external agent protocols (MCP, ACP, OpenAI, Anthropic,
HTTP REST) and the internal Terrarium action context.
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
    StepResult,
    StepVerdict,
)

logger = logging.getLogger(__name__)


class AgentAdapterEngine(BaseEngine):
    """PASS-THROUGH (Phase E1): Returns ALLOW without capability checks.

    Also acts as the ``capability`` pipeline step.
    """

    engine_name: ClassVar[str] = "adapter"
    subscriptions: ClassVar[list[str]] = ["world"]
    dependencies: ClassVar[list[str]] = ["state", "permission"]

    # -- PipelineStep interface ------------------------------------------------

    @property
    def step_name(self) -> str:
        """Return the pipeline step name."""
        return "capability"

    async def execute(self, ctx: ActionContext) -> StepResult:
        """PASS-THROUGH (Phase E1): Returns ALLOW without capability checks.

        This is the correct Phase C behavior. When Phase E1 implements
        real governance, replace this method body with actual logic.
        The method signature and return type MUST NOT change.
        """
        logger.debug("%s: allowing action '%s' for actor '%s' (pass-through)",
                     self.step_name, ctx.action, ctx.actor_id)
        return StepResult(step_name=self.step_name, verdict=StepVerdict.ALLOW,
                          message="pass-through")

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """PASS-THROUGH (Phase E1): Logs event without processing."""
        logger.debug("%s: received event %s (pass-through)", self.engine_name, event.event_type)

    # -- Adapter operations ----------------------------------------------------

    async def translate_inbound(
        self, raw_request: Any, protocol: str
    ) -> ActionContext:
        """Stub -- Phase E1 implementation."""
        ...

    async def translate_outbound(
        self, result: ActionContext, protocol: str
    ) -> Any:
        """Stub -- Phase E1 implementation."""
        ...

    async def get_tool_manifest(
        self, actor_id: ActorId, protocol: str
    ) -> list[dict[str, Any]]:
        """Stub -- Phase E1 implementation."""
        ...
