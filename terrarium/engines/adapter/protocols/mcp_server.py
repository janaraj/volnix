"""MCP server adapter.

Exposes world services as MCP tools. Uses mcp Python SDK in server mode.
Agents connect as MCP clients.
"""

from __future__ import annotations

from typing import Any, ClassVar

from terrarium.core import ActionContext, ActorId
from terrarium.engines.adapter.protocols.base import ProtocolAdapter


class MCPServerAdapter(ProtocolAdapter):
    """Exposes world services as MCP tools.

    Uses mcp Python SDK in server mode. Agents connect as MCP clients.
    """

    protocol_name: ClassVar[str] = "mcp"

    async def translate_inbound(self, raw_request: Any) -> ActionContext:
        """Translate an MCP tool call into an ActionContext."""
        ...

    async def translate_outbound(self, ctx: ActionContext) -> Any:
        """Translate an ActionContext result into an MCP response."""
        ...

    async def get_tool_manifest(self, actor_id: ActorId) -> list[dict[str, Any]]:
        """Return the MCP tool manifest for an actor."""
        ...

    async def start_server(self) -> None:
        """Start the MCP server."""
        ...

    async def stop_server(self) -> None:
        """Stop the MCP server."""
        ...
