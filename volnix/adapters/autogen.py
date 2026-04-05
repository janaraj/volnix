"""AutoGen adapter — convert Volnix tools to AutoGen BaseTool subclasses.

Requires: ``pip install autogen-agentchat``

Usage::

    from volnix.adapters.autogen import autogen_tools
    tools = await autogen_tools(url="http://localhost:8080")
    agent = AssistantAgent("analyst", model_client=client, tools=tools)
"""
from __future__ import annotations

import json
from typing import Any

from volnix.adapters._schema import json_schema_to_pydantic
from volnix.sdk import execute_tool, get_tool_manifest


async def autogen_tools(
    url: str = "http://localhost:8080",
    actor_id: str = "autogen-agent",
) -> list[Any]:
    """Load Volnix tools as AutoGen BaseTool instances.

    Each tool uses a Pydantic model (from ``json_schema_to_pydantic``)
    for typed arguments — same schema bridge as CrewAI and LangGraph.

    Each tool call is independent (no leaked connections).
    """
    from autogen_core import CancellationToken
    from autogen_core.tools import BaseTool
    from pydantic import BaseModel

    tool_defs = await get_tool_manifest(url=url, fmt="mcp")

    tools = []
    for td in tool_defs:
        name = td.get("name", "")
        desc = td.get("description", "")
        schema = td.get("inputSchema", {})
        if not name:
            continue

        args_model = json_schema_to_pydantic(name, schema)

        # Bind values for this tool (closure via class attributes)
        tool_cls = type(
            f"VolnixTool_{name}",
            (BaseTool,),
            {
                "__init__": lambda self, *, _n=name, _d=desc, _m=args_model: BaseTool.__init__(
                    self, args_type=_m, return_type=str, name=_n, description=_d,
                ),
                "run": _make_run(url, name, actor_id),
            },
        )
        tools.append(tool_cls())

    return tools


def _make_run(bound_url: str, bound_name: str, bound_actor: str):
    """Create a ``run`` method for a BaseTool subclass."""

    async def run(self, args, cancellation_token=None) -> str:
        # args is a Pydantic model — dump to dict, skip None values
        args_dict = args.model_dump(exclude_none=True)
        result = await execute_tool(
            url=bound_url, tool=bound_name, args=args_dict, actor_id=bound_actor,
        )
        return json.dumps(result, default=str)

    return run
