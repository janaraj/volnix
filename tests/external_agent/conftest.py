"""Shared fixtures for external agent E2E tests.

These tests verify that external agent frameworks can connect to
Terrarium via HTTP and MCP transports, discover tools, and execute
actions through the full 7-step governance pipeline.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from terrarium.engines.adapter.protocols.http_rest import HTTPRestAdapter


def _make_gateway_with_tools(
    *,
    tools: list[dict[str, Any]] | None = None,
    handle_result: dict[str, Any] | None = None,
):
    """Create a mock Gateway with realistic ticket/email tools."""
    from terrarium.core.context import StepResult
    from terrarium.core.types import StepVerdict

    gateway = MagicMock()

    mcp_tools = tools or [
        {
            "name": "zendesk_tickets_list",
            "description": "List tickets with optional filters",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "page": {"type": "integer"},
                },
            },
        },
        {
            "name": "zendesk_tickets_show",
            "description": "Show a single ticket by ID",
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        },
        {
            "name": "zendesk_tickets_update",
            "description": "Update ticket fields",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "status": {"type": "string"},
                },
                "required": ["id"],
            },
        },
        {
            "name": "zendesk_ticket_comments_create",
            "description": "Add a comment to a ticket",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "body": {"type": "string"},
                    "public": {"type": "boolean"},
                },
                "required": ["id", "body"],
            },
        },
        {
            "name": "zendesk_users_show",
            "description": "Show a user by ID",
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        },
        {
            "name": "send_gmail_message",
            "description": "Send an email message",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    ]
    gateway.get_tool_manifest = AsyncMock(return_value=mcp_tools)

    # Realistic ticket response (Zendesk-style wrapper)
    default_result = handle_result or {
        "ticket": {
            "id": "ticket-001",
            "subject": "Broken API integration",
            "status": "open",
            "requester_id": "user-042",
            "priority": "high",
            "created_at": "2026-03-23T10:00:00Z",
            "updated_at": "2026-03-23T10:00:00Z",
        },
    }
    gateway.handle_request = AsyncMock(return_value=default_result)

    # Mock app internals
    permission_engine = AsyncMock()
    permission_engine.execute = AsyncMock(
        return_value=StepResult(step_name="permission", verdict=StepVerdict.ALLOW)
    )
    registry = MagicMock()
    registry.get = MagicMock(return_value=permission_engine)

    bus = MagicMock()
    bus.subscribe = AsyncMock()
    bus.unsubscribe = AsyncMock()

    mock_app = MagicMock()
    mock_app.registry = registry
    mock_app.bus = bus
    gateway._app = mock_app

    return gateway


@pytest.fixture
async def terrarium_http_adapter():
    """HTTPRestAdapter with mock gateway returning realistic ticket data."""
    gateway = _make_gateway_with_tools()
    adapter = HTTPRestAdapter(gateway)
    await adapter.start_server()
    yield adapter, gateway
    await adapter.stop_server()


@pytest.fixture
def http_transport(terrarium_http_adapter):
    """httpx ASGITransport for direct ASGI testing (no real server)."""
    adapter, _gw = terrarium_http_adapter
    return httpx.ASGITransport(app=adapter.fastapi_app)
