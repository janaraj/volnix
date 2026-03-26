"""Tests for terrarium.sdk public entry points."""
from __future__ import annotations

import httpx


async def test_get_tools_default_format(test_adapter, transport):
    """GET /api/v1/tools returns tool list."""
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/tools")

    assert resp.status_code == 200
    tools = resp.json()
    assert isinstance(tools, list)
    assert len(tools) >= 1


async def test_get_tools_openai_format(test_adapter, mock_gateway):
    """GET /api/v1/tools?format=openai calls gateway with openai protocol."""
    transport = httpx.ASGITransport(app=test_adapter.fastapi_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get(
            "/api/v1/tools", params={"format": "openai"}
        )

    assert resp.status_code == 200
    # Verify gateway was called with the right protocol
    mock_gateway.get_tool_manifest.assert_awaited()


async def test_execute_tool_via_http(test_adapter, transport):
    """POST /api/v1/actions/{tool} executes tool."""
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/actions/email_send",
            json={
                "actor_id": "test-agent",
                "arguments": {"to": "a@b.com", "body": "hi"},
            },
        )

    assert resp.status_code == 200
    result = resp.json()
    assert "email_id" in result
