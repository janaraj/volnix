"""CrewAI adapter — convert Terrarium tools to CrewAI BaseTool subclasses.

Requires: ``pip install crewai``

Usage::

    # Simple (single agent, backward compat):
    from terrarium.adapters.crewai import crewai_tools
    tools = await crewai_tools(url="http://localhost:8080")

    # Multi-agent (each agent gets own identity + budget):
    from terrarium.adapters.crewai import crewai_register_agent
    token, tools = await crewai_register_agent(url="http://localhost:8080", agent_name="analyst")
"""
from __future__ import annotations

from typing import Any

import httpx

from terrarium.sdk import get_tool_manifest


def _make_tool_class(
    tool_name: str,
    description: str,
    url: str,
    actor_id: str,
    agent_token: str | None = None,
    input_schema: dict[str, Any] | None = None,
) -> Any:
    """Create a CrewAI BaseTool subclass for a single Terrarium tool."""
    from crewai.tools import BaseTool as CrewAIBaseTool
    from terrarium.adapters._schema import json_schema_to_pydantic

    _url = url
    _name = tool_name
    _desc = description
    _actor = actor_id
    _token = agent_token
    _schema_model = json_schema_to_pydantic(tool_name, input_schema or {})

    class TerrariumTool(CrewAIBaseTool):
        name: str = _name  # type: ignore[assignment]
        description: str = _desc
        args_schema: type = _schema_model  # type: ignore[assignment]

        def _run(self, **kwargs: Any) -> str:
            """Sync tool execution via HTTP."""
            import json

            headers: dict[str, str] = {}
            if _token:
                headers["Authorization"] = f"Bearer {_token}"

            resp = httpx.post(
                f"{_url}/api/v1/actions/{_name}",
                json={
                    "actor_id": _actor,
                    "arguments": kwargs,
                },
                headers=headers,
                timeout=30.0,
            )
            return json.dumps(resp.json(), default=str)

    return TerrariumTool()


async def crewai_tools(
    url: str = "http://localhost:8080",
    actor_id: str = "http-agent",
) -> list[Any]:
    """Load Terrarium tools as CrewAI-compatible tool objects.

    Uses the default http-agent identity (no registration needed).
    All tools share the same actor identity.

    Raises:
        ImportError: If crewai is not installed.
    """
    try:
        from crewai.tools import BaseTool as _  # noqa: F401
    except ImportError:
        raise ImportError(
            "crewai is required for CrewAI adapter. "
            "Install with: pip install crewai"
        )

    tool_defs = await get_tool_manifest(url=url, fmt="mcp")
    return [
        _make_tool_class(
            td["name"], td.get("description", ""), url, actor_id,
            input_schema=td.get("inputSchema"),
        )
        for td in tool_defs
        if td.get("name")
    ]


async def crewai_register_agent(
    url: str = "http://localhost:8080",
    agent_name: str = "crewai-agent",
    actor_id: str | None = None,
    role_hint: str | None = None,
) -> tuple[str, list[Any]]:
    """Register an agent with Terrarium and get identity-bound tools.

    Claims an actor slot, receives a token, and creates tools that
    include the token on every call. The agent's tool calls are
    tracked against the slot's budget and permissions.

    Args:
        url: Terrarium server URL.
        agent_name: Human-readable name for this agent.
        actor_id: Specific actor slot to claim (optional).
        role_hint: Prefer slots with this role (optional, used for auto-assign).

    Returns:
        (agent_token, tools) tuple.

    Raises:
        RuntimeError: If registration fails (no slots, already claimed).
    """
    try:
        from crewai.tools import BaseTool as _  # noqa: F401
    except ImportError:
        raise ImportError(
            "crewai is required for CrewAI adapter. "
            "Install with: pip install crewai"
        )

    # Register with Terrarium
    body: dict[str, Any] = {"agent_name": agent_name}
    if actor_id:
        body["actor_id"] = actor_id
    elif role_hint:
        body["role_hint"] = role_hint

    async with httpx.AsyncClient(base_url=url, timeout=10.0) as client:
        resp = await client.post("/api/v1/agents/register", json=body)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Registration failed: {resp.json().get('error', resp.text)}"
        )

    reg = resp.json()
    token = reg["agent_token"]
    resolved_actor_id = reg["actor_id"]

    # Load tools with the token baked in
    tool_defs = await get_tool_manifest(url=url, fmt="mcp")
    tools = [
        _make_tool_class(
            td["name"], td.get("description", ""), url,
            resolved_actor_id, agent_token=token,
            input_schema=td.get("inputSchema"),
        )
        for td in tool_defs
        if td.get("name")
    ]

    return token, tools
