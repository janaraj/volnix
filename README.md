# Volnix

**Programmable worlds for AI agents.**

Every AI agent today runs in a vacuum. It calls APIs, gets responses, and has no idea whether the world it's operating in is consistent, adversarial, or even real. There's no state between calls. No other actors with their own goals. No policies that push back. No consequences that cascade. No world that moves while the agent is thinking.

Volnix changes that. It creates complete, living realities — with places, institutions, actors that have personalities and agendas, budgets, policies, communication systems, and causal chains — where AI agents exist as participants inside a world that doesn't stop when they do.

<p align="center">
  <a href="https://youtu.be/AoWVcPGoj6E">
    <img src="https://img.youtube.com/vi/AoWVcPGoj6E/maxresdefault.jpg" alt="Volnix Demo" width="800">
  </a>
  <br>
  <a href="https://youtu.be/AoWVcPGoj6E">Watch the 1-minute demo</a>
</p>

```bash
pip install volnix
export GOOGLE_API_KEY=...
volnix serve dynamic_support_center --internal agents_dynamic_support --port 8080
```

---

## Internal Agents

Deploy 3 agents or 30 — each is an LLM-powered actor that lives inside the world. Bounded only by configurable parallel execution. No orchestrator routes messages between them. Agents coordinate through the world itself — posting in Slack, updating tickets, processing payments, observing each other's actions through shared state. The world mediates the collaboration, not a framework.

A **lead agent** coordinates the team through a 4-phase lifecycle:

| Phase | What the Lead Does |
|-------|-------------------|
| **Delegate** | Assigns tasks to each team member, sets expectations |
| **Monitor** | Validates findings, directs next steps, assigns new work |
| **Buffer** | Requests all agents to share final findings as simulation nears end |
| **Synthesize** | Generates the final deliverable from the full team conversation |

Sub-agents are autonomous — they investigate, act, and share findings through world channels. The lead doesn't control them directly. It posts in Slack, sub-agents react. The deliverable emerges from agents operating inside an environment, not from a pipeline of LLM calls.

```
┌──────────────────────────────────────────────────────────────┐
│                        VOLNIX WORLD                          │
│                                                              │
│   Lead ──▶ Slack ◀── Agent 2 ◀── Agent 3 ◀── ... Agent N    │
│     │         ▲          │            │                      │
│     ▼         │          ▼            ▼                      │
│   Zendesk ────┘    Stripe (refunds)  Gmail                   │
│     │                    │                                   │
│     ▼                    ▼                                   │
│   Policy Engine ◀── Budget Engine ◀── Permission Engine      │
│                                                              │
│   NPCs: customers follow up, escalate, complain              │
│   Animator: new events arrive on the world's own timeline    │
│                          ↓                                   │
│        Deliverable: synthesis / prediction / decision         │
└──────────────────────────────────────────────────────────────┘
```

Define a team in YAML — roles, permissions, budgets, a mission, and a deliverable type:

```yaml
mission: >
  Investigate each open ticket. Process refunds where appropriate.
  Senior-agent handles refunds under $100. Supervisor approves over $100.

deliverable: synthesis    # synthesis | prediction | decision | brainstorm | assessment

agents:
  - role: supervisor
    lead: true
    permissions: { read: [zendesk, stripe, slack], write: [zendesk, stripe, slack] }
    budget: { api_calls: 50, spend_usd: 500 }
  - role: senior-agent
    permissions: { read: [zendesk, stripe, slack], write: [zendesk, stripe, slack] }
    budget: { api_calls: 40, spend_usd: 100 }
  - role: triage-agent
    permissions: { read: [zendesk, slack], write: [zendesk, slack] }
    budget: { api_calls: 30 }
```

```bash
uv run volnix serve dynamic_support_center \
  --internal agents_dynamic_support --port 8080
```

See [docs/internal-agents.md](docs/internal-agents.md) for the complete guide.

---

## External Agents

Connect your own agent — CrewAI, PydanticAI, LangGraph, AutoGen, OpenClaw, or any HTTP client. Your agent connects via MCP, REST, or native SDK and interacts with the world as if it were real services. It doesn't know it's in a simulation. The governance pipeline enforces rules on every action.

