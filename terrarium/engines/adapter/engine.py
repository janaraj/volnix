"""Agent adapter engine implementation.

Translates between external agent protocols (MCP, ACP, OpenAI, Anthropic,
HTTP REST) and the internal Terrarium action context.
"""

from __future__ import annotations

from typing import Any, ClassVar

from terrarium.core import (
    ActionContext,
    ActorId,
    BaseEngine,
    Event,
    PipelineStep,
    StepResult,
)


class AgentAdapterEngine(BaseEngine):
    """Protocol translation and capability exposure engine.

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
        """Execute the capability pipeline step."""
        ...

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Handle an inbound event from the bus."""
        ...

    # -- Adapter operations ----------------------------------------------------

    async def translate_inbound(
        self, raw_request: Any, protocol: str
    ) -> ActionContext:
        """Translate a raw external request into an ActionContext."""
        ...

    async def translate_outbound(
        self, result: ActionContext, protocol: str
    ) -> Any:
        """Translate an ActionContext result back to the external protocol."""
        ...

    async def get_tool_manifest(
        self, actor_id: ActorId, protocol: str
    ) -> list[dict[str, Any]]:
        """Return the tool manifest for an actor in the given protocol format."""
        ...
