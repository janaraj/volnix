# Agent Integration

This guide covers how to connect external AI agents to Volnix using MCP, REST API, Python SDK, or framework adapters.

---

## Overview

Volnix exposes world tools through multiple protocols. Your agent connects to a running Volnix server and interacts with the simulated world as if it were real services.

```
Your Agent (Claude, GPT, custom)
  |
  |-- MCP (recommended for Claude Desktop, Cursor, Windsurf)
  |-- REST API (any HTTP client)
  |-- Python SDK (async Python)
  |-- OpenAI / Anthropic tool format (framework adapters)
  |
  v
Volnix Server
  |
  v
7-Step Governance Pipeline --> Simulated World State
```

---

## Starting the Server

Before connecting an agent, start Volnix with a world:

```bash
# From a blueprint
volnix serve customer_support --port 8080

# From a YAML file
volnix serve my_world.yaml --port 8080

# From natural language
volnix serve "A support team with Zendesk and Slack" --port 8080

# Re-serve an existing run (instant, no compilation)
volnix serve --run run_64ca8171df83 --port 8080
```

The server exposes:
- **HTTP REST API** at `http://localhost:8080/api/v1/`
- **MCP endpoint** at `http://localhost:8080/mcp`
- **WebSocket** at `ws://localhost:8080/api/v1/events/stream`

---

## MCP (Model Context Protocol)

The recommended integration for Claude Desktop, Cursor, and Windsurf.

### Setup

```bash
# Start server
uv run volnix serve customer_support --port 8080

# Export the MCP config snippet for your agent
uv run volnix config --export claude-desktop --port 8080
```

Add the exported snippet to your agent's MCP configuration file.

Supported targets: `claude-desktop`, `cursor`, `windsurf`

### Manual Config

If you prefer to configure manually, export the config snippet:

```bash
volnix config --export claude-desktop --port 8080
```

