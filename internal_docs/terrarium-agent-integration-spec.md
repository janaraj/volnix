# Terrarium — Agent Integration Spec (Final)

## The problem we solved incorrectly before

Our original design assumed agents connect to services through a single swappable layer (MCP). The OpenClaw audit disproved this. Agents have **multiple integration layers**, each requiring a different interception strategy:

- **Native channel/provider integrations** — Slack Bolt, Gmail Pub/Sub, WhatsApp Baileys, Stripe SDK. These talk directly to real APIs over HTTP or receive inbound events via webhooks. Not MCP. Not swappable via config alone.
- **MCP tools/skills** — The extensibility layer. Config-swappable. Growing rapidly across the ecosystem.
- **Framework tool abstractions** — OpenAI function calling, Anthropic tool use, LangGraph tool nodes, AutoGen/CrewAI tool classes. Programmatic, not protocol-based.

No single interception path covers all three. Terrarium needs three paths, each targeting a different layer.

---

## Path 1 — Provider / Channel Simulation Layer

### What it intercepts

Everything that talks to the outside world through:

- Direct REST/SDK calls (Slack Web API, Gmail API, Stripe API)
- Inbound webhooks / Pub/Sub / push notifications
- Provider auth flows (OAuth tokens, API keys)
- Event streams and callback handlers

### Why this path exists

This is the only path that catches native integrations — the ones agents use for their core service connections. OpenClaw's Slack channel uses Slack Bolt (direct SDK). Its Gmail integration is a full Pub/Sub → webhook → hook pipeline. Its WhatsApp connection uses Baileys. None of these are MCP. A `terrarium attach` that only swaps MCP config misses all of them.

Any agent using official Python/Node SDKs for Slack, Gmail, Stripe, GitHub, etc. hits the same problem. The SDK calls `https://api.slack.com/...` directly — there's no MCP layer to intercept.

### How it works

Terrarium runs local HTTP servers that simulate real service APIs plus inbound event sources. Two submodes:

**1A — Outbound API simulation (base URL swap)**

Terrarium mimics the actual REST API surface of real services. Agent SDKs are redirected by changing their base URL.

```bash
terrarium serve --apis slack,gmail,stripe --port 7400

# Terrarium now serves:
# localhost:7400/slack/api/*     → Slack Web API surface
# localhost:7400/gmail/v1/*      → Gmail API surface
# localhost:7400/stripe/v1/*     → Stripe API surface
```

Agent integration is an environment variable or config change:

```python
# Slack SDK — one line change
from slack_sdk import WebClient
client = WebClient(token="xoxb-terrarium", base_url="http://localhost:7400/slack/api")

# Stripe SDK — one line change
import stripe
stripe.api_base = "http://localhost:7400/stripe"
stripe.api_key = "sk_terrarium"

# OpenClaw — channel config patch
{
  "channels": {
    "slack": {
      "apiUrl": "http://localhost:7400/slack/api",
      "botToken": "xoxb-terrarium-simulated",
      "appToken": "xapp-terrarium-simulated"
    }
  }
}
```

**1B — Inbound event simulation (webhook/push/event-source)**

Many integrations are event-driven. Gmail in OpenClaw is: Gmail watch → Pub/Sub push → `gog gmail watch serve` → OpenClaw webhook. Slack sends events via Socket Mode or webhooks. WhatsApp pushes messages via Baileys.

Terrarium must simulate the inbound side too — pushing events into the agent as if real services were sending them.

```bash
terrarium serve --apis slack,gmail --events enabled --port 7400

# Terrarium now also:
# - Pushes simulated Gmail notifications to the agent's webhook endpoint
# - Sends simulated Slack events via the agent's Socket Mode / webhook
# - Delivers simulated WhatsApp messages to the agent's Baileys listener
```

For OpenClaw Gmail specifically:

