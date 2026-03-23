"""Phase E2: Anthropic tool use compatibility. Not implemented in E1.

This adapter will translate Anthropic tool-use requests/responses
into Terrarium ActionContexts, allowing agents using the Anthropic SDK to
interact with a Terrarium world directly.
"""

from __future__ import annotations

from typing import Any, ClassVar

from terrarium.core import ActionContext, ActorId
from terrarium.engines.adapter.protocols.base import ProtocolAdapter


class AnthropicCompatAdapter(ProtocolAdapter):
    """Anthropic tool use compatible endpoint."""

    protocol_name: ClassVar[str] = "anthropic"

    async def translate_inbound(self, raw_request: Any) -> ActionContext:
        """Translate an Anthropic tool use call into an ActionContext."""
        ...

    async def translate_outbound(self, ctx: ActionContext) -> Any:
        """Translate an ActionContext result into an Anthropic response."""
        ...

    async def get_tool_manifest(self, actor_id: ActorId) -> list[dict[str, Any]]:
        """Return tools in Anthropic tool use format."""
        ...

    async def start_server(self) -> None:
        """Start the Anthropic-compatible server."""
        ...

    async def stop_server(self) -> None:
        """Stop the Anthropic-compatible server."""
        ...
