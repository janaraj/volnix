## E2a Phase 1: SDK, Export, Transport — Detailed Implementation Plan

Saves to: `internal_docs/plans/E2a-phase1-sdk-export-transport.md`

### Context

Phase 1 enables external agents to connect to running Terrarium worlds. The MCP server and HTTP API already work. This phase adds the **ease-of-use layer**: a Python SDK, config export for popular agents, framework adapters, and SSE/HTTP MCP transport for remote connections.

**Current state**: 2209 tests, 1 failed (Google), 0 xfails.

---

### Architecture

```
terrarium/
  sdk.py                          ← G1 + G2: standalone HTTP client (zero internal imports)
  adapters/
    __init__.py
    langgraph.py                  ← G3: ~40 lines
    autogen.py                    ← G3: ~40 lines
    crewai.py                     ← G3: ~40 lines
  cli_exports/
    __init__.py
    templates.py                  ← G4: config snippet templates per agent type
  engines/adapter/protocols/
    http_rest.py                  ← G6: add /mcp SSE endpoint (small addition)
  cli.py                          ← G4 + G5: config export + attach/detach commands
```

**Design rules:**
- `sdk.py` uses `httpx` only — no internal Terrarium imports. It's a standalone client that talks to the HTTP API.
- `adapters/` modules import from `sdk.py` only — no engine/gateway/pipeline imports.
- `cli_exports/templates.py` is pure string templates — no complex logic.
- G6 (SSE MCP) is a small addition to the existing FastAPI app — not a new server.

---

### G6: SSE/HTTP MCP Transport

**What**: Mount `/mcp` endpoint on the existing FastAPI server so remote MCP clients (Claude Desktop, Cursor, Windsurf) can connect over HTTP+SSE instead of stdio.

**File**: `terrarium/engines/adapter/protocols/http_rest.py`

**How**: Use MCP SDK's `StreamableHTTPSessionManager` (already installed, production-ready). Mount as a Starlette route on the existing FastAPI app.

```python
# In start_server(), after existing route setup:
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

# Reuse the same MCP Server instance from MCPServerAdapter
mcp_adapter = gateway._adapters.get("mcp")
if mcp_adapter and mcp_adapter._server:
    session_manager = StreamableHTTPSessionManager(
        app=mcp_adapter._server,
        stateless=True,  # each request is independent
    )

    # Mount MCP endpoint
    from starlette.routing import Route
    app.mount("/mcp", session_manager.handle_request)
```

**Result**: `http://localhost:8080/mcp` accepts MCP clients over HTTP+SSE. Stdio continues to work for local agents.

**Verify**: Connect a MCP client to `http://localhost:8080/mcp`, call a tool.

---

### G2: Public Entry Points

**What**: Two functions any Python script can use without understanding Terrarium internals.

**File**: `terrarium/sdk.py` (NEW)

```python
"""Terrarium SDK — connect to a running Terrarium world.

Usage:
    from terrarium.sdk import get_tool_manifest, execute_tool

    tools = get_tool_manifest(url="http://localhost:8080", format="openai")
    result = execute_tool(url="http://localhost:8080", tool="email_send", args={...})
"""
import httpx
from typing import Any


def get_tool_manifest(
    url: str = "http://localhost:8080",
    format: str = "openai",  # "openai" | "anthropic" | "mcp" | "raw"
) -> list[dict[str, Any]]:
    """Fetch tool definitions from a running Terrarium server."""
    resp = httpx.get(f"{url}/api/v1/tools", params={"format": format})
    resp.raise_for_status()
    return resp.json()


async def execute_tool(
    url: str = "http://localhost:8080",
    tool: str = "",
    args: dict[str, Any] | None = None,
    actor_id: str = "sdk-agent",
) -> dict[str, Any]:
    """Execute a tool on a running Terrarium server."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{url}/api/v1/actions/{tool}",
            json={"actor_id": actor_id, "arguments": args or {}},
        )
        resp.raise_for_status()
        return resp.json()
```

**HTTP API dependency**: The `/api/v1/tools` endpoint needs a `format` query param. Check if it exists; if not, add it to `http_rest.py`.