```bash
# Terrarium replaces the entire Gmail Pub/Sub pipeline:
# Real:  Gmail → Pub/Sub → gog gmail watch serve → OpenClaw /hooks/gmail
# Sim:   Terrarium world event → POST to OpenClaw /hooks/gmail
#        (with the same payload shape gog would produce)
```

**Auth mimicry**: Terrarium accepts any token that looks structurally valid (e.g. `xoxb-*` for Slack, `sk_*` for Stripe) and returns success. For OAuth flows, Terrarium provides a mock OAuth server that issues simulated tokens.

### Export patterns

```bash
terrarium config --export openclaw-channels   # Patches openclaw.json channel URLs + hook config
terrarium config --export env-vars            # SLACK_API_URL=... STRIPE_API_BASE=... GMAIL_HOOK_URL=...
terrarium config --export docker-compose      # Compose file with network aliases (api.slack.com → terrarium)
```

The Docker Compose approach is the most transparent — network-level aliasing means the agent doesn't need any config changes at all. The container resolves `api.slack.com` to Terrarium.

### What this catches

| Integration type | Example | Submode |
|---|---|---|
| OpenClaw native channels | Slack Bolt, WhatsApp Baileys, Telegram grammY | 1A + 1B |
| OpenClaw Gmail pipeline | Pub/Sub → webhook → hooks | 1B |
| Official SDK users | slack_sdk, google-api-python-client, stripe-python | 1A |
| Webhook-driven agents | GitHub webhooks, Stripe webhooks | 1B |
| Any REST API consumer | Custom HTTP clients to service APIs | 1A |

### What this misses

- MCP-based tools (use Path 2)
- Framework tool abstractions (use Path 3)
- Browser automation / CDP (acknowledged gap — see Gaps section)

### Implementation cost

**Highest of the three paths.** Each service API needs:

- Request routing and parsing
- Response shape matching (must return what the real API returns)
- State integration with the world engine
- Auth mimicry
- For 1B: event payload generation, push scheduling, callback signature validation

**Ship order:** Start with a small set of high-value APIs: Slack Web API (core endpoints), Gmail API (read/send), Stripe (charges/refunds). Expand based on demand.

---

## Path 2 — MCP Tool Server

### What it intercepts

The MCP-based tools/skills/extensions layer — everything agents discover and call via the Model Context Protocol.

### Why this path exists

MCP is the standard extensibility mechanism across the agent ecosystem. OpenClaw has 3,200+ ClawHub skills accessible via MCP. Cursor, Windsurf, and Claude Desktop are native MCP clients. LangGraph has explicit MCP adapter support via `langchain-mcp-adapters`. This layer is config-swappable by design.

### How it works

Terrarium exposes world services as one or more MCP servers. Agents connect via stdio (local) or HTTP/SSE (remote).

```bash
terrarium serve --protocol mcp --port 8100

# Terrarium exposes MCP tools:
# email_read_inbox, email_send, tickets_list, tickets_update_status,
# chat_send_message, payments_create_refund, etc.
```

Each tool call flows through the world engine — state changes, policy checks, budget tracking, causal graph recording — then returns a response.

### Agent-specific integration

**OpenClaw (skills/plugins layer):**

```bash
terrarium config --export openclaw-skills
# Adds to openclaw.json → plugins.entries or mcp.servers:
# {
#   "mcp": {
#     "servers": {
#       "terrarium": {
#         "url": "http://localhost:8100/mcp",
#         "transport": "sse"
#       }
#     }
#   }
# }
```

**Claude Desktop / Cursor / Windsurf:**

```bash
terrarium config --export claude-desktop    # claude_desktop_config.json MCP entry
terrarium config --export cursor            # Cursor MCP settings patch
terrarium config --export windsurf          # Windsurf MCP config patch
```

**LangGraph (via langchain-mcp-adapters):**

