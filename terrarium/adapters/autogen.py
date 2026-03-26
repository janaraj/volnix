"""AutoGen adapter — convert Terrarium tools to AutoGen tool functions.

Requires: ``pip install autogen-agentchat``

Usage::

    from terrarium.adapters.autogen import autogen_tools
    tools = await autogen_tools(url="http://localhost:8080")
"""
from __future__ import annotations

from typing import Any

from terrarium.sdk import execute_tool, get_tool_manifest


async def autogen_tools(
    url: str = "http://localhost:8080",
    actor_id: str = "autogen-agent",
) -> list[dict[str, Any]]:
    """Load Terrarium tools as AutoGen-compatible function definitions.

    Returns tool definitions with ``name``, ``description``,
    ``function_def`` (OpenAI format), and ``func`` (async callable).

    Each tool call is independent (no leaked connections).
    """
    tool_defs = await get_tool_manifest(url=url, fmt="openai")

    tools = []
    for td in tool_defs:
        func_def = td.get("function", td)
        name = func_def.get("name", "")
        if not name:
            continue

        async def _call(
            _url: str = url,
            _name: str = name,
            _actor: str = actor_id,
            **kwargs: Any,
        ) -> dict[str, Any]:
            return await execute_tool(
                url=_url, tool=_name, args=kwargs, actor_id=_actor
            )

        tools.append({
            "name": name,
            "description": func_def.get("description", ""),
            "func": _call,
            "function_def": td,
        })

    return tools