**Verify**: `from terrarium.sdk import get_tool_manifest; tools = get_tool_manifest()`

---

### G1: TerrariumClient SDK

**What**: A class with service namespaces for ergonomic tool access.

**File**: `terrarium/sdk.py` (same file as G2, below the entry points)

```python
class TerrariumClient:
    """High-level client for a running Terrarium world.

    Usage:
        terra = TerrariumClient(url="http://localhost:8080")
        inbox = terra.call("email_list_inbox")
        terra.call("tickets_update_status", ticket_id="T-123", status="in_progress")
    """

    def __init__(
        self,
        url: str = "http://localhost:8080",
        actor_id: str = "sdk-agent",
    ) -> None:
        self._url = url.rstrip("/")
        self._actor_id = actor_id
        self._client = httpx.AsyncClient(base_url=self._url)

    async def tools(self, format: str = "raw") -> list[dict]:
        """List available tools."""
        resp = await self._client.get("/api/v1/tools", params={"format": format})
        resp.raise_for_status()
        return resp.json()

    async def call(self, tool: str, **kwargs) -> dict:
        """Call a tool by name."""
        resp = await self._client.post(
            f"/api/v1/actions/{tool}",
            json={"actor_id": self._actor_id, "arguments": kwargs},
        )
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
```

**Note**: No service namespaces (`terra.email.send()`) in v1. Just `terra.call("email_send", ...)`. Namespaces can be added later by dynamically building them from the tool manifest. Keeps it simple.

**Verify**: `async with TerrariumClient() as terra: result = await terra.call("email_send", to="a@b.com")`

---

### G3: Framework Adapters

**What**: Thin wrappers converting Terrarium tools into framework-specific tool objects.

**Files**: `terrarium/adapters/__init__.py`, `langgraph.py`, `autogen.py`, `crewai.py`

**`terrarium/adapters/langgraph.py`** (~40 lines):
```python
"""LangGraph adapter — convert Terrarium tools to LangChain tools."""
from terrarium.sdk import TerrariumClient


async def langgraph_tools(url: str = "http://localhost:8080"):
    """Load Terrarium tools as LangChain-compatible tool objects.

    Usage:
        from terrarium.adapters.langgraph import langgraph_tools
        tools = await langgraph_tools(url="http://localhost:8080")
        agent = create_react_agent(model, tools)
    """
    from langchain_core.tools import StructuredTool

    client = TerrariumClient(url=url)
    tool_defs = await client.tools(format="raw")

    tools = []
    for td in tool_defs:
        name = td["name"]

        async def _call(tool_name=name, **kwargs):
            return await client.call(tool_name, **kwargs)

        tools.append(StructuredTool.from_function(
            coroutine=_call,
            name=name,
            description=td.get("description", ""),
        ))
    return tools
```

**`autogen.py` and `crewai.py`**: Same pattern, different tool class. Each ~40 lines.

**Optional deps**: These adapters import `langchain_core`, `autogen`, `crewai` — which are NOT in Terrarium's dependencies. They're optional. If the framework isn't installed, the import fails with a clear error.

**Verify**: `tools = await langgraph_tools(); assert len(tools) > 0`

---

### G4: `terrarium config --export` CLI

**What**: CLI command that prints config snippets for different agent types.

**Files**: `terrarium/cli_exports/templates.py` (NEW), `terrarium/cli.py` (add command)

**`terrarium/cli_exports/templates.py`**: Pure template functions. Each returns a string.

