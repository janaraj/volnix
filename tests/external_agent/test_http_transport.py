"""E2E tests: External agent connecting to Volnix via HTTP transport.

Simulates what a real agent framework (agent-ecosystem, LangGraph, AutoGen)
does when connecting to Volnix's HTTP API:
  1. GET /api/v1/tools → discover available tools
  2. POST /api/v1/actions/{name} with raw arguments → execute actions
  3. Parse envelope response → extract structured_content

No LLM required — uses mock gateway with realistic Zendesk/Gmail responses.
"""
from __future__ import annotations

import json

import httpx
import pytest

from tests.external_agent.conftest import _make_gateway_with_tools
from volnix.engines.adapter.protocols.http_rest import HTTPRestAdapter


class TestToolDiscovery:
    """Agent discovers tools via GET /api/v1/tools."""

    async def test_discover_tools_returns_list(self, http_transport):
        """GET /api/v1/tools returns a list of tool definitions."""
        async with httpx.AsyncClient(
            transport=http_transport, base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/tools")

        assert resp.status_code == 200
        tools = resp.json()
        assert isinstance(tools, list)
        assert len(tools) >= 6

    async def test_tools_have_mcp_schema(self, http_transport):
        """Each tool has name, description, and inputSchema."""
        async with httpx.AsyncClient(
            transport=http_transport, base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/tools")

        tools = resp.json()
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool

    async def test_expected_tools_present(self, http_transport):
        """Volnix exposes the Zendesk/Gmail tools we need."""
        async with httpx.AsyncClient(
            transport=http_transport, base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/tools")

        tool_names = {t["name"] for t in resp.json()}
        expected = {
            "tickets.list",
            "tickets.read",
            "tickets.update",
            "tickets.comment_create",
            "customers.read",
            "users.messages.send",
        }
        assert expected.issubset(tool_names)


class TestRawArgumentExecution:
    """Agent sends raw arguments (standard tool transport protocol)."""

    async def test_raw_args_auto_detected(self, http_transport):
        """POST with raw args (no wrapper) is accepted."""
        async with httpx.AsyncClient(
            transport=http_transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/actions/tickets.read",
                json={"id": "ticket-001"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "structured_content" in data
        assert "is_error" in data

    async def test_single_entity_unwrapped(self, http_transport):
        """Single-entity responses are unwrapped from Zendesk wrapper."""
        async with httpx.AsyncClient(
            transport=http_transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/actions/tickets.read",
                json={"id": "ticket-001"},
            )

        data = resp.json()
        sc = data["structured_content"]
        # Should be the inner ticket object, not {"ticket": {...}}
        assert sc["id"] == "ticket-001"
        assert sc["subject"] == "Broken API integration"
        assert sc["status"] == "open"

    async def test_error_response_sets_is_error(self, volnix_http_adapter):
        """Pipeline errors set is_error=True in envelope."""
        adapter, gateway = volnix_http_adapter
        gateway.handle_request = pytest.importorskip("unittest.mock").AsyncMock(
            return_value={"error": "Blocked by policy", "step": "policy"}
        )
        transport = httpx.ASGITransport(app=adapter.fastapi_app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/actions/tickets.update",
                json={"id": "ticket-001", "status": "closed"},
            )

        data = resp.json()
        assert data["is_error"] is True

    async def test_multi_key_response_not_unwrapped(self, volnix_http_adapter):
        """Multi-key responses (lists) are NOT unwrapped."""
        adapter, gateway = volnix_http_adapter
        gateway.handle_request = pytest.importorskip("unittest.mock").AsyncMock(
            return_value={
                "tickets": [{"id": "t-1"}, {"id": "t-2"}],
                "count": 2,
                "next_page": None,
            }
        )
        transport = httpx.ASGITransport(app=adapter.fastapi_app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/actions/tickets.list",
                json={},
            )

        data = resp.json()
        assert "tickets" in data["structured_content"]
        assert data["structured_content"]["count"] == 2

    async def test_actor_id_from_header(self, volnix_http_adapter):
        """X-Actor-Id header sets the actor for pipeline execution."""
        adapter, gateway = volnix_http_adapter
        transport = httpx.ASGITransport(app=adapter.fastapi_app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            await client.post(
                "/api/v1/actions/tickets.read",
                json={"id": "ticket-001"},
                headers={"x-actor-id": "triage-agent-42"},
            )

        call_kwargs = gateway.handle_request.call_args.kwargs
        assert call_kwargs["actor_id"] == "triage-agent-42"


class TestBackwardCompatibility:
    """Existing SDK clients using wrapped format are unaffected."""

    async def test_wrapped_format_returns_raw_response(self, http_transport, volnix_http_adapter):
        """Wrapped requests get raw response (no envelope)."""
        _, gateway = volnix_http_adapter

        async with httpx.AsyncClient(
            transport=http_transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/actions/tickets.read",
                json={
                    "actor_id": "sdk-agent",
                    "arguments": {"id": "ticket-001"},
                },
            )

        data = resp.json()
        # Wrapped mode: raw Zendesk response, NOT envelope
        assert "ticket" in data
        assert "structured_content" not in data

    async def test_wrapped_format_forwards_actor_id(self, http_transport, volnix_http_adapter):
        """Wrapped requests use actor_id from body."""
        _, gateway = volnix_http_adapter

        async with httpx.AsyncClient(
            transport=http_transport, base_url="http://test"
        ) as client:
            await client.post(
                "/api/v1/actions/tickets.read",
                json={
                    "actor_id": "sdk-agent-99",
                    "arguments": {"id": "ticket-001"},
                },
            )

        call_kwargs = gateway.handle_request.call_args.kwargs
        assert call_kwargs["actor_id"] == "sdk-agent-99"


class TestTriageWorkflowHTTP:
    """Simulates a full triage workflow: list → read → update."""

    async def test_full_triage_sequence(self):
        """Agent lists tickets, reads one, updates status — all via raw HTTP."""
        # Step 1: List tickets
        list_result = {
            "tickets": [
                {"id": "ticket-001", "subject": "Broken API", "status": "new"},
                {"id": "ticket-002", "subject": "Password reset", "status": "new"},
            ],
            "count": 2,
            "next_page": None,
        }
        gateway = _make_gateway_with_tools(handle_result=list_result)
        adapter = HTTPRestAdapter(gateway)
        await adapter.start_server()
        transport = httpx.ASGITransport(app=adapter.fastapi_app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/actions/tickets.list", json={}
            )
        assert resp.status_code == 200
        tickets = resp.json()["structured_content"]["tickets"]
        assert len(tickets) == 2

        # Step 2: Read a specific ticket
        show_result = {
            "ticket": {
                "id": "ticket-001",
                "subject": "Broken API",
                "status": "new",
                "requester_id": "user-042",
                "description": "Our API integration broke after the update.",
            },
        }
        gateway.handle_request.return_value = show_result

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/actions/tickets.read",
                json={"id": "ticket-001"},
            )
        assert resp.status_code == 200
        ticket = resp.json()["structured_content"]
        assert ticket["id"] == "ticket-001"
        assert ticket["requester_id"] == "user-042"

        # Step 3: Update ticket status
        update_result = {
            "ticket": {
                "id": "ticket-001",
                "status": "open",
                "updated_at": "2026-03-26T12:00:00Z",
            },
        }
        gateway.handle_request.return_value = update_result

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/actions/tickets.update",
                json={"id": "ticket-001", "status": "open"},
            )
        assert resp.status_code == 200
        updated = resp.json()["structured_content"]
        assert updated["status"] == "open"

        # Verify all 3 calls went through gateway
        assert gateway.handle_request.await_count == 3

        await adapter.stop_server()


class TestEdgeCasesAndFailures:
    """Edge cases, failure paths, and protocol boundary tests."""

    async def test_raw_mode_gateway_returns_none(self, volnix_http_adapter):
        """Gateway returning None → enveloped with is_error=True."""
        adapter, gateway = volnix_http_adapter
        gateway.handle_request = pytest.importorskip("unittest.mock").AsyncMock(
            return_value=None
        )
        transport = httpx.ASGITransport(app=adapter.fastapi_app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/actions/tickets.read",
                json={"id": "ticket-001"},
            )

        data = resp.json()
        assert data["structured_content"] is None
        assert data["is_error"] is True

    async def test_raw_mode_gateway_returns_string(self, volnix_http_adapter):
        """Gateway returning string → enveloped as structured_content."""
        adapter, gateway = volnix_http_adapter
        gateway.handle_request = pytest.importorskip("unittest.mock").AsyncMock(
            return_value="plain text error"
        )
        transport = httpx.ASGITransport(app=adapter.fastapi_app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/actions/some_tool", json={}
            )

        data = resp.json()
        assert data["structured_content"] == "plain text error"

    async def test_unwrap_single_key_none_value(self, volnix_http_adapter):
        """Single-key dict with None value → unwraps to None."""
        adapter, gateway = volnix_http_adapter
        gateway.handle_request = pytest.importorskip("unittest.mock").AsyncMock(
            return_value={"ticket": None}
        )
        transport = httpx.ASGITransport(app=adapter.fastapi_app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/actions/tickets.read", json={"id": "t-1"}
            )

        data = resp.json()
        # {"ticket": None} has one key, but value is not dict → no unwrap
        assert data["structured_content"] == {"ticket": None}

    async def test_unwrap_single_key_list_value(self, volnix_http_adapter):
        """Single-key dict with list value → NOT unwrapped (list, not dict)."""
        adapter, gateway = volnix_http_adapter
        gateway.handle_request = pytest.importorskip("unittest.mock").AsyncMock(
            return_value={"items": [1, 2, 3]}
        )
        transport = httpx.ASGITransport(app=adapter.fastapi_app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/actions/some_tool", json={}
            )

        data = resp.json()
        # Single key but value is list, not dict → NOT unwrapped
        assert data["structured_content"] == {"items": [1, 2, 3]}

    async def test_empty_dict_response(self, volnix_http_adapter):
        """Empty dict response → passed through as-is in envelope."""
        adapter, gateway = volnix_http_adapter
        gateway.handle_request = pytest.importorskip("unittest.mock").AsyncMock(
            return_value={}
        )
        transport = httpx.ASGITransport(app=adapter.fastapi_app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/actions/some_tool", json={}
            )

        data = resp.json()
        assert data["structured_content"] == {}
        assert data["is_error"] is False

    async def test_body_with_actor_id_field_uses_header(self, volnix_http_adapter):
        """Raw mode body containing 'actor_id' → header takes precedence."""
        adapter, gateway = volnix_http_adapter
        transport = httpx.ASGITransport(app=adapter.fastapi_app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            await client.post(
                "/api/v1/actions/tickets.read",
                json={"id": "t-1", "actor_id": "impersonator"},
                headers={"x-actor-id": "real-agent"},
            )

        call_kwargs = gateway.handle_request.call_args.kwargs
        assert call_kwargs["actor_id"] == "real-agent"

    async def test_wrapped_with_extra_fields_still_wrapped(self, volnix_http_adapter):
        """Wrapped request with extra fields → still treated as wrapped."""
        adapter, gateway = volnix_http_adapter
        transport = httpx.ASGITransport(app=adapter.fastapi_app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/actions/tickets.read",
                json={
                    "actor_id": "agent-1",
                    "arguments": {"id": "t-1"},
                    "extra_field": "ignored",
                },
            )

        assert resp.status_code == 200
        # Wrapped mode: no envelope
        assert "structured_content" not in resp.json()

    async def test_empty_body_raw_mode(self, volnix_http_adapter):
        """Empty body {} → raw mode, default actor."""
        adapter, gateway = volnix_http_adapter
        transport = httpx.ASGITransport(app=adapter.fastapi_app)

        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/actions/tickets.list", json={}
            )

        assert resp.status_code == 200
        call_kwargs = gateway.handle_request.call_args.kwargs
        assert call_kwargs["actor_id"] == "http-agent"
        assert call_kwargs["input_data"] == {}
