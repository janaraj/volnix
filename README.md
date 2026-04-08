# Volnix

**Programmable worlds for AI agents.**

Volnix creates stateful, governed realities where AI agents operate as participants — not isolated prompt loops, but actors inside a world with services, policies, budgets, other agents, and real consequences. Describe a world. Compile it. Put agents inside. Watch what happens.

[![PyPI](https://img.shields.io/pypi/v/volnix)](https://pypi.org/project/volnix/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

<p align="center">
  <a href="https://youtu.be/AoWVcPGoj6E">
    <img src="https://img.youtube.com/vi/AoWVcPGoj6E/maxresdefault.jpg" alt="Volnix Demo" width="800">
  </a>
  <br>
  <a href="https://youtu.be/AoWVcPGoj6E">Watch the 1-minute demo</a>
</p>

## Quick Start

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/getting-started/installation/) (recommended), and at least one LLM API key (`GOOGLE_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`). See [docs/llm-providers.md](docs/llm-providers.md) for supported providers.

### Option 1: pip install

```bash
pip install volnix
export GOOGLE_API_KEY=...    # or OPENAI_API_KEY / ANTHROPIC_API_KEY
volnix check                 # verify setup
volnix serve dynamic_support_center --internal agents_dynamic_support --port 8080
```

### Option 2: From source (includes dashboard)

```bash
git clone https://github.com/janaraj/volnix.git && cd volnix
uv sync --all-extras
export GOOGLE_API_KEY=...
uv run volnix serve dynamic_support_center --internal agents_dynamic_support --port 8080

# Dashboard (separate terminal)
cd volnix-dashboard && npm install && npm run dev    # http://localhost:3000
```

> With venv activated (`source .venv/bin/activate`), you can run `volnix` directly instead of `uv run volnix`.

> **Note:** The React dashboard is only available when installed from source. The pip package includes the full backend and CLI.

---

## How It Works

Volnix supports two modes — test your own agents against a governed world, or deploy internal agent teams that collaborate autonomously.

```
  Mode 1: Test Your Agent                 Mode 2: Deploy Agent Teams
  ────────────────────────                ──────────────────────────

  Your Agent (any framework)              Mission + Team YAML
       │                                       │
       ▼                                       ▼
  Gateway (MCP/REST/SDK)                  Lead Agent ──▶ Slack ◀── Agent N
       │                                       │            ▲
       ▼                                       ▼            │
  ┌──────────────────────┐               ┌──────────────────────┐
  │   Volnix World       │               │   Volnix World       │
  │   7-Step Pipeline    │               │   7-Step Pipeline    │
  │   Simulated Services │               │   Simulated Services │
  │   Policies + Budget  │               │   Policies + Budget  │
  │   Static world       │               │   Living world (NPCs)│
  └──────────┬───────────┘               └──────────┬───────────┘
             │                                      │
             ▼                                      ▼
  Scorecard + Event Log                   Deliverable + Scorecard
```

Every action flows through a **7-step governance pipeline** — permission, policy, budget, capability, responder, validation, commit — before it touches the world. Nothing bypasses it.

---

## Internal Agents

Deploy agent teams that coordinate through the world itself — posting in Slack, updating tickets, processing payments. A lead agent manages a 4-phase lifecycle (delegate → monitor → buffer → synthesize) to produce a deliverable.

```yaml
mission: >
  Investigate each open ticket. Process refunds where appropriate.
  Senior-agent handles refunds under $100. Supervisor approves over $100.
deliverable: synthesis

agents:
  - role: supervisor
    lead: true
    permissions: { read: [zendesk, stripe, slack], write: [zendesk, stripe, slack] }
    budget: { api_calls: 50, spend_usd: 500 }
  - role: senior-agent
    permissions: { read: [zendesk, stripe, slack], write: [zendesk, stripe, slack] }
    budget: { api_calls: 40, spend_usd: 100 }
```

See [docs/internal-agents.md](docs/internal-agents.md) for the complete guide.

## External Agents

Connect any agent framework — CrewAI, PydanticAI, LangGraph, AutoGen, or plain HTTP. Your agent interacts with simulated services as if they were real. It doesn't know it's in a simulation.

| Protocol | Endpoint | Best For |
|----------|----------|----------|
| **MCP** | `/mcp` | Claude Desktop, Cursor, PydanticAI |
| **OpenAI compat** | `/openai/v1/` | OpenAI SDK, LangGraph, AutoGen |
| **Anthropic compat** | `/anthropic/v1/` | Anthropic SDK |
| **Gemini compat** | `/gemini/v1/` | Google Gemini SDK |
| **REST** | `/api/v1/` | Any HTTP client |

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

## Key Features

- **7-step governance pipeline** on every action (permission → policy → budget → capability → responder → validation → commit)
- **Policy engine** with block, hold, escalate, and log enforcement modes
- **Budget tracking** per agent (API calls, LLM spend, time)
- **Reality dimensions** — tune information quality, reliability, social friction, complexity, and boundaries
- **11 verified service packs** — Stripe, Zendesk, Slack, Gmail, GitHub, Calendar, Twitter, Reddit, Notion, Alpaca, Browser
- **BYOSP** — bring any service; the compiler auto-resolves from API docs
- **Multi-provider LLM** — Gemini, OpenAI, Anthropic, Ollama, vLLM, CLI tools
- **Real-time dashboard** with event feed, scorecards, and agent timeline
- **Causal graph** — every event traces back to its causes
- **13 built-in blueprints** across support, finance, DevOps, research, security, and marketing

---

## Built-in Blueprints

| Blueprint | Domain | Services | Agent Team |
|-----------|--------|----------|------------|
| `dynamic_support_center` | Support | Stripe, Zendesk, Slack | `agents_dynamic_support` (3) |
| `market_prediction_analysis` | Finance | Slack, Twitter, Reddit | `agents_market_analysts` (3) |
| `incident_response` | DevOps | Slack, GitHub, Calendar | — |
| `climate_research_station` | Research | Slack, Gmail | `agents_climate_researchers` (4) |
| `feature_prioritization` | Product | Slack | `agents_feature_team` (3) |
| `security_posture_assessment` | Security | Slack, Zendesk | `agents_security_team` (3) |

```bash
volnix blueprints                        # list all
volnix serve market_prediction_analysis \
  --internal agents_market_analysts --port 8080
```

See [docs/blueprints-reference.md](docs/blueprints-reference.md) for the full catalog.

---

## Dashboard

```bash
cd volnix-dashboard && npm install && npm run dev    # http://localhost:3000
```

Live event streaming, governance scorecards, policy trigger logs, deliverable inspection, agent activity timeline, entity browser.

---

## Documentation

| Guide | Description |
|-------|-------------|
| [Getting Started](docs/getting-started.md) | Installation, first run, connecting agents |
| [Creating Worlds](docs/creating-worlds.md) | World YAML schema, reality dimensions, seeds |
| [Internal Agents](docs/internal-agents.md) | Agent teams, lead lifecycle, deliverables |
| [Agent Integration](docs/agent-integration.md) | MCP, REST, SDK, framework adapters |
| [Blueprints Reference](docs/blueprints-reference.md) | Complete catalog of blueprints and pairings |
| [Service Packs](docs/service-packs.md) | Verified packs, YAML profiles, BYOSP |
| [LLM Providers](docs/llm-providers.md) | Provider types, tested models, routing |
| [Configuration](docs/configuration.md) | TOML config, LLM routing, tuning |
| [Architecture](docs/architecture.md) | Two-half model, 10 engines, pipeline |
| [Vision](docs/volnix-vision.md) | World memory, generative worlds, visual reality |

---

## Development

```bash
uv sync --all-extras          # install
uv run pytest                 # test (2800+ tests)
uv run ruff check volnix/     # lint
uv run ruff format --check volnix/  # format
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and PR process.

---

## Acknowledgments

- [Context Hub](https://github.com/andrewyng/context-hub) by Andrew Ng — curated, versioned documentation for coding agents. Volnix uses Context Hub for dynamic API schema extraction during service profile resolution.

## License

MIT License. See [LICENSE](LICENSE) for details.

