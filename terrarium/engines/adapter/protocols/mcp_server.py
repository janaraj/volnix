"""MCP Server Adapter -- exposes Terrarium world tools as MCP tools.

When an agent connects as an MCP client, it sees all service pack tools
(email_send, email_read, etc.) as MCP tools. Tool calls go through the
Gateway -> Pipeline -> Pack handler -> Response.

Uses: mcp SDK (Server, stdio_server)
Uses: Gateway.handle_request() for all tool calls
Uses: Gateway.get_tool_manifest(protocol="mcp") for tool discovery
"""

from __future__ import annotations

import json
import logging
from typing import Any, ClassVar

from terrarium.core.types import ToolName
from terrarium.engines.adapter.protocols.base import ProtocolAdapter

logger = logging.getLogger(__name__)


class MCPServerAdapter(ProtocolAdapter):
    """Exposes Terrarium world as an MCP server."""

    protocol_name: ClassVar[str] = "mcp"

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway
        self._server: Any = None
        self._actor_id: str = "mcp-agent"  # Default, overridden by connection

    async def start_server(self) -> None:
        """Create MCP server with tool handlers."""
        from mcp.server import Server
        from mcp.types import TextContent, Tool

        server = Server("terrarium-world")

        gateway = self._gateway
        adapter_self = self

        @server.list_tools()
        async def list_tools() -> list[Tool]:
            """Return all tools available in this world."""
            raw_tools = await gateway.get_tool_manifest(
                actor_id=adapter_self._actor_id, protocol="mcp"
            )
            return [Tool(**t) for t in raw_tools]

        @server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            """Handle tool call -> Gateway -> Pipeline -> Response."""
            result = await gateway.handle_request(
                actor_id=adapter_self._actor_id,
                tool_name=name,
                input_data=arguments or {},
            )
            return [TextContent(
                type="text",
                text=json.dumps(result, default=str),
            )]

        self._server = server
        logger.info("MCP server created with tool handlers")

    async def run_stdio(self) -> None:
        """Run MCP server on stdio transport (for local agents)."""
        if not self._server:
            await self.start_server()
        from mcp.server.stdio import stdio_server
        async with stdio_server() as (read, write):
            await self._server.run(
                read, write, self._server.create_initialization_options()
            )

    async def stop_server(self) -> None:
        """Stop the MCP server."""
        self._server = None

    async def translate_inbound(
        self,
        tool_name: ToolName,
        raw_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Translate inbound. MCP SDK handles parsing; pass-through."""
        return raw_input

    async def translate_outbound(
        self,
        tool_name: ToolName,
        internal_response: dict[str, Any],
    ) -> dict[str, Any]:
        """Translate outbound. MCP SDK handles serialization; pass-through."""
        return internal_response

    async def get_tool_manifest(self) -> list[dict[str, Any]]:
        """Return tool manifest for the MCP protocol."""
        return await self._gateway.get_tool_manifest(protocol="mcp")
