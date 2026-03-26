"""Tests for TerrariumClient."""
from __future__ import annotations

from terrarium.sdk import TerrariumClient


async def test_client_list_tools(test_adapter, transport):
    """TerrariumClient.tools() returns tool list."""
    async with TerrariumClient(
        url="http://test", _transport=transport
    ) as terra:
        tools = await terra.tools()

    assert isinstance(tools, list)
    assert len(tools) >= 1


async def test_client_call_tool(test_adapter, transport):
    """TerrariumClient.call() returns action result."""
    async with TerrariumClient(
        url="http://test", _transport=transport
    ) as terra:
        result = await terra.call(
            "email_send", to="a@b.com", body="hello"
        )

    assert "email_id" in result


async def test_client_custom_actor_id(test_adapter, transport, mock_gateway):
    """TerrariumClient uses custom actor_id in requests."""
    async with TerrariumClient(
        url="http://test",
        actor_id="my-custom-agent",
        _transport=transport,
    ) as terra:
        await terra.call("email_send", to="a@b.com")

    # Check gateway received the custom actor_id
    call_kwargs = mock_gateway.handle_request.call_args.kwargs
    assert call_kwargs["actor_id"] == "my-custom-agent"


async def test_client_context_manager(test_adapter, transport):
    """TerrariumClient works as async context manager."""
    terra = TerrariumClient(url="http://test", _transport=transport)
    async with terra:
        tools = await terra.tools()
    assert isinstance(tools, list)
