"""LangGraph adapter — convert Volnix tools to LangChain tools.

Requires: ``pip install langchain-core``

Usage::

    from volnix.adapters.langgraph import langgraph_tools
    tools = await langgraph_tools(url="http://localhost:8080")
    agent = create_react_agent(model, tools)
"""
from __future__ import annotations

from typing import Any

from volnix.sdk import execute_tool


async def langgraph_tools(
    url: str = "http://localhost:8080",
    actor_id: str = "langgraph-agent",
) -> list[Any]:
    """Load Volnix tools as LangChain StructuredTool objects.

    Each tool calls the Volnix HTTP API directly (no leaked
    connections — each call is independent).

    Raises:
        ImportError: If langchain-core is not installed.
    """
    try:
        from langchain_core.tools import StructuredTool
    except ImportError:
        raise ImportError(
            "langchain-core is required for LangGraph adapter. "
            "Install with: pip install langchain-core"
        )

    from volnix.adapters._schema import json_schema_to_pydantic
    from volnix.sdk import get_tool_manifest

    tool_defs = await get_tool_manifest(url=url, fmt="mcp")

    tools = []
    for td in tool_defs:
        name = td.get("name", "")
        desc = td.get("description", "")
        schema = td.get("inputSchema", {})
        if not name:
            continue

        # Build Pydantic model from JSON Schema (same as CrewAI adapter)
        args_model = json_schema_to_pydantic(name, schema)

        # Stateless tool call — each invocation is an independent HTTP request
        async def _invoke(
            _url: str = url,
            _name: str = name,
            _actor: str = actor_id,
            **kwargs: Any,
        ) -> str:
            import json

            result = await execute_tool(
                url=_url, tool=_name, args=kwargs, actor_id=_actor
            )
            return json.dumps(result, default=str)

        tools.append(StructuredTool(
            name=name,
            description=desc,
            args_schema=args_model,
            coroutine=_invoke,
            func=lambda **kw: None,  # sync placeholder (required)
        ))

    return tools