```
┌─────────────────────────────────┐      ┌──────────────────────────────────┐
│        YOUR AGENTS              │      │           VOLNIX                 │
│                                 │      │                                  │
│  CrewAI / LangGraph / PydanticAI│─MCP─▶│  Gateway                         │
│  OpenAI SDK / Anthropic SDK     │─REST─▶│   │                             │
│  Claude Desktop / Cursor        │─MCP─▶│    ▼                             │
│  Custom HTTP client             │─HTTP─▶│  7-Step Pipeline                │
│                                 │      │    │                             │
│                                 │      │    ▼                             │
│                                 │      │  Simulated Services              │
│                                 │      │  (Stripe, Zendesk, Slack, ...)   │
└─────────────────────────────────┘      │    │                             │
                                         │    ▼                             │
                                         │  World State + Causal Graph      │
                                         │  Scorecards + Event Log          │
                                         └──────────────────────────────────┘
```

| Protocol | Endpoint | Best For |
|----------|----------|----------|
| **MCP** | `http://localhost:8080/mcp` | Claude Desktop, Cursor, Windsurf, PydanticAI |
| **OpenAI compat** | `http://localhost:8080/openai/v1/` | OpenAI SDK, LangGraph, AutoGen |
| **Anthropic compat** | `http://localhost:8080/anthropic/v1/` | Anthropic SDK |
| **Gemini compat** | `http://localhost:8080/gemini/v1/` | Google Gemini SDK |
| **REST API** | `http://localhost:8080/api/v1/` | Custom agents, scripts, any HTTP client |

```bash
uv run volnix serve customer_support --port 8080
```

```python
# PydanticAI via MCP — zero Volnix imports
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStreamableHTTP

server = MCPServerStreamableHTTP("http://localhost:8080/mcp/")
agent = Agent("openai:gpt-4.1-mini", toolsets=[server])

async with agent:
    result = await agent.run("Check the support queue and handle urgent tickets.")
```

See [docs/agent-integration.md](docs/agent-integration.md) for the full guide.

---

## Two Modes Control How Alive the World Is

| Mode | The world... | Use when... |
|------|-------------|-------------|
| **Static** | Frozen after compilation. Only agents move. | Deterministic, reproducible benchmarks |
| **Dynamic** | Lives on its own. NPCs create events, follow up, escalate, change their minds. | Testing how agents handle a world that doesn't wait |

Internal agent teams require `dynamic` mode — the Animator generates organic events that drive agent activations. External agents can use either mode.

---

## The 7-Step Governance Pipeline

Every action — from any agent, internal or external, through any protocol — flows through this pipeline before it touches the world:

```
  ┌──────────┐   ┌────────┐   ┌────────┐   ┌────────────┐   ┌───────────┐   ┌────────────┐   ┌────────┐
  │Permission│──▶│ Policy │──▶│ Budget │──▶│ Capability │──▶│ Responder │──▶│ Validation │──▶│ Commit │
  └──────────┘   └────────┘   └────────┘   └────────────┘   └───────────┘   └────────────┘   └────────┘
   Can this       Does a       Is there     Does this       Generate the    Is the result    Apply state
   actor do       policy       budget       tool exist?     service         consistent?      changes and
   this?          block it?    remaining?                   response                         record event
```

Each step can halt the action. A refund over $100 gets blocked by policy. A tool call that exceeds the budget is denied. A state mutation that violates consistency is rejected. Every decision is recorded in the causal graph and visible in the dashboard.

---

## What Volnix Is Not

**Not a mock server.** Mock servers return canned responses. Volnix maintains deep, interconnected state — a refund changes the customer's balance, triggers an activity log entry, updates the ticket status, and may cause the customer's sentiment to shift. Actions have consequences. Consequences have consequences.

**Not a test harness.** Test harnesses verify outputs. Volnix evaluates behavior — how your agent handles ambiguity, conflicting information, policy constraints, resource limits, uncooperative actors, and situations it has never seen before.

