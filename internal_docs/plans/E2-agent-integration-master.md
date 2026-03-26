## Agent Integration — Master Roadmap

This is the roadmap document. Implementation details go in separate per-phase plans.
Saves to: `internal_docs/plans/E2-agent-integration-master.md`

---

### What the spec requires

3 paths for external agents to connect to Terrarium worlds:

| Path | Layer | What it intercepts | Example |
|------|-------|-------------------|---------|
| **1A** | Outbound API sim | Native SDK/REST calls | `slack_sdk.WebClient(base_url="http://localhost:7400/slack/api")` |
| **1B** | Inbound event sim | Webhooks, Pub/Sub, push | Terrarium pushes simulated Gmail notification to agent's webhook |
| **2** | MCP Tool Server | MCP tools/skills | Claude Desktop connects to Terrarium MCP server |
| **3A** | Direct SDK | Python/TS client | `terra.email.send()`, `terra.tickets.update()` |
| **3B** | Tool manifest | Function-calling formats | `get_tool_manifest(format="openai")` for GPT agents |
| **3C** | Framework adapters | LangGraph/AutoGen/CrewAI | `from terrarium.adapters import langgraph_tools` |

Plus: `terrarium config --export` system, `terrarium attach/detach` commands.

---

### What EXISTS today

| Component | Status | What works |
|-----------|--------|-----------|
| MCP Server (Path 2) | **DONE** | stdio transport, tool listing, tool calls through 7-step pipeline |
| HTTP REST API (Path 3B base) | **DONE** | `/api/v1/tools`, `/api/v1/actions/{tool}`, auto-mounted pack routes |
| Tool format converters | **DONE** | `to_openai_function()`, `to_anthropic_tool()`, `get_mcp_tools()`, `get_http_routes()` |
| Gateway routing | **DONE** | Protocol-agnostic `handle_request()` → pipeline |
| `terrarium serve` CLI | **DONE** | Compiles world, starts MCP + HTTP, shows tools |
| 87 tools across 6 packs | **DONE** | Email, chat, tickets, payments, repos, calendar |
| Real API paths in packs | **DONE** | `/gmail/v1/messages`, `/v1/charges`, `/rest/api/3/issue`, etc. |
| Pack route auto-mounting | **DONE** | HTTP adapter reads `http_path` + `http_method` from packs, mounts FastAPI routes |

**Key architectural insight**: The gateway is already protocol-agnostic. All protocols funnel through `handle_request(actor_id, tool_name, input_data)` → `app.handle_action()` → 7-step pipeline. Adding new protocols = new adapter wrapping the same gateway.

---

### Gap inventory (13 gaps across 3 phases)

#### Phase 1 — SDK, Export, Transport (G1-G6)

These enable external agents to connect using what's already built.

| # | Gap | What | Depends on |
|---|-----|------|-----------|
| **G1** | TerrariumClient SDK | Python client: `terra.email.send()` wrapping HTTP API | HTTP API (done) |
| **G2** | Public entry points | `from terrarium import get_tool_manifest, execute_tool` | Gateway (done) |
| **G3** | Framework adapters | `terrarium/adapters/langgraph.py`, `autogen.py`, `crewai.py` | G1 or HTTP API |
| **G4** | `config --export` CLI | 13 export targets (claude-desktop, openai-tools, env-vars, etc.) | Tool manifest (done) |
| **G5** | `attach / detach` CLI | Patch + restore agent configs | G4 |
| **G6** | SSE/HTTP MCP transport | Remote MCP connections (not just stdio) | MCP server (done) |

#### Phase 2 — Real API Surface Simulation (G7-G8)

These make Terrarium look like real service APIs to native SDKs.

| # | Gap | What | Depends on |
|---|-----|------|-----------|
| **G7** | API surface handlers | Service-specific route handlers that return real API response shapes | Pack routes (done) |
| **G8** | Auth mimicry | Accept structurally valid tokens, mock OAuth | G7 |

**Key insight**: Pack routes are already auto-mounted at real API paths (e.g., `/gmail/v1/messages`). The HTTP adapter already handles GET/POST routing. What's missing is:
- Service-specific URL prefixing (`/slack/api/*`, `/gmail/*`, `/stripe/*`)
- Auth header validation (accept `Bearer xoxb-*` for Slack, `Bearer sk_*` for Stripe)
- Response shape matching (wrap Terrarium responses in service-specific envelopes)

#### Phase 3 — Event Simulation (G9-G10)

These push events INTO agents as if real services were sending them.

| # | Gap | What | Depends on |
|---|-----|------|-----------|
| **G9** | Event push system | HTTP POST to agent webhook endpoints with simulated payloads | Animator (done), pack schemas |
| **G10** | Webhook delivery | Retry, ordering, signature validation, callback config | G9 |

#### Deferred (G11-G13)

| # | Gap | Notes |
|---|-----|-------|
| **G11** | OpenAI/Anthropic protocol adapters | Stubs exist. E2 scope. |
| **G12** | ACP server adapter | Stub exists. E2 scope. |
| **G13** | Browser/CDP interception | Acknowledged gap. Post-MVP. |

---

### Dependency graph

```
Phase 1 (foundation — enables ALL agent types):
  G6 (SSE MCP) ← standalone, unblocks Claude Desktop/Cursor/Windsurf
  G2 (entry points) ← needs gateway (done)
  G1 (SDK client) ← needs HTTP API (done)
  G3 (adapters) ← needs G1 or G2
  G4 (config export) ← needs tool manifest (done)
  G5 (attach/detach) ← needs G4

Phase 2 (native SDK interception):
  G7 (API surfaces) ← needs pack routes (done) + service-specific wrappers
  G8 (auth mimicry) ← needs G7

Phase 3 (event push):
  G9 (event system) ← needs animator (done) + webhook delivery
  G10 (webhook delivery) ← needs G9
```

---

### What each phase unlocks

**After Phase 1**: Any MCP client (Claude Desktop, Cursor, Windsurf, LangGraph), any function-calling agent (OpenAI, Anthropic SDK loops), any framework (AutoGen, CrewAI, LangGraph) can connect to Terrarium. Config export makes setup trivial.

**After Phase 2**: Agents using native SDKs (Slack Bolt, stripe-python, google-api-python-client) can point at Terrarium by changing one base URL. No code changes needed.

**After Phase 3**: Event-driven agents (webhook receivers, Pub/Sub consumers) get simulated inbound events. Full-stack agent testing including reactive behavior.

---

### Implementation approach

Each phase gets its own detailed plan with:
- Exact file changes with code snippets
- Test plan
- Audit step after completion
- Verification commands

We do NOT write code until the phase plan is approved.

---

### Files to create

- `internal_docs/plans/E2-agent-integration-master.md` — this roadmap (save after approval)
- `internal_docs/plans/E2a-phase1-sdk-export-transport.md` — Phase 1 implementation plan
- `internal_docs/plans/E2b-phase2-api-surfaces.md` — Phase 2 implementation plan (later)
- `internal_docs/plans/E2c-phase3-event-simulation.md` — Phase 3 implementation plan (later)