```python
def claude_desktop(url: str, tools: list[dict]) -> str:
    """Generate claude_desktop_config.json MCP server entry."""
    import json
    config = {
        "mcpServers": {
            "terrarium": {
                "url": f"{url}/mcp",
                "transport": "streamable-http"
            }
        }
    }
    return json.dumps(config, indent=2)


def openai_tools(url: str, tools: list[dict]) -> str:
    """Generate OpenAI function-calling tool definitions."""
    import json
    return json.dumps(tools, indent=2)


def env_vars(url: str, tools: list[dict]) -> str:
    """Generate environment variable exports."""
    lines = [f"export TERRARIUM_URL={url}"]
    # Add per-service URLs from pack HTTP paths
    services = set()
    for t in tools:
        name = t.get("name", "")
        service = name.split("_")[0] if "_" in name else ""
        if service:
            services.add(service)
    for svc in sorted(services):
        lines.append(f"export {svc.upper()}_API_URL={url}/{svc}")
    return "\n".join(lines)


# ... similar for: cursor, windsurf, anthropic_tools,
#     python_sdk, typescript_sdk, langgraph, autogen, crewai,
#     docker_compose, mcp_raw
```

**CLI command** in `cli.py`:
```python
@app.command()
def config(
    export: str = typer.Option(..., "--export", help="Export target"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8080, "--port"),
):
    """Export configuration for agent integration."""
    asyncio.run(_config_export_impl(export, host, port))
```

**Supported targets** (13): `claude-desktop`, `cursor`, `windsurf`, `openai-tools`, `anthropic-tools`, `mcp-raw`, `env-vars`, `docker-compose`, `python-sdk`, `typescript-sdk`, `langgraph`, `autogen`, `crewai`

**Verify**: `uv run terrarium config --export claude-desktop --port 8080`

---

### G5: `terrarium attach / detach`

**What**: Convenience commands that patch an agent's config file to point at Terrarium.

**How it works**:
1. `attach` reads the agent's config file (known path per agent type)
2. Backs up to `{file}.terrarium-backup`
3. Patches the MCP/tool config section
4. `detach` restores from backup

```python
@app.command()
def attach(
    agent: str = typer.Argument(help="Agent type: claude-desktop, cursor, windsurf"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8080, "--port"),
):
    """Patch agent config to connect to Terrarium."""

@app.command()
def detach(
    agent: str = typer.Argument(help="Agent type to restore"),
):
    """Restore agent config from backup."""
```

**Known config paths**:
- Claude Desktop: `~/.config/claude/claude_desktop_config.json` (Linux) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
- Cursor: `.cursor/mcp.json` in workspace
- Windsurf: similar pattern

**Verify**: `uv run terrarium attach claude-desktop --port 8080` then check config file.

---

### HTTP API Enhancement Needed

The `/api/v1/tools` endpoint needs to support a `format` query parameter so the SDK can request tools in different formats:

```python
# In http_rest.py, update the tools endpoint:
@app.get("/api/v1/tools")
async def list_tools(
    format: str = fastapi.Query(default="mcp"),
    actor_id: str = fastapi.Query(default="http-agent"),
):
    tools = await gateway.get_tool_manifest(protocol=format)
    return tools
```

---

### Critical Code Context (for subagents)

**Existing patterns to follow:**

1. **HTTP tool endpoint** (`http_rest.py:81-86`): `/api/v1/tools` currently calls `gateway.get_tool_manifest(protocol="mcp")`. Needs `format` query param.

2. **Gateway tool manifest** (`gateway.py:144-174`): `get_tool_manifest(protocol=)` supports "mcp", "http", "openai", "anthropic". Returns list of dicts.

3. **MCP server creation** (`mcp_server.py:34-66`): Creates `mcp.server.Server`, registers `list_tools` + `call_tool` handlers. Currently uses `stdio_server()` at line 68.

4. **MCP SDK SSE** (installed at `.venv/lib/.../mcp/server/`):
   - `StreamableHTTPSessionManager` — production-grade, manages sessions
   - Constructor: `StreamableHTTPSessionManager(app=mcp_server, stateless=True)`
   - Mount: `app.add_route("/mcp", session_manager.handle_request)`
   - Lifespan: needs `async with session_manager.run(): yield` in app lifespan

5. **CLI command pattern** (`cli.py`): Sync def + `asyncio.run(_impl())`. Uses `typer`, `app_context()` for async app access.

6. **Test pattern** (`tests/engines/adapter/test_http_rest.py`): Uses `httpx.ASGITransport` + `httpx.AsyncClient` for testing FastAPI apps without real server.

