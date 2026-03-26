"""Tests for terrarium.engines.adapter.protocols.mcp_server -- MCP protocol.

Tests use the REAL MCP server object by verifying registered handlers and
testing through the gateway delegation pattern.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from terrarium.engines.adapter.protocols.mcp_server import MCPServerAdapter


def _make_mock_gateway(tools=None, handle_result=None):
    """Create a mock Gateway for testing MCP adapter."""
    gateway = MagicMock()

    mcp_tools = tools or [
        {"name": "email_send", "description": "Send an email",
         "inputSchema": {"type": "object", "properties": {}, "required": []}},
        {"name": "email_read", "description": "Read an email",
         "inputSchema": {"type": "object", "properties": {}, "required": []}},
    ]
    gateway.get_tool_manifest = AsyncMock(return_value=mcp_tools)

    result = handle_result or {"email_id": "email-abc123", "status": "sent"}
    gateway.handle_request = AsyncMock(return_value=result)

    return gateway


@pytest.mark.asyncio
async def test_mcp_server_adapter_init():
    """MCPServerAdapter can be instantiated with a gateway."""
    gateway = _make_mock_gateway()
    adapter = MCPServerAdapter(gateway)
    assert adapter.protocol_name == "mcp"
    assert adapter._server is None


@pytest.mark.asyncio
async def test_mcp_server_start_creates_server():
    """start_server() creates an MCP Server instance."""
    gateway = _make_mock_gateway()
    adapter = MCPServerAdapter(gateway)
    await adapter.start_server()

    assert adapter._server is not None
    assert adapter._server.name == "terrarium-world"


@pytest.mark.asyncio
async def test_mcp_list_tools_handler_registered():
    """list_tools handler is registered on the MCP server."""
    gateway = _make_mock_gateway()
    adapter = MCPServerAdapter(gateway)
    await adapter.start_server()

    from mcp.types import ListToolsRequest
    assert ListToolsRequest in adapter._server.request_handlers


@pytest.mark.asyncio
async def test_mcp_call_tool_handler_registered():
    """call_tool handler is registered on the MCP server."""
    gateway = _make_mock_gateway()
    adapter = MCPServerAdapter(gateway)
    await adapter.start_server()

    from mcp.types import CallToolRequest
    assert CallToolRequest in adapter._server.request_handlers


@pytest.mark.asyncio
async def test_mcp_get_tool_manifest():
    """get_tool_manifest delegates to gateway."""
    gateway = _make_mock_gateway()
    adapter = MCPServerAdapter(gateway)

    manifest = await adapter.get_tool_manifest()
    assert len(manifest) == 2
    names = [t["name"] for t in manifest]
    assert "email_send" in names
    assert "email_read" in names
    gateway.get_tool_manifest.assert_awaited_with(protocol="mcp")


@pytest.mark.asyncio
async def test_mcp_gateway_handle_request_delegation():
    """Verify gateway.handle_request is called correctly for MCP tool calls."""
    expected = {"email_id": "email-abc123", "status": "sent"}
    gateway = _make_mock_gateway(handle_result=expected)
    adapter = MCPServerAdapter(gateway)
    await adapter.start_server()

    # Simulate what the call_tool handler does
    result = await gateway.handle_request(
        actor_id=adapter._actor_id,
        tool_name="email_send",
        input_data={"from_addr": "a@b.com", "to_addr": "c@d.com"},
    )

    assert result == expected
    gateway.handle_request.assert_awaited_once_with(
        actor_id="mcp-agent",
        tool_name="email_send",
        input_data={"from_addr": "a@b.com", "to_addr": "c@d.com"},
    )


@pytest.mark.asyncio
async def test_mcp_stop_server():
    """stop_server() cleans up the MCP server."""
    gateway = _make_mock_gateway()
    adapter = MCPServerAdapter(gateway)
    await adapter.start_server()
    assert adapter._server is not None

    await adapter.stop_server()
    assert adapter._server is None


@pytest.mark.asyncio
async def test_mcp_translate_passthrough():
    """translate_inbound/outbound are pass-throughs for MCP (SDK handles it)."""
    gateway = _make_mock_gateway()
    adapter = MCPServerAdapter(gateway)
    result = await adapter.translate_inbound("tool", {"key": "val"})
    assert result == {"key": "val"}
    result = await adapter.translate_outbound("tool", {"resp": "data"})
    assert result == {"resp": "data"}


@pytest.mark.asyncio
async def test_mcp_actor_id_default():
    """Default actor_id is 'mcp-agent'."""
    gateway = _make_mock_gateway()
    adapter = MCPServerAdapter(gateway)
    assert adapter._actor_id == "mcp-agent"