```python
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

async with streamablehttp_client(url="http://localhost:8100/mcp") as (read, write, _):
    async with ClientSession(read, write) as session:
        await session.initialize()
        tools = await load_mcp_tools(session)
        agent = create_react_agent(model, tools)
```

**The `terrarium attach` shortcut (from original design, now correctly scoped):**

```bash
terrarium attach --agent openclaw --layer skills    # Patches MCP/plugin config only
terrarium attach --agent claude --layer tools        # Patches MCP server config
terrarium detach --agent openclaw                    # Restores original config
```

### What this catches

| Agent / host | How it connects |
|---|---|
| OpenClaw skills/tools | `mcp.servers` config entry or `plugins.entries` |
| Claude Desktop | MCP server in `claude_desktop_config.json` |
| Cursor | MCP server in settings |
| Windsurf | MCP server config (stdio / HTTP / SSE) |
| LangGraph | `MultiServerMCPClient` or `load_mcp_tools` |
| Any MCP-capable client | Standard MCP connection |

### What this misses

- Native channel/provider integrations (use Path 1)
- Agents that don't support MCP (use Path 3)
- Browser automation tools (partial — CDP-via-MCP tools are covered; raw Playwright is not)

### Implementation cost

**Lowest of the three paths.** Terrarium already needs a tool interface for the world engine. Wrapping that in MCP protocol is straightforward. This should ship first.

---

## Path 3 — SDK + Tool Manifest

### What it intercepts

The programmatic tool layer — for agents where you control the tool execution code and can swap in Terrarium's tools directly.

### Why this path exists

Many agents don't use MCP and don't use interceptable service SDKs. They're custom model loops with function calling (OpenAI, Anthropic), framework-based agents (AutoGen, CrewAI), or hand-rolled Python/TS scripts. For these, Terrarium needs to provide tools they can call programmatically.

### How it works

Three sub-options, all backed by the same HTTP API:

**3A — Direct SDK (for custom agents)**

```python
from terrarium import TerrariumClient

terra = TerrariumClient(world="./world.yaml", actor="agent-alpha")

inbox = terra.email.list_inbox()
terra.tickets.update_status("T-123", "in_progress")
terra.chat.send("#support", "Working on it")
result = terra.payments.create_refund(charge_id="ch_123", amount=5000)
```

**3B — Tool manifest (for function-calling agents)**

```python
from terrarium import get_tool_manifest, execute_tool

# OpenAI format
tools = get_tool_manifest(world="./world.yaml", format="openai")
response = client.chat.completions.create(model="gpt-4o", tools=tools, messages=[...])
result = execute_tool(world="./world.yaml", call=response.tool_calls[0])

# Anthropic format
tools = get_tool_manifest(world="./world.yaml", format="anthropic")
response = client.messages.create(model="claude-sonnet-4-20250514", tools=tools, messages=[...])
result = execute_tool(world="./world.yaml", call=response.content[0])  # tool_use block
```

**3C — Framework adapters (thin wrappers on the SDK)**

```python
# LangGraph (non-MCP path)
from terrarium.adapters import langgraph_tools
tools = langgraph_tools(world="./world.yaml")
agent = create_react_agent(model, tools)

# AutoGen
from terrarium.adapters import autogen_tools
tools = autogen_tools(world="./world.yaml")

# CrewAI
from terrarium.adapters import crewai_tools
tools = crewai_tools(world="./world.yaml")
```

### Export patterns

```bash
terrarium config --export openai-tools       # JSON tool definitions in OpenAI format
terrarium config --export anthropic-tools    # JSON tool definitions in Anthropic format
terrarium config --export python-sdk         # Python code snippet with TerrariumClient
terrarium config --export typescript-sdk     # TypeScript code snippet
```

### What this catches