Output (paste into your agent's MCP config):

```json
{
  "mcpServers": {
    "volnix": {
      "url": "http://localhost:8080/mcp",
      "transport": "streamable-http"
    }
  }
}
```

Config file locations:
- **Claude Desktop**: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
- **Cursor**: `.cursor/mcp.json` (workspace-relative)
- **Windsurf**: `.windsurf/mcp.json` (workspace-relative)

### MCP Stdio Mode

For agents that spawn Volnix as a subprocess:

```bash
volnix mcp customer_support
```

This starts an MCP server on stdio (stdin/stdout). The agent sends JSON-RPC requests on stdin and receives responses on stdout.

---

## REST API

For custom agents, scripts, or any HTTP client.

### Discover Tools

```bash
# List tools in OpenAI format
curl http://localhost:8080/api/v1/tools?format=openai

# List tools in Anthropic format
curl http://localhost:8080/api/v1/tools?format=anthropic

# List tools in MCP format
curl http://localhost:8080/api/v1/tools?format=mcp
```

### Execute a Tool

```bash
curl -X POST http://localhost:8080/api/v1/actions/email_send \
  -H "Content-Type: application/json" \
  -d '{
    "actor_id": "my-agent",
    "arguments": {
      "to": "customer@example.com",
      "subject": "Re: Your refund request",
      "body": "Your refund has been processed."
    }
  }'
```

Response:

```json
{
  "structured_content": {
    "message_id": "msg_a1b2c3",
    "status": "sent",
    "timestamp": "2026-03-15T10:30:00Z"
  },
  "content": "Email sent successfully",
  "is_error": false
}
```

### Request Formats

The API accepts two body formats (auto-detected):

**Wrapped (SDK style):**
```json
{
  "actor_id": "my-agent",
  "arguments": { "to": "user@example.com", "body": "Hello" }
}
```

**Raw (standard):**
```json
{
  "to": "user@example.com",
  "body": "Hello"
}
```

With raw format, identify yourself via header: `X-Actor-Id: my-agent`

### Agent Registration

Register to get a dedicated actor slot:

```bash
curl -X POST http://localhost:8080/api/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "my-agent", "role": "support-agent"}'
```

Or let Volnix auto-assign by setting `allow_unregistered_access = true` in config (the default).

### Key Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/tools` | List available tools |
| `POST` | `/api/v1/actions/{tool}` | Execute a tool |
| `GET` | `/api/v1/health` | Health check |
| `GET` | `/api/v1/agents/slots` | Discover available actor slots |
| `POST` | `/api/v1/agents/register` | Register an external agent |
| `GET` | `/api/v1/runs` | List runs |
| `GET` | `/api/v1/runs/{id}/events` | List events for a run |
| `GET` | `/api/v1/report/scorecard` | Governance scorecard |
| `WS` | `/api/v1/events/stream` | Live event stream |

---

## Python SDK

For Python agents and scripts:

```python
from volnix.sdk import VolnixClient

async with VolnixClient(
    url="http://localhost:8080",
    actor_id="my-agent",
) as terra:
    # Discover tools
    tools = await terra.tools(fmt="openai")
    print(f"Available tools: {len(tools)}")

    # Read emails
    emails = await terra.call("email_list", query="is:unread")

    # Reply to a ticket
    result = await terra.call(
        "tickets.update",
        ticket_id="T-1234",
        status="in_progress",
        comment="Looking into this now.",
    )

    # Send a Slack message
    await terra.call(
        "chat.postMessage",
        channel_id="C-support",
        text="Ticket T-1234 is being handled.",
    )
```

### Standalone Functions

For one-off calls without a client context:

```python
from volnix.sdk import get_tool_manifest, execute_tool

tools = await get_tool_manifest(url="http://localhost:8080", fmt="openai")

result = await execute_tool(
    url="http://localhost:8080",
    tool="email_send",
    args={"to": "user@example.com", "body": "Hello"},
    actor_id="my-agent",
)
```

### Error Handling

```python
from volnix.sdk import VolnixClient, VolnixConnectionError, VolnixAPIError

try:
    async with VolnixClient(url="http://localhost:8080") as terra:
        result = await terra.call("email_send", to="user@example.com")
except VolnixConnectionError:
    print("Could not connect to Volnix server")
except VolnixAPIError as e:
    print(f"API error: {e}")
```

---

## Framework Adapters

Export tool definitions for popular agent frameworks:

### OpenAI Function Calling

```bash
volnix config --export openai-tools --port 8080
```

Returns JSON array of OpenAI function definitions. Pass these as `tools` to the OpenAI Chat Completions API.

### Anthropic Tool Use

```bash
volnix config --export anthropic-tools --port 8080
```

Returns JSON array of Anthropic tool definitions. Pass these as `tools` to the Anthropic Messages API.

### LangGraph

```bash
volnix config --export langgraph --port 8080
```

Returns a Python code snippet for integrating Volnix tools into a LangGraph agent.

### CrewAI

```bash
volnix config --export crewai --port 8080
```

### AutoGen

```bash
volnix config --export autogen --port 8080
```

### Docker Compose

```bash
volnix config --export docker-compose --port 8080
```

Returns a `docker-compose.yml` snippet with network aliases matching the simulated services.

---

## WebSocket Live Stream

Subscribe to real-time events:

```javascript
const ws = new WebSocket("ws://localhost:8080/api/v1/events/stream");

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`[${data.event_type}] ${data.actor_id}: ${data.action}`);
};
```

Events include actions, policy triggers, budget warnings, and state changes.

---

## Authentication

By default, Volnix accepts unauthenticated requests (`auth_enabled = false`).

To enable authentication:

```toml
# volnix.local.toml
[middleware]
auth_enabled = true
```

With auth enabled, agents must register and use Bearer tokens:

```bash
curl -H "Authorization: Bearer volnix_abc123" \
  http://localhost:8080/api/v1/actions/email_list
```

---

## Tips

- **Start simple**: Use `volnix config --export` for the fastest setup. Manual config is only needed for custom workflows.
- **Check available tools**: Run `curl http://localhost:8080/api/v1/tools?format=openai | python -m json.tool` to see what your agent can do.
- **Watch the dashboard**: Run `volnix dashboard --port 8200` in another terminal to observe your agent's actions in real time.
- **Review the report**: After a session, run `volnix report last` to see governance scores and capability gaps.
