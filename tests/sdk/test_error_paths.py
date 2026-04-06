"""Tests for SDK error handling — failure cases and edge cases."""

from __future__ import annotations

import pytest

from volnix.sdk import (
    VolnixAPIError,
    VolnixClient,
    VolnixConnectionError,
    VolnixSDKError,
    execute_tool,
    get_tool_manifest,
)

# -- get_tool_manifest errors --------------------------------------------------


async def test_get_tool_manifest_connection_refused():
    """Connection refused raises VolnixConnectionError."""
    with pytest.raises(VolnixConnectionError):
        await get_tool_manifest(url="http://localhost:1", timeout=1)


async def test_get_tool_manifest_invalid_url():
    """Invalid URL raises VolnixConnectionError."""
    with pytest.raises(VolnixConnectionError):
        await get_tool_manifest(
            url="http://invalid-host-that-does-not-exist:9999",
            timeout=2,
        )


# -- execute_tool errors -------------------------------------------------------


async def test_execute_tool_connection_refused():
    """Connection refused raises VolnixConnectionError."""
    with pytest.raises(VolnixConnectionError):
        await execute_tool(
            url="http://localhost:1",
            tool="email_send",
            timeout=1,
        )


# -- VolnixClient errors ---------------------------------------------------


async def test_client_connection_refused():
    """Client raises VolnixConnectionError on server down."""
    async with VolnixClient(url="http://localhost:1", timeout=1) as terra:
        with pytest.raises(VolnixConnectionError):
            await terra.tools()


async def test_client_call_invalid_host():
    """Client raises VolnixConnectionError for unreachable host."""
    async with VolnixClient(url="http://invalid-host-xyz:9999", timeout=2) as terra:
        with pytest.raises(VolnixConnectionError):
            await terra.call("any_tool")


async def test_client_double_close(test_adapter, transport):
    """Closing client twice doesn't raise."""
    terra = VolnixClient(url="http://test", _transport=transport)
    await terra.close()
    await terra.close()  # Should not raise


# -- SDK error hierarchy -------------------------------------------------------


def test_errors_inherit_from_base():
    """All SDK errors inherit from VolnixSDKError."""
    assert issubclass(VolnixConnectionError, VolnixSDKError)
    assert issubclass(VolnixAPIError, VolnixSDKError)


def test_api_error_has_status_code():
    """VolnixAPIError carries status_code."""
    err = VolnixAPIError("test", status_code=404)
    assert err.status_code == 404