| Agent type | Sub-option | Code changes |
|---|---|---|
| OpenAI SDK agents | 3B (tool manifest) | 2 imports + swap tool defs |
| Anthropic SDK agents | 3B (tool manifest) | 2 imports + swap tool defs |
| LangGraph (non-MCP) | 3C (adapter) | 1 import |
| AutoGen | 3C (adapter) | 1 import |
| CrewAI | 3C (adapter) | 1 import |
| Custom Python/TS agent | 3A (SDK) | Replace tool calls with terra.* |
| Any HTTP client | Raw HTTP API | Point at Terrarium URL |

### What this misses

Nothing — this is the universal fallback. If you can change code, you can use Path 3.

### Implementation cost

**Low.** The SDK wraps the same HTTP API that backs Path 1 and Path 2. Framework adapters are thin wrappers (~50 lines each). Ships alongside Path 2.

---

## How the paths compose for real agents

### OpenClaw (the most complex case)

OpenClaw needs **all three paths** for full coverage:

| OpenClaw layer | What it does | Terrarium path |
|---|---|---|
| Native channels | Slack Bolt, WhatsApp Baileys, Telegram grammY | Path 1A (API sim) |
| Gmail Pub/Sub | Gmail watch → webhook → hooks pipeline | Path 1B (event sim) |
| MCP skills/tools | 3,200+ ClawHub skills, managed MCP servers | Path 2 (MCP) |
| Custom code/scripts | Agent workspace scripts, custom tool code | Path 3 (SDK) |

The `terrarium config --export openclaw` command patches all three layers in one shot:

```bash
terrarium config --export openclaw --world ./world.yaml

# Outputs:
# 1. Channel URL patches (Path 1A)
# 2. Hook endpoint config for Gmail sim (Path 1B)  
# 3. MCP server entries for skills (Path 2)
# 4. Instructions for any custom tool code (Path 3)
```

### Claude Desktop / Cursor / Windsurf

Single path — Path 2 only. These are MCP-native hosts with no native service SDK integrations.

### LangGraph agent

Depends on how the agent is built:

| LangGraph pattern | Terrarium path |
|---|---|
| MCP tools via `langchain-mcp-adapters` | Path 2 |
| Direct SDK calls to services | Path 1A |
| Custom tool functions | Path 3B or 3C |

### OpenAI / Anthropic SDK loop

Path 3B (tool manifest) for the agent's tools. If the agent also calls service SDKs directly (e.g., `stripe.Charge.create()`), those need Path 1A.

### AutoGen / CrewAI

Path 3C (framework adapter) for tools. Path 2 if they use MCP. Path 1A if they also use native SDKs.

---

## Complete coverage matrix

| Agent type | Path 1A (API) | Path 1B (events) | Path 2 (MCP) | Path 3 (SDK) |
|---|---|---|---|---|
| **OpenClaw channels** | ✓ primary | ✓ Gmail/webhooks | — | — |
| **OpenClaw skills** | — | — | ✓ primary | — |
| **Claude Desktop** | — | — | ✓ only path | — |
| **Cursor / Windsurf** | — | — | ✓ only path | — |
| **LangGraph + MCP** | — | — | ✓ primary | fallback |
| **LangGraph + SDKs** | ✓ primary | if event-driven | — | fallback |
| **OpenAI SDK loop** | if uses SDKs | — | — | ✓ primary |
| **Anthropic SDK loop** | if uses SDKs | — | — | ✓ primary |
| **AutoGen / CrewAI** | — | — | if MCP | ✓ primary |
| **Custom Python agent** | if uses SDKs | if webhook-based | — | ✓ primary |
| **Webhook-driven agent** | — | ✓ primary | — | — |

---

## Acknowledged gaps

### Browser automation

OpenClaw has an isolated managed browser and can attach to Chrome via CDP. Other agents use Playwright, Puppeteer, or raw CDP.

- **Browser-via-MCP** (e.g., Chrome DevTools MCP server): covered by Path 2.
- **Direct CDP/Playwright**: NOT covered. Would need a browser/CDP interception path under Path 1 or a browser wrapper under Path 3. Deferred to post-MVP.