7. **Pack tool definitions** (`packs/verified/email/schemas.py:114+`): Each tool has `name`, `description`, `http_path`, `http_method`, `parameters`, `required_params`, `response_schema`.

8. **`TerrariumClient` transport injection**: For testing, the client should accept an optional `_transport` parameter (httpx transport) so tests can use `ASGITransport` instead of hitting a real server.

**Files that must NOT be changed:**
- `terrarium/gateway/gateway.py` — no changes needed (already supports all formats)
- `terrarium/engines/` — no engine changes
- `terrarium/packs/` — no pack changes
- `terrarium/core/` — no core changes

**New files only:**
- `terrarium/sdk.py` (G1 + G2)
- `terrarium/adapters/__init__.py`, `langgraph.py`, `autogen.py`, `crewai.py` (G3)
- `terrarium/cli_exports/__init__.py`, `templates.py`, `attach.py` (G4 + G5)
- `tests/sdk/` directory with conftest + 10 test files (32 tests)

**Small modifications to existing files:**
- `terrarium/engines/adapter/protocols/http_rest.py` — add `format` param to tools endpoint + mount `/mcp` SSE
- `terrarium/cli.py` — add `config` and `attach`/`detach` commands

---

### Implementation Order

```
1. G6 (SSE MCP)          — mount /mcp on FastAPI, test with MCP client
2. HTTP format param      — add format query to /api/v1/tools
3. G2 (entry points)      — sdk.py: get_tool_manifest + execute_tool
4. G1 (SDK client)        — sdk.py: TerrariumClient class
5. G3 (adapters)          — adapters/langgraph.py, autogen.py, crewai.py
6. G4 (config export)     — cli_exports/templates.py + CLI command
7. G5 (attach/detach)     — CLI commands with file backup/restore
8. Tests for each
9. Full suite verification
```

### Test Harness

**Directory**: `tests/sdk/` (NEW)

**`tests/sdk/conftest.py`** — Reusable fixtures for all SDK + adapter + export tests:

```python
"""Test harness for SDK, adapters, and config export."""
import pytest
from unittest.mock import AsyncMock, MagicMock
import httpx
from terrarium.engines.adapter.protocols.http_rest import HTTPRestAdapter


# Sample tool definitions (reused across all tests)
SAMPLE_TOOLS_RAW = [
    {"name": "email_send", "description": "Send an email",
     "parameters": {"to": {"type": "string"}, "body": {"type": "string"}},
     "required_params": ["to", "body"]},
    {"name": "tickets_update", "description": "Update a ticket",
     "parameters": {"ticket_id": {"type": "string"}, "status": {"type": "string"}},
     "required_params": ["ticket_id"]},
]

SAMPLE_TOOLS_OPENAI = [
    {"type": "function", "function": {"name": "email_send",
     "description": "Send an email",
     "parameters": {"type": "object",
      "properties": {"to": {"type": "string"}, "body": {"type": "string"}},
      "required": ["to", "body"]}}},
]

SAMPLE_ACTION_RESULT = {"email_id": "e-123", "status": "sent"}


@pytest.fixture
def mock_gateway():
    """Mock gateway returning sample tools and action results."""
    gw = MagicMock()
    gw.get_tool_manifest = AsyncMock(return_value=SAMPLE_TOOLS_RAW)
    gw.handle_request = AsyncMock(return_value=SAMPLE_ACTION_RESULT)

    mock_app = MagicMock()
    mock_app.bus = MagicMock()
    mock_app.bus.subscribe = AsyncMock()
    mock_app.read_entities = AsyncMock(return_value={})
    gw._app = mock_app
    return gw


@pytest.fixture
async def test_http_server(mock_gateway):
    """Running HTTP adapter with mock gateway for SDK tests."""
    adapter = HTTPRestAdapter(mock_gateway)
    await adapter.start_server()
    yield adapter
    await adapter.stop_server()


@pytest.fixture
def server_url():
    """Base URL for test server (used with httpx ASGITransport)."""
    return "http://test"
```

**Test files**:

