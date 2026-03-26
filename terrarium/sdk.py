"""Terrarium SDK — connect to a running Terrarium world.

Standalone HTTP client with zero internal Terrarium imports.
Uses ``httpx`` to talk to the Terrarium HTTP API.

Quick start::

    from terrarium.sdk import TerrariumClient

    async with TerrariumClient(url="http://localhost:8080") as terra:
        tools = await terra.tools()
        result = await terra.call("email_send", to="a@b.com", body="hello")

Standalone functions::

    from terrarium.sdk import get_tool_manifest, execute_tool

    tools = await get_tool_manifest(url="http://localhost:8080", fmt="openai")
    result = await execute_tool(url="http://localhost:8080",
                                tool="email_send", args={"to": "a@b.com"})
"""
from __future__ import annotations

from typing import Any

import httpx

# Default timeout for all SDK HTTP calls (seconds)
_DEFAULT_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# SDK Errors (M1: user-friendly, not raw httpx)
# ---------------------------------------------------------------------------


class TerrariumSDKError(Exception):
    """Base exception for Terrarium SDK errors."""


class TerrariumConnectionError(TerrariumSDKError):
    """Cannot connect to the Terrarium server."""


class TerrariumAPIError(TerrariumSDKError):
    """Server returned an error response."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Public entry points (both async — M6 fix)
# ---------------------------------------------------------------------------


async def get_tool_manifest(
    url: str = "http://localhost:8080",
    fmt: str = "openai",
    timeout: float = _DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """Fetch tool definitions from a running Terrarium server.

    Args:
        url: Base URL of the Terrarium server.
        fmt: Tool format — ``"openai"``, ``"anthropic"``, ``"mcp"``,
             or ``"http"``.
        timeout: Request timeout in seconds.

    Returns:
        List of tool definitions in the requested format.

    Raises:
        TerrariumConnectionError: If the server is unreachable.
        TerrariumAPIError: If the server returns an error.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"{url.rstrip('/')}/api/v1/tools",
                params={"format": fmt},
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise TerrariumConnectionError(
            f"Cannot connect to Terrarium server at {url}"
        )
    except httpx.HTTPStatusError as exc:
        raise TerrariumAPIError(
            f"Server error: {exc.response.status_code}",
            status_code=exc.response.status_code,
        )


async def execute_tool(
    url: str = "http://localhost:8080",
    tool: str = "",
    args: dict[str, Any] | None = None,
    actor_id: str = "sdk-agent",
    timeout: float = _DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Execute a tool on a running Terrarium server.

    Args:
        url: Base URL of the Terrarium server.
        tool: Tool name to execute.
        args: Tool arguments.
        actor_id: Actor identity for governance pipeline.
        timeout: Request timeout in seconds.

    Returns:
        Tool execution result.

    Raises:
        TerrariumConnectionError: If the server is unreachable.
        TerrariumAPIError: If the server returns an error.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{url.rstrip('/')}/api/v1/actions/{tool}",
                json={"actor_id": actor_id, "arguments": args or {}},
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise TerrariumConnectionError(
            f"Cannot connect to Terrarium server at {url}"
        )
    except httpx.HTTPStatusError as exc:
        raise TerrariumAPIError(
            f"Server error: {exc.response.status_code}",
            status_code=exc.response.status_code,
        )


# ---------------------------------------------------------------------------
# TerrariumClient — reusable async client
# ---------------------------------------------------------------------------


class TerrariumClient:
    """High-level async client for a running Terrarium world.

    Usage::

        async with TerrariumClient(url="http://localhost:8080") as terra:
            tools = await terra.tools()
            result = await terra.call("email_send", to="a@b.com")

    For testing, pass ``_transport`` to use httpx's ASGITransport
    instead of hitting a real server.
    """

    def __init__(
        self,
        url: str = "http://localhost:8080",
        actor_id: str = "sdk-agent",
        timeout: float = _DEFAULT_TIMEOUT,
        _transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._actor_id = actor_id
        self._client = httpx.AsyncClient(
            base_url=self._url,
            transport=_transport,
            timeout=timeout,
        )

    async def tools(self, fmt: str = "mcp") -> list[dict[str, Any]]:
        """List available tools.

        Args:
            fmt: Tool format — ``"openai"``, ``"anthropic"``,
                 ``"mcp"`` (default), or ``"http"``.
        """
        try:
            resp = await self._client.get(
                "/api/v1/tools", params={"format": fmt}
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError:
            raise TerrariumConnectionError(
                f"Cannot connect to Terrarium server at {self._url}"
            )
        except httpx.HTTPStatusError as exc:
            raise TerrariumAPIError(
                f"Server error: {exc.response.status_code}",
                status_code=exc.response.status_code,
            )

    async def call(self, tool: str, **kwargs: Any) -> dict[str, Any]:
        """Call a tool by name.

        Args:
            tool: Tool name (e.g., ``"email_send"``).
            **kwargs: Tool arguments passed as keyword args.

        Returns:
            Tool execution result dict.

        Raises:
            TerrariumConnectionError: If the server is unreachable.
            TerrariumAPIError: If the server returns an error.
        """
        try:
            resp = await self._client.post(
                f"/api/v1/actions/{tool}",
                json={
                    "actor_id": self._actor_id,
                    "arguments": kwargs,
                },
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError:
            raise TerrariumConnectionError(
                f"Cannot connect to Terrarium server at {self._url}"
            )
        except httpx.HTTPStatusError as exc:
            raise TerrariumAPIError(
                f"Server error: {exc.response.status_code}",
                status_code=exc.response.status_code,
            )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> TerrariumClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