### Coverage claim

We do **not** claim 90% coverage. The three-path structure is correct and covers the major agent categories. Actual coverage depends on how much of Path 1 is implemented — each service API surface is real engineering work.

---

## Implementation priority

### Phase 1 — Ship together (weeks 1-4)

**Path 2 (MCP server):** Lowest effort, highest breadth. Covers the entire MCP ecosystem immediately.

**Path 3 (SDK + tool manifest):** Ships alongside Path 2 — same HTTP API, different wrapper. Covers function-calling and framework agents.

### Phase 2 — High-value API surfaces (weeks 5-8)

**Path 1A (outbound API sim):** Start with Slack Web API (core: `chat.postMessage`, `conversations.list`, `reactions.add`), Gmail API (core: `messages.list`, `messages.get`, `messages.send`), Stripe API (core: `charges.retrieve`, `refunds.create`, `refunds.list`).

### Phase 3 — Event simulation (weeks 9-12)

**Path 1B (inbound events):** Gmail Pub/Sub push simulation, Slack event push, webhook delivery. This is when OpenClaw gets full-stack coverage.

### Ongoing — Community-driven expansion

Each new service API surface can be contributed as a pack (Tier 1 verified or Tier 2 profiled). The promotion ladder applies here too: someone implements the Jira API surface, captures it, promotes it.

---

## The `terrarium config --export` system

Universal CLI for all paths:

```bash
# Agent-specific (patches all relevant layers)
terrarium config --export openclaw           # Channels + skills + hooks
terrarium config --export claude-desktop     # MCP server config
terrarium config --export cursor             # MCP server config
terrarium config --export windsurf           # MCP server config

# Path-specific
terrarium config --export mcp-raw            # Generic MCP server JSON
terrarium config --export openai-tools       # OpenAI function-calling manifest
terrarium config --export anthropic-tools    # Anthropic tool-use manifest
terrarium config --export env-vars           # Environment variables for API URL swaps
terrarium config --export docker-compose     # Network-level aliasing (most transparent)

# Framework-specific
terrarium config --export langgraph          # MCP adapter or tool node snippet
terrarium config --export autogen            # AutoGen tool class snippet
terrarium config --export crewai             # CrewAI BaseTool subclass snippet
terrarium config --export python-sdk         # Generic TerrariumClient snippet
```

Each export knows its target's config format and file location. Agent-specific exports combine multiple paths into a single patch.

---

## Summary

Three paths, correctly scoped:

| Path | Layer | Interception point | Code changes | Ships |
|---|---|---|---|---|
| **1. Provider / Channel Sim** | Native SDKs + webhooks | API base URL + event push | Config only (or Docker alias for zero-change) | Phase 2-3 |
| **2. MCP Tool Server** | Tools / skills / extensions | MCP config swap | Zero | Phase 1 |
| **3. SDK + Tool Manifest** | Programmatic tools | Import + swap | 1-2 lines | Phase 1 |

The critical insight: **MCP is not universal.** It's the extensibility layer, not the integration layer. Native service connections are HTTP/SDK/webhook-based and need their own interception strategy. Terrarium's three-path design respects this reality.


Few things to consider further:

1. Config patching + rollback
Your terrarium config --export ... story is strong, but you still need one exact contract for:

where config gets patched,
how backups are stored,
how detach/restore works,
and how to avoid clobbering user config.

2. Auth mimicry rules
You say Terrarium accepts structurally valid tokens and can mock OAuth. That’s the right direction, but you should freeze:

whether Terrarium validates token shape only or also scopes,
how simulated auth errors are produced,
how refresh/expiry is represented.

3. Webhook/event delivery semantics
Path 1B is now present, which is great, but you should define:

retry behavior,
ordering,
dedupe/idempotency,
signature validation behavior,
and whether delivery is at-least-once vs exactly-once in simulation