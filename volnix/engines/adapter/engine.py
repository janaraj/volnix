"""Agent adapter engine implementation.

Translates between external agent protocols (MCP, ACP, OpenAI, Anthropic,
HTTP REST) and the internal Volnix action context.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from volnix.core import (
    ActionContext,
    ActorId,
    BaseEngine,
    CapabilityGapEvent,
    Event,
    PipelineStep,
    StepResult,
    StepVerdict,
)

logger = logging.getLogger(__name__)


class AgentAdapterEngine(BaseEngine):
    """Capability check pipeline step + protocol adapter engine.

    Checks PackRegistry.has_tool() for requested actions.
    Returns ALLOW if the tool exists, ERROR with CapabilityGapEvent if not.
    """

    engine_name: ClassVar[str] = "adapter"
    subscriptions: ClassVar[list[str]] = []  # capability checks via pipeline step, not events
    dependencies: ClassVar[list[str]] = ["state", "permission"]

    # Injected by app._inject_cross_engine_deps()
    _pack_registry: Any = None
    _profile_registry: Any = None  # ProfileRegistry for Tier 2 tools

    # -- PipelineStep interface ------------------------------------------------

    @property
    def step_name(self) -> str:
        """Return the pipeline step name."""
        return "capability"

    async def execute(self, ctx: ActionContext) -> StepResult:
        """Check if the requested tool exists in the world.

        Uses PackRegistry.has_tool() when available.
        Falls back to ALLOW when pack_registry is not yet injected
        (backward compat with tests that don't wire the full app).
        """
        if self._pack_registry is not None:
            # Check Tier 1 packs
            if self._pack_registry.has_tool(ctx.action):
                logger.debug(
                    "%s: tool '%s' found (tier1) for actor '%s'",
                    self.step_name, ctx.action, ctx.actor_id,
                )
                return StepResult(
                    step_name=self.step_name,
                    verdict=StepVerdict.ALLOW,
                    message=f"tool '{ctx.action}' available (tier1)",
                )

            # Check Tier 2 profiles
            if self._profile_registry is not None:
                profile = self._profile_registry.get_profile_for_action(ctx.action)
                if profile is not None:
                    logger.debug(
                        "%s: tool '%s' found (tier2, profile=%s) for actor '%s'",
                        self.step_name, ctx.action, profile.service_name, ctx.actor_id,
                    )
                    return StepResult(
                        step_name=self.step_name,
                        verdict=StepVerdict.ALLOW,
                        message=f"tool '{ctx.action}' available (tier2, profile={profile.service_name})",
                    )

            # Capability gap
            logger.info(
                "%s: capability gap — tool '%s' not found for actor '%s'",
                self.step_name, ctx.action, ctx.actor_id,
            )
            from volnix.core.types import Timestamp, ToolName
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)

            gap_event = CapabilityGapEvent(
                event_type="capability.gap",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                actor_id=ctx.actor_id,
                requested_tool=ToolName(ctx.action),
                input_data=ctx.input_data,
            )
            return StepResult(
                step_name=self.step_name,
                verdict=StepVerdict.ERROR,
                message=f"Tool '{ctx.action}' is not available in this world",
                events=[gap_event],
            )

        # No pack registry injected yet — pass-through for backward compat
        logger.debug(
            "%s: allowing action '%s' for actor '%s' (no pack registry)",
            self.step_name, ctx.action, ctx.actor_id,
        )
        return StepResult(
            step_name=self.step_name,
            verdict=StepVerdict.ALLOW,
            message="pass-through (no pack registry)",
        )

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Log event without processing."""
        logger.debug(
            "%s: received event %s", self.engine_name, event.event_type
        )

    # -- Adapter operations ----------------------------------------------------

    async def translate_inbound(
        self, raw_request: Any, protocol: str
    ) -> ActionContext:
        """Stub -- delegated to protocol adapters."""
        ...

    async def translate_outbound(
        self, result: ActionContext, protocol: str
    ) -> Any:
        """Stub -- delegated to protocol adapters."""
        ...

    async def get_tool_manifest(
        self, actor_id: ActorId, protocol: str
    ) -> list[dict[str, Any]]:
        """Stub -- delegated to protocol adapters."""
        ...
