"""ACP server adapter.

Handles agent-to-agent communication via ACP. Routes messages through
world channels. Visibility rules enforced.
"""

from __future__ import annotations

from typing import Any, ClassVar

from terrarium.core import ActionContext, ActorId
from terrarium.engines.adapter.protocols.base import ProtocolAdapter


class ACPServerAdapter(ProtocolAdapter):
    """Handles agent-to-agent communication via ACP.

    Routes messages through world channels. Visibility rules enforced.
    """

    protocol_name: ClassVar[str] = "acp"

    async def translate_inbound(self, raw_request: Any) -> ActionContext:
        """Translate an ACP message into an ActionContext."""
        ...

    async def translate_outbound(self, ctx: ActionContext) -> Any:
        """Translate an ActionContext result into an ACP response."""
        ...

    async def get_tool_manifest(self, actor_id: ActorId) -> list[dict[str, Any]]:
        """Return the ACP tool manifest for an actor."""
        ...

    async def start_server(self) -> None:
        """Start the ACP server."""
        ...

    async def stop_server(self) -> None:
        """Stop the ACP server."""
        ...
