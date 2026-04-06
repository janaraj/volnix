"""Test harness for SDK, adapters, and config export.

Provides reusable fixtures for testing the Volnix SDK layer
against mocked HTTP servers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

# -- Sample data ---------------------------------------------------------------

SAMPLE_TOOLS_MCP = [
    {
        "name": "email_send",
        "description": "Send an email",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "body"],
        },
    },
    {
        "name": "tickets.update",
        "description": "Update a ticket status",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "status": {"type": "string"},
            },
            "required": ["ticket_id"],
        },
    },
]

SAMPLE_ACTION_RESULT = {"email_id": "e-123", "status": "sent"}


# -- Fixtures ------------------------------------------------------------------


@pytest.fixture
def mock_gateway():
    """Mock gateway returning sample tools and action results."""
    gw = MagicMock()
    gw.get_tool_manifest = AsyncMock(return_value=SAMPLE_TOOLS_MCP)
    gw.handle_request = AsyncMock(return_value=SAMPLE_ACTION_RESULT)
    gw._adapters = {}  # No MCP adapter for SSE tests

    mock_app = MagicMock()
    mock_app.bus = MagicMock()
    mock_app.bus.subscribe = AsyncMock()
    mock_app.read_entities = AsyncMock(
        return_value={
            "entity_type": "email",
            "count": 0,
            "entities": [],
        }
    )
    gw._app = mock_app
    return gw


@pytest.fixture
async def test_adapter(mock_gateway):
    """Running HTTP adapter with mock gateway."""
    from volnix.engines.adapter.protocols.http_rest import (
        HTTPRestAdapter,
    )

    adapter = HTTPRestAdapter(mock_gateway)
    await adapter.start_server()
    yield adapter
    await adapter.stop_server()


@pytest.fixture
def transport(test_adapter):
    """httpx ASGITransport for testing against the adapter."""
    import httpx

    return httpx.ASGITransport(app=test_adapter.fastapi_app)