| File | Tests | What it covers |
|------|-------|---------------|
| `tests/sdk/__init__.py` | — | Package init |
| `tests/sdk/conftest.py` | — | Shared fixtures |
| `tests/sdk/test_entry_points.py` | 5 | `get_tool_manifest()` and `execute_tool()` with mocked HTTP |
| `tests/sdk/test_client.py` | 5 | `TerrariumClient` tools/call/close lifecycle |
| `tests/sdk/test_adapters_langgraph.py` | 3 | LangGraph tool conversion (skip if langchain not installed) |
| `tests/sdk/test_adapters_autogen.py` | 2 | AutoGen tool conversion (skip if autogen not installed) |
| `tests/sdk/test_adapters_crewai.py` | 2 | CrewAI tool conversion (skip if crewai not installed) |
| `tests/sdk/test_config_export.py` | 8 | Each export template produces valid output |
| `tests/sdk/test_attach_detach.py` | 4 | Config patch, backup, restore, error handling |
| `tests/sdk/test_mcp_sse.py` | 3 | SSE MCP endpoint accepts connections |
| **Total** | **32** | |

**Test patterns**:

```python
# test_entry_points.py — uses httpx ASGITransport to test against real FastAPI app
async def test_get_tool_manifest_openai_format(test_http_server, mock_gateway):
    """get_tool_manifest with format=openai returns OpenAI function definitions."""
    transport = httpx.ASGITransport(app=test_http_server.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/tools", params={"format": "openai"})
    assert resp.status_code == 200
    tools = resp.json()
    assert isinstance(tools, list)
    assert all(t.get("type") == "function" for t in tools)

# test_client.py — tests TerrariumClient against mocked HTTP
async def test_client_call_tool(test_http_server):
    """TerrariumClient.call() sends correct request and returns result."""
    from terrarium.sdk import TerrariumClient
    transport = httpx.ASGITransport(app=test_http_server.fastapi_app)
    # Use the test transport directly
    async with TerrariumClient(url="http://test", _transport=transport) as terra:
        result = await terra.call("email_send", to="a@b.com", body="hello")
    assert "email_id" in result

# test_config_export.py — pure template tests, no server needed
def test_claude_desktop_export():
    """claude-desktop export produces valid JSON with mcpServers."""
    from terrarium.cli_exports.templates import claude_desktop
    output = claude_desktop(url="http://localhost:8080", tools=[])
    import json
    config = json.loads(output)
    assert "mcpServers" in config
    assert "terrarium" in config["mcpServers"]

# test_attach_detach.py — tests file manipulation
def test_attach_creates_backup(tmp_path):
    """attach backs up existing config before patching."""
    config_file = tmp_path / "config.json"
    config_file.write_text('{"existing": true}')
    from terrarium.cli_exports.attach import patch_config
    patch_config(config_file, {"mcpServers": {"terrarium": {}}})
    assert (tmp_path / "config.json.terrarium-backup").exists()
```

---

### Documentation Updates

**After implementation, update these docs:**

1. **`IMPLEMENTATION_STATUS.md`** — Full update:
   - Current focus: E2a (Agent Integration Phase 1)
   - Test count: 2240+ (current 2209 + ~32 new)
   - Mark G1-G4 as done, G4a-G4b as done
   - Mark E2a as done
   - Update gap sections

2. **`internal_docs/plans/E2a-phase1-sdk-export-transport.md`** — Save this plan

3. **`internal_docs/plans/E2-agent-integration-master.md`** — Already saved

---

### Verification

```bash
# Unit tests
uv run pytest tests/sdk/ -v
uv run pytest tests/ --ignore=tests/live --ignore=tests/integration -q
# Target: 2240+ passed, 0 xfails

# Lint
uv run ruff check terrarium/sdk.py terrarium/adapters/ terrarium/cli_exports/

# Manual E2E (after implementation)
uv run terrarium serve examples/support-team.yaml --port 8080 &
uv run terrarium config --export claude-desktop --port 8080
python -c "
from terrarium.sdk import get_tool_manifest
tools = get_tool_manifest(url='http://localhost:8080', format='openai')
print(f'{len(tools)} tools available')
"
```
