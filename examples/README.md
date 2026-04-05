# Volnix Integration Examples

Each folder contains a working example of connecting an AI agent framework to a Volnix world. All examples have been tested E2E against the Stock Analysis world (Alpaca service).

## Prerequisites

1. **Volnix installed and a world compiled:**
   ```bash
   cd /path/to/volnix
   uv sync --all-extras
   volnix serve customer_support --port 8080
   ```

2. **API keys** in a `.env` file (needed by the agent's LLM, not by Volnix):
   ```
   OPENAI_API_KEY=sk-...
   ANTHROPIC_API_KEY=sk-ant-...
   GOOGLE_API_KEY=AI...
   ```

3. **Dashboard** (optional, to watch events live):
   ```bash
   cd volnix-dashboard && npm run dev
   # Open http://localhost:3000
   ```

---

## Examples

| Framework | Folder | Connection | Volnix Imports |
|-----------|--------|-----------|-------------------|
| **OpenAI SDK** | `openai-sdk/` | HTTP compat (`/openai/v1/`) | None |
| **Anthropic SDK** | `anthropic-sdk/` | HTTP compat (`/anthropic/v1/`) | None |
| **Gemini SDK** | `gemini-sdk/` | HTTP compat (`/gemini/v1/`) | None |
| **CrewAI** | `crewai/` | Adapter (`volnix.adapters.crewai`) | 1 import |
| **LangGraph** | `langgraph/` | Adapter (`volnix.adapters.langgraph`) | 1 import |
| **AutoGen** | `autogen/` | Adapter (`volnix.adapters.autogen`) | 1 import |
| **MCP** | `mcp/` | MCP Streamable HTTP (`/mcp/`) | None |
| **PydanticAI** | `pydanticai/` | MCP (native) | None |

---

## Running Each Example

### OpenAI SDK

Zero Volnix imports. Uses the `/openai/v1/` compat endpoint.

```bash
mkdir my-openai-agent && cd my-openai-agent
uv venv --python 3.12
uv pip install openai httpx python-dotenv
# Copy your .env file here
cp /path/to/examples/openai-sdk/main.py .
uv run python main.py
```

**What it does:** Fetches tools from Volnix in OpenAI function format, runs a standard tool-calling loop, executes tool calls against the Volnix world.

**Integration code (the only change to your existing agent):**
```python
import httpx
tools = httpx.get("http://localhost:8080/openai/v1/tools").json()
# Pass tools to client.chat.completions.create(tools=tools)
# Execute tool_calls via POST /openai/v1/tools/call
```

---

### Anthropic SDK

Zero Volnix imports. Uses the `/anthropic/v1/` compat endpoint.

```bash
mkdir my-anthropic-agent && cd my-anthropic-agent
uv venv --python 3.12
uv pip install anthropic httpx python-dotenv
cp /path/to/examples/anthropic-sdk/main.py .
uv run python main.py
```

**Integration code:**
```python
import httpx
tools = httpx.get("http://localhost:8080/anthropic/v1/tools").json()
# Pass tools to client.messages.create(tools=tools)
# Execute tool_use blocks via POST /anthropic/v1/tools/call
```

---

### Gemini SDK

Zero Volnix imports. Uses the `/gemini/v1/` compat endpoint.

```bash
mkdir my-gemini-agent && cd my-gemini-agent
uv venv --python 3.12
uv pip install google-genai httpx python-dotenv
cp /path/to/examples/gemini-sdk/main.py .
uv run python main.py
```

**Integration code:**
```python
import httpx
from google.genai import types
tool_defs = httpx.get("http://localhost:8080/gemini/v1/tools").json()
declarations = [types.FunctionDeclaration(**t) for t in tool_defs]
# Use in generate_content(config={"tools": [types.Tool(function_declarations=declarations)]})
# Execute function_calls via POST /gemini/v1/tools/call
```

---

### CrewAI

Uses the Volnix adapter. Install volnix as editable from source.

```bash
# From your CrewAI project directory:
uv venv --python 3.12
uv pip install -e /path/to/volnix    # editable install
uv pip install crewai[tools] python-dotenv
```

**Integration code (replace your existing tools):**
```python
# BEFORE:
from crewai_tools import SomeSearchTool
tools = [SomeSearchTool()]

# AFTER:
import asyncio
from volnix.adapters.crewai import crewai_tools
tools = asyncio.get_event_loop().run_until_complete(
    crewai_tools("http://localhost:8080", actor_id="financial-analyst")
)
# Rest of your crew code unchanged
```

---

### LangGraph

Uses the Volnix adapter. Install volnix as editable from source.

```bash
mkdir my-langgraph-agent && cd my-langgraph-agent
uv venv --python 3.12
uv pip install -e /path/to/volnix
uv pip install langchain-core langchain-openai langgraph python-dotenv
```

**Integration code (replace your existing tools):**
```python
# BEFORE:
from langchain_community.tools.tavily_search import TavilySearchResults
tools = [TavilySearchResults(max_results=1)]

# AFTER:
import asyncio
from volnix.adapters.langgraph import langgraph_tools
tools = asyncio.get_event_loop().run_until_complete(
    langgraph_tools("http://localhost:8080", actor_id="research-analyst")
)
# Rest of your graph code unchanged
```

**Run:**
```bash
# Set API keys in environment
export OPENAI_API_KEY=sk-...
uv run python volnix_agent.py
```

---

### AutoGen

Uses the Volnix adapter. Install volnix as editable from source.

```bash
mkdir my-autogen-agent && cd my-autogen-agent
uv venv --python 3.12
uv pip install -e /path/to/volnix
uv pip install autogen-agentchat "autogen-ext[openai]" python-dotenv
cp /path/to/examples/autogen/main.py .
```

**Integration code (replace your existing tools):**
```python
# BEFORE (from AutoGen tutorial):
tools = [increment_number]  # local Python function

# AFTER:
from volnix.adapters.autogen import autogen_tools
tools = await autogen_tools(url="http://localhost:8080", actor_id="research-analyst")
# Pass to AssistantAgent(tools=tools) — rest unchanged
```

**Run:**
```bash
export OPENAI_API_KEY=sk-...
uv run python main.py
```

---

### MCP (Claude Desktop / Cursor / OpenClaw)

No code needed. Just add config and connect.

**Option 1: Streamable HTTP (remote — Volnix serving on a port):**

Add to your Claude Desktop / Cursor MCP config:
```json
{
  "mcpServers": {
    "volnix": {
      "url": "http://localhost:8080/mcp/",
      "transport": "streamable-http"
    }
  }
}
```

**Option 2: stdio (local — Volnix compiles + serves inline):**
```json
{
  "mcpServers": {
    "volnix": {
      "command": "volnix",
      "args": ["mcp", "customer_support"],
      "transport": "stdio"
    }
  }
}
```

**Option 3: Python MCP client (programmatic):**
```bash
# Uses volnix's own venv (mcp package already installed)
cd /path/to/volnix
uv run python examples/mcp/main.py
```

---

### PydanticAI

Zero Volnix imports. Connects directly via MCP (PydanticAI has native MCP support).

```bash
mkdir my-pydanticai-agent && cd my-pydanticai-agent
uv venv --python 3.12
uv pip install pydantic-ai openai python-dotenv
cp /path/to/examples/pydanticai/main.py .
```

**Integration code:**
```python
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStreamableHTTP

server = MCPServerStreamableHTTP("http://localhost:8080/mcp/")
agent = Agent("openai:gpt-4.1-mini", toolsets=[server])

async with agent:
    result = await agent.run("Analyze AAPL stock")
```

**Run:**
```bash
export OPENAI_API_KEY=sk-...
uv run python main.py
```

---

## Connection Paths

Volnix exposes tools through multiple protocols. Choose based on your framework:

```
Your Agent Framework
    │
    ├── MCP ──────────── /mcp/               (PydanticAI, Claude Desktop, Cursor)
    ├── HTTP Compat ──── /openai/v1/         (OpenAI SDK — zero imports)
    │                    /anthropic/v1/      (Anthropic SDK — zero imports)
    │                    /gemini/v1/         (Gemini SDK — zero imports)
    ├── Adapter ──────── volnix.adapters  (CrewAI, LangGraph, AutoGen)
    └── HTTP REST ────── /api/v1/            (Any HTTP client)
```

## Multi-Agent Setup

Each agent can have its own identity with separate permissions and budgets. Define agents in a YAML profile:

```yaml
# agents.yaml
agents:
  - id: research-analyst
    role: research-analyst
    permissions:
      read: [alpaca]
      write: []
    budget:
      api_calls: 200

  - id: investment-advisor
    role: investment-advisor
    permissions:
      read: [alpaca]
      write: [alpaca]
    budget:
      api_calls: 300
      spend_usd: 1000
```

Start with: `volnix serve --world <world_id> --agents agents.yaml --port 8080`

Then each agent uses its own `actor_id`:
```python
researcher_tools = await crewai_tools(url, actor_id="research-analyst")
advisor_tools = await crewai_tools(url, actor_id="investment-advisor")
```

Volnix enforces permissions and budgets per agent through the governance pipeline.
