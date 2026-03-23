"""Tests for terrarium.gateway.gateway -- request handling and tool discovery."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from terrarium.gateway.gateway import Gateway
from terrarium.gateway.config import GatewayConfig


def _make_mock_app(tools=None, handle_result=None):
    """Create a mock TerrariumApp with a working registry and pack setup."""
    app = MagicMock()

    # Mock ledger
    ledger = AsyncMock()
    ledger.append = AsyncMock(return_value=1)
    app.ledger = ledger

    # Mock pack registry on responder
    pack_registry = MagicMock()
    tool_list = tools or [
        {"name": "email_send", "pack_name": "email", "category": "communication",
         "description": "Send an email", "parameters": {}},
        {"name": "email_read", "pack_name": "email", "category": "communication",
         "description": "Read an email", "parameters": {}},
    ]
    pack_registry.list_tools.return_value = tool_list

    # Mock pack for manifest generation
    mock_pack = MagicMock()
    mock_pack.pack_name = "email"
    mock_pack.category = "communication"
    mock_pack.fidelity_tier = 1
    mock_pack.get_tools.return_value = [
        {"name": "email_send", "description": "Send an email",
         "parameters": {"type": "object", "properties": {}, "required": []}},
        {"name": "email_read", "description": "Read an email",
         "parameters": {"type": "object", "properties": {}, "required": []}},
    ]
    mock_pack.get_entity_schemas.return_value = {}
    mock_pack.get_state_machines.return_value = {}

    pack_registry.list_packs.return_value = [
        {"pack_name": "email", "category": "communication", "fidelity_tier": 1, "tools": ["email_send", "email_read"]},
    ]
    pack_registry.get_pack.return_value = mock_pack

    # Mock responder engine
    responder = MagicMock()
    responder._pack_registry = pack_registry

    # Mock registry.get()
    def registry_get(name):
        if name == "responder":
            return responder
        return MagicMock()

    app.registry = MagicMock()
    app.registry.get = registry_get

    # Mock handle_action
    result = handle_result or {"email_id": "email-abc123", "status": "sent"}
    app.handle_action = AsyncMock(return_value=result)

    return app


@pytest.mark.asyncio
async def test_gateway_initialize_discovers_tools():
    """Gateway discovers tools from PackRegistry during initialize()."""
    app = _make_mock_app()
    gw = Gateway(app=app, config=GatewayConfig())
    await gw.initialize()

    assert gw._started is True
    assert "email_send" in gw._tool_map
    assert "email_read" in gw._tool_map
    assert gw._tool_map["email_send"] == ("email", "email_send")


@pytest.mark.asyncio
async def test_gateway_handle_request_success():
    """Successful tool call goes through app.handle_action()."""
    expected = {"email_id": "email-abc123", "status": "sent"}
    app = _make_mock_app(handle_result=expected)
    gw = Gateway(app=app, config=GatewayConfig())
    await gw.initialize()

    result = await gw.handle_request(
        protocol="mcp",
        actor_id="agent-1",
        tool_name="email_send",
        arguments={"from_addr": "a@b.com", "to_addr": "c@d.com",
                    "subject": "test", "body": "hello"},
    )

    assert result == expected
    app.handle_action.assert_awaited_once()
    call_kwargs = app.handle_action.call_args.kwargs
    assert call_kwargs["actor_id"] == "agent-1"
    assert call_kwargs["service_id"] == "email"
    assert call_kwargs["action"] == "email_send"


@pytest.mark.asyncio
async def test_gateway_handle_request_capability_gap():
    """Unknown tool returns structured capability_gap response."""
    app = _make_mock_app()
    gw = Gateway(app=app, config=GatewayConfig())
    await gw.initialize()

    result = await gw.handle_request(
        protocol="http",
        actor_id="agent-1",
        tool_name="nonexistent_tool",
        arguments={},
    )

    assert result["status"] == "capability_not_available"
    assert "nonexistent_tool" in result["message"]
    assert "available_tools" in result
    # handle_action should NOT be called for missing tools
    app.handle_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_gateway_records_to_ledger():
    """Every request is recorded to the ledger."""
    app = _make_mock_app()
    gw = Gateway(app=app, config=GatewayConfig())
    await gw.initialize()

    await gw.handle_request(
        protocol="mcp",
        actor_id="agent-1",
        tool_name="email_send",
        arguments={},
    )

    app.ledger.append.assert_awaited()
    entry = app.ledger.append.call_args[0][0]
    assert entry.entry_type == "gateway_request"
    assert entry.protocol == "mcp"
    assert entry.action == "email_send"
    assert entry.response_status == "success"


@pytest.mark.asyncio
async def test_gateway_records_capability_gap_to_ledger():
    """Capability gaps are also recorded to the ledger."""
    app = _make_mock_app()
    gw = Gateway(app=app, config=GatewayConfig())
    await gw.initialize()

    await gw.handle_request(
        protocol="http",
        actor_id="agent-1",
        tool_name="nonexistent_tool",
        arguments={},
    )

    app.ledger.append.assert_awaited()
    entry = app.ledger.append.call_args[0][0]
    assert entry.response_status == "capability_gap"


@pytest.mark.asyncio
async def test_gateway_get_tool_manifest_mcp():
    """get_tool_manifest returns MCP-formatted tools."""
    app = _make_mock_app()
    gw = Gateway(app=app, config=GatewayConfig())
    await gw.initialize()

    tools = await gw.get_tool_manifest(protocol="mcp")

    assert len(tools) >= 2
    names = [t["name"] for t in tools]
    assert "email_send" in names
    assert "email_read" in names
    # MCP tools should have inputSchema
    for t in tools:
        assert "inputSchema" in t


@pytest.mark.asyncio
async def test_gateway_shutdown():
    """Gateway shutdown stops all adapters."""
    app = _make_mock_app()
    gw = Gateway(app=app, config=GatewayConfig())
    await gw.initialize()

    assert gw._started is True
    await gw.shutdown()
    assert gw._started is False


@pytest.mark.asyncio
async def test_gateway_handle_request_records_error():
    """Pipeline errors are recorded with 'error' status."""
    app = _make_mock_app(handle_result={"error": "Pipeline short-circuited"})
    gw = Gateway(app=app, config=GatewayConfig())
    await gw.initialize()

    result = await gw.handle_request(
        protocol="http",
        actor_id="agent-1",
        tool_name="email_send",
        arguments={},
    )

    assert "error" in result
    entry = app.ledger.append.call_args[0][0]
    assert entry.response_status == "error"


@pytest.mark.asyncio
async def test_gateway_no_ledger():
    """Gateway works even without a ledger (ledger is None)."""
    app = _make_mock_app()
    app.ledger = None
    gw = Gateway(app=app, config=GatewayConfig())
    await gw.initialize()

    # Should not raise
    result = await gw.handle_request(
        protocol="mcp",
        actor_id="agent-1",
        tool_name="email_send",
        arguments={},
    )
    assert "email_id" in result


@pytest.mark.asyncio
async def test_gateway_creates_adapters():
    """Gateway creates MCP and HTTP adapters during initialize()."""
    app = _make_mock_app()
    gw = Gateway(app=app, config=GatewayConfig())
    await gw.initialize()

    assert "mcp" in gw._adapters
    assert "http" in gw._adapters


# ── P0-2: Dynamic pack discovery tests ────────────────────────────


def _make_mock_pack(pack_name, category, tools):
    """Create a mock ServicePack with the given tools."""
    pack = MagicMock()
    pack.pack_name = pack_name
    pack.category = category
    pack.fidelity_tier = 1
    pack.get_tools.return_value = tools
    pack.get_entity_schemas.return_value = {}
    pack.get_state_machines.return_value = {}
    return pack


@pytest.mark.asyncio
async def test_new_pack_tools_appear_in_manifest_dynamically():
    """New packs registered in PackRegistry appear in get_tool_manifest() immediately."""
    app = _make_mock_app()
    gw = Gateway(app=app, config=GatewayConfig())
    await gw.initialize()

    # 1. Verify email tools are in manifest
    manifest = await gw.get_tool_manifest(protocol="mcp")
    tool_names = [t["name"] for t in manifest]
    assert "email_send" in tool_names
    assert "email_read" in tool_names

    # 2. Register a NEW calendar pack in the PackRegistry
    calendar_tools = [
        {"name": "calendar_create", "description": "Create a calendar event",
         "parameters": {"type": "object", "properties": {}, "required": []}},
        {"name": "calendar_list", "description": "List calendar events",
         "parameters": {"type": "object", "properties": {}, "required": []}},
    ]
    calendar_pack = _make_mock_pack("calendar", "productivity", calendar_tools)

    responder = app.registry.get("responder")
    pack_registry = responder._pack_registry

    # Add calendar pack to the registry
    pack_registry._packs["calendar"] = calendar_pack
    # Update list_packs to return both
    pack_registry.list_packs.return_value = [
        {"pack_name": "email", "category": "communication", "fidelity_tier": 1,
         "tools": ["email_send", "email_read"]},
        {"pack_name": "calendar", "category": "productivity", "fidelity_tier": 1,
         "tools": ["calendar_create", "calendar_list"]},
    ]
    pack_registry.get_pack.side_effect = lambda name: (
        calendar_pack if name == "calendar" else app.registry.get("responder")._pack_registry.get_pack.return_value
    )

    # 3. get_tool_manifest() should show new pack's tools WITHOUT re-init
    manifest2 = await gw.get_tool_manifest(protocol="mcp")
    tool_names2 = [t["name"] for t in manifest2]
    assert "calendar_create" in tool_names2
    assert "calendar_list" in tool_names2
    # Original tools still present
    assert "email_send" in tool_names2


@pytest.mark.asyncio
async def test_new_pack_tools_not_routable_until_tool_map_refreshed():
    """New pack tools appear in manifest but NOT in handle_request routing until _tool_map is updated.

    This tests an actual design limitation: _tool_map is built during initialize()
    and is cached. New tools show up in get_tool_manifest() (which queries PackRegistry
    each time) but handle_request() uses the cached _tool_map for routing.
    """
    app = _make_mock_app()
    gw = Gateway(app=app, config=GatewayConfig())
    await gw.initialize()

    # Verify existing tool IS routable
    assert "email_send" in gw._tool_map

    # Register a new tool in pack registry's list_tools
    responder = app.registry.get("responder")
    pack_registry = responder._pack_registry
    original_tools = pack_registry.list_tools.return_value
    pack_registry.list_tools.return_value = original_tools + [
        {"name": "calendar_create", "pack_name": "calendar",
         "category": "productivity", "description": "Create event", "parameters": {}},
    ]

    # The new tool is NOT in _tool_map (cached from initialize)
    assert "calendar_create" not in gw._tool_map

    # handle_request returns capability_gap for the new tool
    result = await gw.handle_request(
        protocol="mcp",
        actor_id="agent-1",
        tool_name="calendar_create",
        arguments={},
    )
    assert result["status"] == "capability_not_available"

    # After re-initialize, the tool map is rebuilt
    await gw.initialize()
    assert "calendar_create" in gw._tool_map


# ── P1-6: Error path tests for Gateway ────────────────────────────


@pytest.mark.asyncio
async def test_gateway_handle_request_empty_arguments():
    """Handle request with empty arguments dict succeeds (pack decides validation)."""
    expected = {"email_id": "email-empty", "status": "draft"}
    app = _make_mock_app(handle_result=expected)
    gw = Gateway(app=app, config=GatewayConfig())
    await gw.initialize()

    result = await gw.handle_request(
        protocol="mcp",
        actor_id="agent-1",
        tool_name="email_send",
        arguments={},
    )

    assert result == expected
    call_kwargs = app.handle_action.call_args.kwargs
    assert call_kwargs["input_data"] == {}


@pytest.mark.asyncio
async def test_gateway_handle_request_pipeline_error_dict():
    """Pipeline returning error dict is recorded as 'error' and forwarded."""
    error_result = {"error": "Validation failed: missing required field 'to_addr'"}
    app = _make_mock_app(handle_result=error_result)
    gw = Gateway(app=app, config=GatewayConfig())
    await gw.initialize()

    result = await gw.handle_request(
        protocol="http",
        actor_id="agent-1",
        tool_name="email_send",
        arguments={"from_addr": "a@b.com"},
    )

    assert "error" in result
    assert "to_addr" in result["error"]
    # Ledger should record error status
    entry = app.ledger.append.call_args[0][0]
    assert entry.response_status == "error"


@pytest.mark.asyncio
async def test_gateway_handle_request_missing_tool_fields():
    """Requesting a tool with no arguments and no actor_id still processes correctly."""
    expected = {"status": "ok"}
    app = _make_mock_app(handle_result=expected)
    gw = Gateway(app=app, config=GatewayConfig())
    await gw.initialize()

    result = await gw.handle_request(
        protocol="mcp",
        actor_id="",
        tool_name="email_send",
        arguments={},
    )

    assert result == expected
    call_kwargs = app.handle_action.call_args.kwargs
    assert call_kwargs["actor_id"] == ""
    assert call_kwargs["input_data"] == {}


@pytest.mark.asyncio
async def test_gateway_capability_gap_lists_available_tools():
    """Capability gap response includes all available tools for discovery."""
    app = _make_mock_app()
    gw = Gateway(app=app, config=GatewayConfig())
    await gw.initialize()

    result = await gw.handle_request(
        protocol="mcp",
        actor_id="agent-1",
        tool_name="nonexistent_tool",
        arguments={},
    )

    assert result["status"] == "capability_not_available"
    available = result["available_tools"]
    assert "email_send" in available
    assert "email_read" in available
    assert "nonexistent_tool" not in available
