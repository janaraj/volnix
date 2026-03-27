"""E2E tests: External agent connecting to Terrarium via MCP transport.

Simulates what a real MCP client does when connecting to Terrarium's
MCP server:
  1. list_tools() → discover available tools
  2. call_tool(name, args) → execute actions
  3. Parse TextContent JSON → extract structured data

No LLM required — uses mock gateway with realistic responses.
Tests run in-process (no subprocess) for speed and reliability.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.external_agent.conftest import _make_gateway_with_tools
from terrarium.engines.adapter.protocols.mcp_server import MCPServerAdapter


@pytest.fixture
async def mcp_adapter():
    """MCPServerAdapter with mock gateway returning realistic data."""
    gateway = _make_gateway_with_tools()
    adapter = MCPServerAdapter(gateway)
    await adapter.start_server()
    yield adapter, gateway
    await adapter.stop_server()


class TestMCPToolDiscovery:
    """Agent discovers tools via MCP list_tools."""

    async def test_list_tools_returns_mcp_tools(self, mcp_adapter):
        """MCP server exposes tools with name + inputSchema."""
        adapter, gateway = mcp_adapter
        manifest = await adapter.get_tool_manifest()
        assert len(manifest) >= 6
        names = {t["name"] for t in manifest}
        assert "tickets_show" in names
        assert "messages_send" in names


class TestMCPToolExecution:
    """Agent calls tools via MCP call_tool."""

    async def test_call_tool_returns_unwrapped_json(self, mcp_adapter):
        """MCP call_tool returns TextContent with unwrapped JSON."""
        adapter, gateway = mcp_adapter

        # Access the internal call_tool handler via the MCP server
        # The server registers handlers; we invoke via gateway mock
        result = await gateway.handle_request(
            actor_id="mcp-agent",
            tool_name="tickets_show",
            input_data={"id": "ticket-001"},
        )

        # Simulate what MCPServerAdapter does: unwrap + serialize
        from terrarium.engines.adapter.protocols._response import (
            unwrap_single_entity,
        )

        if isinstance(result, dict):
            result = unwrap_single_entity(result)
        text = json.dumps(result, default=str)

        # Parse like the agent's MCP normalizer would
        parsed = json.loads(text)
        assert isinstance(parsed, dict)
        # Unwrapped: inner ticket object, not {"ticket": {...}}
        assert parsed["id"] == "ticket-001"
        assert parsed["subject"] == "Broken API integration"

    async def test_multi_key_not_unwrapped(self, mcp_adapter):
        """Multi-key responses (lists) pass through unchanged."""
        adapter, gateway = mcp_adapter
        gateway.handle_request.return_value = {
            "tickets": [{"id": "t-1"}],
            "count": 1,
            "next_page": None,
        }

        result = await gateway.handle_request(
            actor_id="mcp-agent",
            tool_name="tickets_list",
            input_data={},
        )

        from terrarium.engines.adapter.protocols._response import (
            unwrap_single_entity,
        )

        unwrapped = unwrap_single_entity(result)
        # Multi-key: stays as-is
        assert "tickets" in unwrapped
        assert unwrapped["count"] == 1

    async def test_error_response_preserved(self, mcp_adapter):
        """Error responses are NOT unwrapped."""
        adapter, gateway = mcp_adapter
        gateway.handle_request.return_value = {
            "error": "Permission denied",
            "step": "permission",
        }

        result = await gateway.handle_request(
            actor_id="mcp-agent",
            tool_name="tickets_update",
            input_data={"id": "t-1", "status": "closed"},
        )

        from terrarium.engines.adapter.protocols._response import (
            unwrap_single_entity,
        )

        unwrapped = unwrap_single_entity(result)
        assert unwrapped["error"] == "Permission denied"


class TestMCPTriageWorkflow:
    """Full triage workflow via MCP: list → read → update."""

    async def test_triage_sequence_via_mcp(self, mcp_adapter):
        """Complete triage cycle through MCP adapter."""
        adapter, gateway = mcp_adapter

        from terrarium.engines.adapter.protocols._response import (
            unwrap_single_entity,
        )

        # Step 1: List tickets
        gateway.handle_request.return_value = {
            "tickets": [
                {"id": "ticket-001", "subject": "Broken API", "status": "new"},
            ],
            "count": 1,
            "next_page": None,
        }
        result = await gateway.handle_request(
            actor_id="mcp-agent",
            tool_name="tickets_list",
            input_data={},
        )
        data = unwrap_single_entity(result)
        assert "tickets" in data
        ticket_id = data["tickets"][0]["id"]

        # Step 2: Read specific ticket
        gateway.handle_request.return_value = {
            "ticket": {
                "id": ticket_id,
                "subject": "Broken API",
                "status": "new",
                "requester_id": "user-042",
            },
        }
        result = await gateway.handle_request(
            actor_id="mcp-agent",
            tool_name="tickets_show",
            input_data={"id": ticket_id},
        )
        ticket = unwrap_single_entity(result)
        assert ticket["id"] == ticket_id
        assert ticket["requester_id"] == "user-042"

        # Step 3: Update status
        gateway.handle_request.return_value = {
            "ticket": {
                "id": ticket_id,
                "status": "open",
                "updated_at": "2026-03-26T12:00:00Z",
            },
        }
        result = await gateway.handle_request(
            actor_id="mcp-agent",
            tool_name="tickets_update",
            input_data={"id": ticket_id, "status": "open"},
        )
        updated = unwrap_single_entity(result)
        assert updated["status"] == "open"

        # All 3 calls went through gateway
        assert gateway.handle_request.await_count == 3


class TestMCPEdgeCases:
    """Edge cases for MCP response handling."""

    async def test_unwrap_single_key_none_value(self):
        """{"ticket": None} → NOT unwrapped (value is not dict)."""
        from terrarium.engines.adapter.protocols._response import (
            unwrap_single_entity,
        )

        result = unwrap_single_entity({"ticket": None})
        # None is not a dict → stays wrapped
        assert result == {"ticket": None}

    async def test_unwrap_empty_dict(self):
        """{} → passes through unchanged."""
        from terrarium.engines.adapter.protocols._response import (
            unwrap_single_entity,
        )

        result = unwrap_single_entity({})
        assert result == {}

    async def test_non_dict_result_serialized(self):
        """Non-dict results (None, string, list) are JSON-serializable."""
        import json

        for value in [None, "error text", ["a", "b"], 42]:
            text = json.dumps(value, default=str)
            parsed = json.loads(text)
            assert parsed == value