**Volnix is a world engine.** Describe a reality. Compile it. Turn it on. Put agents inside it. Watch what happens when the world pushes back.

---

## Quick Start

### System Requirements

| Dependency | Version | Purpose |
|-----------|---------|---------|
| **Python** | 3.12+ | Core runtime |
| **uv** | latest | Package manager ([install](https://docs.astral.sh/uv/getting-started/installation/)) |
| **SQLite** | 3.35+ | Bundled with Python — no separate install needed |
| **Node.js** | 18+ | Dashboard only (optional) |
| **LLM API key** | any one | Google (`GOOGLE_API_KEY`), OpenAI (`OPENAI_API_KEY`), or Anthropic (`ANTHROPIC_API_KEY`). See [docs/llm-providers.md](docs/llm-providers.md) |

### Install

```bash
# From PyPI
pip install volnix

# Or from source
git clone https://github.com/janaraj/volnix.git
cd volnix
uv sync --all-extras

# Set an LLM provider (at least one required)
export GOOGLE_API_KEY=AIza...
export OPENAI_API_KEY=sk-...         # optional, needed for agency engine
export ANTHROPIC_API_KEY=sk-ant-...  # optional

# Verify setup
volnix check
```

### Dashboard (optional — requires source install)

The React dashboard is not included in the pip package. Clone the repo to use it:

```bash
git clone https://github.com/janaraj/volnix.git
cd volnix/volnix-dashboard
npm install && npm run dev
# Open http://localhost:3000 — connects to any running Volnix server
```

---

## Defining Worlds

Worlds are defined in YAML under a single `world:` section:

```yaml
world:
  name: "Customer Support"
  description: "A mid-size SaaS company support team handling tickets and refunds."
  behavior: dynamic             # static | dynamic
  mode: governed                # governed | ungoverned
  reality:
    preset: messy               # ideal | messy | hostile

  services:
    gmail: verified/gmail
    slack: verified/slack
    zendesk: verified/zendesk
    stripe: verified/stripe

  actors:
    - role: support-agent
      type: external
      count: 2
      permissions:
        read: [gmail, slack, zendesk, stripe]
        write: [gmail, slack, zendesk]
      budget:
        api_calls: 500
        llm_spend: 10.00

    - role: supervisor
      type: internal
      personality: "Experienced and cautious. Asks clarifying questions."

  policies:
    - name: "Refund approval"
      trigger: "refund amount exceeds agent authority"
      enforcement: hold
      hold_config:
        approver_role: supervisor
        timeout: "30m"

  seeds:
    - "VIP customer has been waiting 7 days for a $249 refund"
    - "Three tickets are past SLA deadline"
```

Or create a world from natural language:

```bash
uv run volnix create "Market analysis team with an economist, data analyst, and strategist \
  collaborating via Slack to produce a quarterly prediction" \
  --reality messy --output market_world.yaml
```

### Reality Dimensions

Every world has 5 personality dimensions that shape the data, service behavior, and actor attitudes:

| Dimension | What It Controls | Range |
|-----------|-----------------|-------|
| **Information Quality** | Data staleness, incompleteness, noise | pristine ... chaotic |
| **Reliability** | Service failures, timeouts, degradation | rock_solid ... barely_functional |
| **Social Friction** | Actor cooperation, deception, hostility | everyone_helpful ... actively_hostile |
| **Complexity** | Ambiguity, edge cases, contradictions | straightforward ... overwhelmingly_complex |
| **Boundaries** | Access limits, rule clarity, enforcement gaps | locked_down ... wide_open |

Three presets bundle these: `ideal` (best case), `messy` (realistic, default), `hostile` (adversarial).

---

## Verified Service Packs

Each verified pack simulates a real service with deterministic state machines — no LLM at runtime. For services without a verified pack, Volnix supports YAML profiles, OpenAPI specs, and zero-config bootstrapping (the compiler generates a profile from real API docs via the Context Hub + LLM inference).

**BYOSP — Bring Your Own Service Pack.** Put any service name in your world YAML. If no verified pack exists, the compiler auto-resolves it. Or write a YAML profile in minutes for curated fidelity. See [docs/service-packs.md](docs/service-packs.md) for the full guide.

| Pack | Category | Simulates |
|------|----------|-----------|
| `gmail` | Communication | Gmail API (messages, drafts, labels, threads) |
| `slack` | Communication | Slack API (channels, messages, reactions, threads) |
| `zendesk` | Work Management | Zendesk API (tickets, users, organizations) |
| `stripe` | Payments | Stripe API (charges, customers, refunds, invoices) |
| `github` | Code/DevOps | GitHub API (repos, issues, PRs, commits) |
| `google_calendar` | Scheduling | Calendar API (events, calendars, attendees) |
| `twitter` | Social | Twitter API (tweets, replies, followers) |
| `reddit` | Social | Reddit API (posts, comments, subreddits) |
| `notion` | Documents | Notion API (pages, databases, blocks, search) |
| `alpaca` | Trading | Alpaca API (orders, positions, market data) |
| `browser` | Web | HTTP browsing (GET/POST to custom sites) |

---

## Built-in Blueprints

### World Definitions

Worlds with `Dynamic` behavior generate organic events and work with `--internal` agent teams. `Static` worlds are frozen after compilation.

| Blueprint | Domain | Behavior | Services |
|-----------|--------|----------|----------|
| `customer_support` | Support | Static | Gmail, Slack, Zendesk, Stripe |
| `demo_support_escalation` | Support | Dynamic | Stripe, Zendesk, Slack |
| `dynamic_support_center` | Support | Dynamic | Stripe, Zendesk, Slack |
| `incident_response` | DevOps | Dynamic | Slack, GitHub, Calendar |
| `stock_analysis` | Finance | Static | Alpaca |
| `market_prediction_analysis` | Finance | Dynamic | Slack, Twitter, Reddit |
| `notion_project_tracker` | Product | Static | Notion, Slack |
| `hubspot_sales_pipeline` | Sales | Dynamic | HubSpot (Tier 2), Slack |
| `campaign_brainstorm` | Marketing | Dynamic | Slack |
| `climate_research_station` | Research | Dynamic | Slack, Gmail |
| `feature_prioritization` | Product | Dynamic | Slack |
| `security_posture_assessment` | Security | Dynamic | Slack, Zendesk |
| `open_sandbox` | Testing | Static | All services (ungoverned) |

### Internal Agent Team Profiles

Pair these with a world definition using `--internal`:

| Profile | Team Size | Roles | Deliverable |
|---------|-----------|-------|-------------|
| `agents_support_team` | 3 | Supervisor, Senior-agent, Triage-agent | Synthesis |
| `agents_dynamic_support` | 3 | Supervisor, Senior-agent, Triage-agent | Synthesis |
| `agents_market_analysts` | 3 | Macro-economist, Technical-analyst, Risk-analyst | Prediction |
| `agents_climate_researchers` | 4 | Lead-researcher, Physicist, Oceanographer, Statistician | Synthesis |
| `agents_campaign_creatives` | 3 | Creative-director, Copywriter, Social-media-specialist | Brainstorm |
| `agents_feature_team` | 3 | Product-lead, Engineer, Designer | Decision |
| `agents_security_team` | 3 | Security-lead, Network-engineer, Compliance-officer | Assessment |

```bash
# List all blueprints
uv run volnix blueprints

# Example: market analysis with internal team
uv run volnix serve market_prediction_analysis \
  --internal agents_market_analysts --port 8080
```

See [docs/blueprints-reference.md](docs/blueprints-reference.md) for the full catalog.

---

## CLI Commands

| Command | Description |
|---------|------------|
| `volnix create <description>` | Generate a world YAML from natural language |
| `volnix run <world>` | Compile and execute a simulation |
| `volnix serve <world>` | Start HTTP/MCP servers for agent connections |
| `volnix dashboard` | Start the API server for browsing historical runs (no world needed) |
| `volnix mcp` | Start MCP stdio server (for agent subprocesses) |
| `volnix blueprints` | List available world blueprints and presets |
| `volnix check` | System health check (Python, packages, LLM providers) |
| `volnix report [run_id]` | Generate governance report for a run |
| `volnix inspect <run_id>` | Deep dive into run details |
| `volnix diff <run1> <run2>` | Compare two runs |
| `volnix list` | List runs, tools, services, engines |
| `volnix show <id>` | Show details of a run, tool, or service |
| `volnix ledger` | Query and display audit ledger entries |
| `volnix config` | Export configuration for agent integration |

Key flags for `serve` and `run`:

| Flag | Purpose | Example |
|------|---------|---------|
| `--internal <yaml>` | Run with an internal agent team | `--internal agents_support_team` |
| `--agents <yaml>` | External agent permissions/budgets | `--agents external_agents.yaml` |
| `--behavior <mode>` | Override behavior: static, dynamic | `--behavior static` |
| `--deliverable <type>` | Deliverable type: synthesis, decision, prediction | `--deliverable synthesis` |
| `--world <id>` | Use existing compiled world (skip compilation) | `--world world_83a6d1e3` |
| `--port <n>` | HTTP server port | `--port 8080` |

---

## Configuration

Volnix uses a layered TOML configuration system:

| Layer | File | Purpose |
|-------|------|---------|
| Base | `volnix.toml` | Shipped defaults (committed to repo) |
| Environment | `volnix.{env}.toml` | Environment-specific overrides |
| Local | `volnix.local.toml` | Machine-specific, git-ignored |
| Env vars | `VOLNIX__section__key` | Runtime overrides |

See [docs/configuration.md](docs/configuration.md) and `volnix.toml` for the complete reference.

### LLM Providers

Volnix supports any OpenAI SDK-compatible provider, plus native Gemini, Anthropic, CLI tools, and ACP (Agent Communication Protocol). Different engine tasks route to different providers — use a cheap model for compilation, a strong model for agent reasoning, and a local model for the animator.

| Provider Type | Examples | Auth |
|---|---|---|
| `google` | Gemini (native) | `GOOGLE_API_KEY` |
| `anthropic` | Claude (native) | `ANTHROPIC_API_KEY` |
| `openai_compatible` | OpenAI, Gemini-via-OpenAI, Ollama, vLLM, Together, Groq | `*_API_KEY` or none |
| `cli` | `claude`, `codex`, `gemini` CLI tools | Provider-managed |
| `acp` | `codex-acp`, `claude-agent-acp` | Provider-managed |

See [docs/llm-providers.md](docs/llm-providers.md) for the full provider guide, tested models, and how to add custom providers.

---

## Architecture

Volnix is built on a **two-half architecture**:

**World Law (Deterministic Engine)** owns state, events, the causal graph, permissions, policy enforcement, budget accounting, time, visibility, mutation validation, and replay. The engine never guesses and never generates text. It enforces structure.

**World Content (Generative Layer)** creates realistic data, service behavior, actor responses, and scenario complications. But it operates inside constraints set by the engine. The generative layer proposes; the engine disposes.

### The 10 Engines

| Engine | Responsibility |
|--------|---------------|
| **World Compiler** | Transforms NL/YAML into runnable worlds |
| **State Engine** | Single source of truth for all entities |
| **Policy Engine** | Evaluates governance rules (hold, block, escalate, log) |
| **Permission Engine** | RBAC + visibility scoping per actor |
| **Budget Engine** | Tracks resource consumption (API calls, LLM spend, time) |
| **World Responder** | Generates service responses within constraints |
| **World Animator** | Generates events between agent turns (dynamic mode) |
| **Agency Engine** | Manages internal actor lifecycle and collaboration |
| **Agent Adapter** | Translates between external protocols and internal actions |
| **Report Generator** | Produces scorecards, gap logs, causal traces |

---

## Dashboard

Volnix includes a React dashboard for observing simulations in real time. Start it alongside any `serve` command:

```bash
cd volnix-dashboard && npm run dev    # http://localhost:3000
```

Features: run history, live event streaming (WebSocket), governance scorecards, policy trigger logs, deliverable inspection, agent activity timeline, entity browser.

---

## Project Structure

```
volnix/
  core/           # Types, protocols, event bus, envelope, context
  engines/        # The 10 engines (state, policy, permission, budget, ...)
  pipeline/       # 7-step governance pipeline (DAG executor)
  bus/            # Event bus (inter-engine communication)
  ledger/         # Audit log (observability)
  packs/          # Service packs (verified + profiled)
  kernel/         # Semantic kernel (service classification)
  llm/            # LLM router (multi-provider routing)
  persistence/    # SQLite async persistence layer
  simulation/     # SimulationRunner, EventQueue, config
  actors/         # Actor state, subscriptions, replay
  gateway/        # External request gateway
  blueprints/     # Official world blueprints and agent profiles
  cli.py          # CLI entry point (typer)
  app.py          # Application bootstrap
docs/             # User-facing guides
examples/         # Integration examples (OpenAI, Anthropic, Gemini, etc.)
internal_docs/    # Specifications and architecture documents
```

---

## Documentation

| Document | Description |
|----------|------------|
| [Getting Started](docs/getting-started.md) | Installation, first run, connecting agents |
| [Creating Worlds](docs/creating-worlds.md) | World YAML schema, reality dimensions, seeds |
| [Internal Agents](docs/internal-agents.md) | Agent teams, lead coordination, deliverables |
| [Agent Integration](docs/agent-integration.md) | MCP, REST, SDK, framework adapters |
| [Behavior Modes](docs/behavior-modes.md) | Static vs dynamic, Animator engine |
| [Blueprints Reference](docs/blueprints-reference.md) | Complete catalog of blueprints and pairings |
| [Service Packs & Profiles](docs/service-packs.md) | Verified packs, YAML profiles, fidelity tiers, custom services |
| [LLM Providers](docs/llm-providers.md) | Provider types, tested models, custom providers |
| [Configuration](docs/configuration.md) | TOML config system, LLM providers, tuning |
| [Architecture](docs/architecture.md) | Two-half model, 10 engines, governance pipeline |
| [Vision](docs/volnix-vision.md) | Where Volnix is heading — world memory, generative worlds, visual reality |
| [Design Principles](DESIGN_PRINCIPLES.md) | Architectural rules and patterns |
| [Contributing](CONTRIBUTING.md) | Development setup, code standards, PR process |

---

## Development

```bash
# Install with dev dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Run a single test file
uv run pytest tests/simulation/test_runner.py -v

# Lint
uv run ruff check volnix/ tests/

# Format check
uv run ruff format --check volnix/ tests/

# Type check
uv run mypy volnix/
```

---

## Vision

Volnix today creates worlds that are believable at the API level — realistic data, consistent state, cascading consequences, actors with personalities. This is Stage 1.

Where it's heading:

| Stage | What changes |
|-------|-------------|
| **World Memory** | Actors remember past interactions across runs. The customer who was angry last simulation remembers being angry. Persistent worlds that evolve. |
| **Deep Cross-Service Consistency** | A company announces layoffs → employee morale drops → Slack messages become cautious → some employees start job searching → spending patterns change. One event creates coherent ripples across every service. |
| **Generative Worlds** | You don't define what happens — you define initial conditions and the world writes its own story. "50-person startup, Series A, one toxic executive." Press play. Six months unfold. |
| **Visual Reality** | The world isn't just APIs and reports. A 3D trading floor with characters at desks. A startup office where you watch the designer working late. Opinion clusters forming in a town square as misinformation spreads. |

The primitive isn't "agent." The primitive is **world** — a reality with services, actors, events, policies, and information physics. What you do with that world is up to you: agent testing, behavioral research, outcome prediction, collaborative intelligence, synthetic data generation, or automated agent evolution.

Read the full vision: [docs/volnix-vision.md](docs/volnix-vision.md)

---

## Acknowledgments

- [Context Hub](https://github.com/andrewyng/context-hub) by Andrew Ng — curated, versioned documentation for coding agents. Volnix uses Context Hub for dynamic API schema extraction during service profile resolution, fetching real documentation to build accurate service surfaces directly without LLM inference.

## License

MIT License. See [LICENSE](LICENSE) for details.

Copyright (c) 2026 Janarthanan Rajendran
