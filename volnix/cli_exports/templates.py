"""Config snippet templates for agent integration.

Each function takes a URL and tool list, returns a formatted string
that the user can paste into their agent's config.

To add a new agent target:
1. Add a function here matching the target name
2. Register it in EXPORT_REGISTRY at the bottom
"""
from __future__ import annotations

import json
from typing import Any


def claude_desktop(url: str, tools: list[dict[str, Any]]) -> str:
    """Claude Desktop MCP server config (claude_desktop_config.json)."""
    return json.dumps({
        "mcpServers": {
            "volnix": {
                "url": f"{url}/mcp",
                "transport": "streamable-http",
            }
        }
    }, indent=2)


def cursor(url: str, tools: list[dict[str, Any]]) -> str:
    """Cursor MCP server config (.cursor/mcp.json)."""
    return json.dumps({
        "mcpServers": {
            "volnix": {
                "url": f"{url}/mcp",
            }
        }
    }, indent=2)


def windsurf(url: str, tools: list[dict[str, Any]]) -> str:
    """Windsurf MCP server config."""
    return json.dumps({
        "mcpServers": {
            "volnix": {
                "serverUrl": f"{url}/mcp",
            }
        }
    }, indent=2)


def openai_tools(url: str, tools: list[dict[str, Any]]) -> str:
    """OpenAI function-calling tool definitions."""
    return json.dumps(tools, indent=2)


def anthropic_tools(url: str, tools: list[dict[str, Any]]) -> str:
    """Anthropic tool_use definitions."""
    return json.dumps(tools, indent=2)


def mcp_raw(url: str, tools: list[dict[str, Any]]) -> str:
    """Raw MCP server connection info."""
    return json.dumps({
        "url": f"{url}/mcp",
        "transport": "streamable-http",
        "tools": len(tools),
    }, indent=2)


def env_vars(url: str, tools: list[dict[str, Any]]) -> str:
    """Environment variable exports.

    M4 fix: only outputs VOLNIX_URL and MCP URL.
    Per-service API URLs (SLACK_API_URL etc.) are Phase 2 (Path 1A).
    """
    return (
        f"export VOLNIX_URL={url}\n"
        f"export VOLNIX_MCP_URL={url}/mcp"
    )


def python_sdk(url: str, tools: list[dict[str, Any]]) -> str:
    """Python SDK usage snippet."""
    return f'''\
from volnix.sdk import VolnixClient

async with VolnixClient(url="{url}") as terra:
    tools = await terra.tools()
    result = await terra.call("email_send", to="user@example.com", body="Hello")
'''


def typescript_sdk(url: str, tools: list[dict[str, Any]]) -> str:
    """TypeScript SDK usage snippet (HTTP API)."""
    return f'''\
// Volnix HTTP API
const VOLNIX_URL = "{url}";

// List tools
const tools = await fetch(`${{VOLNIX_URL}}/api/v1/tools?format=openai`).then(r => r.json());

// Call a tool
const result = await fetch(`${{VOLNIX_URL}}/api/v1/actions/email_send`, {{
  method: "POST",
  headers: {{ "Content-Type": "application/json" }},
  body: JSON.stringify({{ actor_id: "ts-agent", arguments: {{ to: "user@example.com" }} }}),
}}).then(r => r.json());
'''


def langgraph(url: str, tools: list[dict[str, Any]]) -> str:
    """LangGraph adapter usage snippet."""
    return f'''\
from volnix.adapters.langgraph import langgraph_tools
from langgraph.prebuilt import create_react_agent

tools = await langgraph_tools(url="{url}")
agent = create_react_agent(model, tools)
'''


def autogen(url: str, tools: list[dict[str, Any]]) -> str:
    """AutoGen adapter usage snippet."""
    return f'''\
from volnix.adapters.autogen import autogen_tools

tools = await autogen_tools(url="{url}")
# Register tools with your AutoGen agents
'''


def crewai(url: str, tools: list[dict[str, Any]]) -> str:
    """CrewAI adapter usage snippet."""
    return f'''\
from volnix.adapters.crewai import crewai_tools

tools = await crewai_tools(url="{url}")
# Pass tools to your CrewAI agents
'''


def docker_compose(url: str, tools: list[dict[str, Any]]) -> str:
    """Docker Compose with network aliases for transparent interception.

    M3 fix: extracts port from url parameter.
    """
    # Extract port from URL
    port = "8080"
    if ":" in url.split("//")[-1]:
        port = url.split(":")[-1].rstrip("/")

    return f'''\
# Add to your docker-compose.yml:
services:
  volnix:
    image: volnix:latest
    ports:
      - "{port}:{port}"
    networks:
      default:
        aliases:
          - api.slack.com
          - gmail.googleapis.com
          - api.stripe.com
'''


# ---------------------------------------------------------------------------
# Registry: maps export target names to template functions
# ---------------------------------------------------------------------------

EXPORT_REGISTRY: dict[str, Any] = {
    "claude-desktop": claude_desktop,
    "cursor": cursor,
    "windsurf": windsurf,
    "openai-tools": openai_tools,
    "anthropic-tools": anthropic_tools,
    "mcp-raw": mcp_raw,
    "env-vars": env_vars,
    "python-sdk": python_sdk,
    "typescript-sdk": typescript_sdk,
    "langgraph": langgraph,
    "autogen": autogen,
    "crewai": crewai,
    "docker-compose": docker_compose,
}
