"""CrewAI adapter — convert Terrarium tools to CrewAI BaseTool subclasses.

Requires: ``pip install crewai``

Usage::

    from terrarium.adapters.crewai import crewai_tools
    tools = await crewai_tools(url="http://localhost:8080")
"""
from __future__ import annotations

from typing import Any

import httpx

from terrarium.sdk import get_tool_manifest


async def crewai_tools(
    url: str = "http://localhost:8080",
    actor_id: str = "crewai-agent",
) -> list[Any]:
    """Load Terrarium tools as CrewAI-compatible tool objects.

    Each tool uses synchronous HTTP calls (CrewAI tools are sync).
    No connection leaks — each call creates and closes its own client.

    Raises:
        ImportError: If crewai is not installed.
    """
    try:
        from crewai.tools import BaseTool as CrewAIBaseTool
    except ImportError:
        raise ImportError(
            "crewai is required for CrewAI adapter. "
            "Install with: pip install crewai"
        )

    tool_defs = await get_tool_manifest(url=url, fmt="mcp")

    tools = []
    for td in tool_defs:
        name = td.get("name", "")
        desc = td.get("description", "")
        if not name:
            continue

        # H2 fix: implement actual _run that calls the API
        _url = url
        _name = name
        _actor = actor_id

        class TerrariumTool(CrewAIBaseTool):
            name: str = _name  # type: ignore[assignment]
            description: str = desc

            def _run(self, **kwargs: Any) -> str:
                """Sync tool execution via HTTP."""
                import json

                resp = httpx.post(
                    f"{_url}/api/v1/actions/{_name}",
                    json={
                        "actor_id": _actor,
                        "arguments": kwargs,
                    },
                    timeout=30.0,
                )
                return json.dumps(resp.json(), default=str)

        tools.append(TerrariumTool())

    return tools
