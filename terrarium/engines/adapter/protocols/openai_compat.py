"""Phase E2: OpenAI function calling compatibility. Not implemented in E1.

This adapter will translate OpenAI function-calling requests/responses
into Terrarium ActionContexts, allowing agents using the OpenAI SDK to
interact with a Terrarium world directly.
"""

from __future__ import annotations

from typing import Any, ClassVar

from terrarium.core import ActionContext, ActorId
from terrarium.engines.adapter.protocols.base import ProtocolAdapter


class OpenAICompatAdapter(ProtocolAdapter):
    """OpenAI function calling compatible endpoint."""

    protocol_name: ClassVar[str] = "openai"

    async def translate_inbound(self, raw_request: Any) -> ActionContext:
        """Translate an OpenAI function call into an ActionContext."""
        ...

    async def translate_outbound(self, ctx: ActionContext) -> Any:
        """Translate an ActionContext result into an OpenAI response."""
        ...

    async def get_tool_manifest(self, actor_id: ActorId) -> list[dict[str, Any]]:
        """Return tools in OpenAI function calling format."""
        ...

    async def start_server(self) -> None:
        """Start the OpenAI-compatible server."""
        ...

    async def stop_server(self) -> None:
        """Stop the OpenAI-compatible server."""
        ...
