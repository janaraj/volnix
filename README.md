# Terrarium

**Programmable worlds for AI agents.**

Terrarium creates stateful, causal, observable realities where AI agents exist as participants — not as isolated prompt loops calling tools, but as actors inside a world that has places, institutions, other agents, budgets, policies, communication systems, and real consequences.

Describe a world in natural language or YAML. Terrarium compiles it into a deep, reproducible simulation. Agents interact through standard protocols (MCP, REST, OpenAI function calling, Anthropic tool use). Everything that happens is recorded, scored, and diffable.

---

## Key Features

- **Natural language world creation** — describe a scenario and Terrarium compiles it into a runnable world with entities, actors, services, policies, and seeded data
- **10-engine governance architecture** — state, policy, permission, budget, responder, animator, agency, adapter, reporter, and feedback engines working in concert
- **7-step governance pipeline** — every action flows through permission, policy, budget, capability, responder, validation, and commit checks
- **Multi-agent simulation** — internal actors collaborate autonomously via LLM; external agents connect via standard protocols
- **11 verified service packs** — Slack, Gmail, GitHub, Zendesk, Stripe, Google Calendar, Twitter, Reddit, Alpaca, and more — each with deterministic state machines
- **Reality dimensions** — tune information quality, reliability, social friction, complexity, and boundaries from ideal to hostile
- **Protocol-native** — MCP server, REST API, OpenAI and Anthropic tool formats, Python SDK
- **One-click agent integration** — `terrarium attach claude-desktop` patches your agent's config automatically
- **React dashboard** — observe simulation events, scorecards, deliverables, and causal traces in real time
- **Reproducible** — seeded worlds produce deterministic state; fork, replay, and diff any run

---

## Quick Start

```bash
# Install
pip install terrarium

# Verify setup
terrarium check

# Run a built-in blueprint with internal agents
terrarium run customer_support --preset brainstorm --actors support-lead,support-agent,supervisor

# View the report
terrarium report last
```

To connect an external AI agent instead:

```bash
# Start Terrarium as a server
terrarium serve customer_support --port 8080

# In another terminal, connect Claude Desktop
terrarium attach claude-desktop --port 8080
```

---

## Installation

**Requirements:** Python 3.12+

```bash
# With pip
pip install terrarium

# With uv (recommended)
uv pip install terrarium

# From source
git clone https://github.com/janaraj/terrarium.git
cd terrarium
uv sync --all-extras
```

### LLM Provider Setup

Terrarium needs an LLM provider for world compilation and internal actor responses. Set at least one:

```bash
# Option 1: Anthropic (Claude)
export ANTHROPIC_API_KEY=sk-ant-...

# Option 2: OpenAI
export OPENAI_API_KEY=sk-proj-...

# Option 3: Google Gemini
export GOOGLE_API_KEY=AIza...

# Option 4: Local via Ollama (no API key needed)
# Configure in terrarium.toml
```

See `.env.example` for all available environment variables.

---

## How It Works

Terrarium is built on a **two-half architecture**:

**World Law (Deterministic Engine)** owns state, events, the causal graph, permissions, policy enforcement, budget accounting, time, visibility, mutation validation, and replay. The engine never guesses and never generates text. It enforces structure.

**World Content (Generative Layer)** creates realistic data, service behavior, actor responses, and scenario complications. But it operates inside constraints set by the engine. The generative layer proposes; the engine disposes.

### The Pipeline

Every agent action flows through a 7-step governance pipeline:

```
Permission --> Policy --> Budget --> Capability --> Responder --> Validation --> Commit
```

Each step can halt the action. A refund that exceeds the agent's authority is held for supervisor approval. An API call that exceeds the budget is denied. A response that violates state consistency is rejected.

### The 10 Engines

| Engine | Responsibility |
|--------|---------------|
| **World Compiler** | Transforms NL/YAML into runnable worlds |
| **State Engine** | Single source of truth for all entities |
| **Policy Engine** | Evaluates governance rules (hold, block, escalate, log) |
| **Permission Engine** | RBAC + visibility scoping per actor |
| **Budget Engine** | Tracks resource consumption (API calls, LLM spend, time) |
| **World Responder** | Generates service responses within constraints |
| **World Animator** | Generates events between agent turns (reactive or dynamic) |
| **Agency Engine** | Manages internal actor lifecycle and collaboration |
| **Agent Adapter** | Translates between external protocols and internal actions |
| **Report Generator** | Produces scorecards, gap logs, causal traces |

---

## Defining Worlds

Worlds are defined in YAML with two sections: `world` (what exists) and `compiler` (how it behaves).

```yaml
world:
  name: "Customer Support"
  description: "A mid-size SaaS company support team handling tickets and refunds."

  services:
    gmail: verified/gmail
    slack: verified/slack
    zendesk: verified/zendesk
    stripe: profiled/stripe

  actors:
    - role: support-agent
      type: external
      count: 2
      permissions:
        read: [gmail, slack, zendesk, stripe]
        write: [gmail, slack, zendesk]
        actions:
          refund_create: { max_amount: 5000 }
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

compiler:
  seed: 42
  behavior: reactive
  mode: governed
  reality:
    preset: messy
```

Or create a world from natural language:

```bash
terrarium create "Market analysis team with an economist, data analyst, and strategist \
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

### Behavior Modes

| Mode | Description |
|------|------------|
| `static` | World frozen after compilation. Fully deterministic. |
| `reactive` | World responds to agent actions. Same actions produce same reactions. |
| `dynamic` | World generates its own events. Fully alive. |

---

## CLI Commands

| Command | Description |
|---------|------------|
| `terrarium create <description>` | Generate a world YAML from natural language |
| `terrarium run <world>` | Compile and execute a simulation |
| `terrarium serve <world>` | Start HTTP/MCP servers for agent connections |
| `terrarium mcp <world>` | Start MCP stdio server (for agent subprocesses) |
| `terrarium dashboard` | Start the React dashboard (historical run viewer) |
| `terrarium blueprints` | List available world blueprints |
| `terrarium report [run_id]` | Generate governance report for a run |
| `terrarium check` | System health check (Python, packages, LLM providers) |
| `terrarium config --export <target>` | Export config for agent integration |
| `terrarium attach <agent>` | Patch agent config to connect to Terrarium |
| `terrarium detach <agent>` | Restore original agent config |
| `terrarium inspect <run_id>` | Deep dive into run details |
| `terrarium diff <run1> <run2>` | Compare two runs |

Run `terrarium --help` or `terrarium <command> --help` for full option details.

---

## Agent Integration

Terrarium speaks multiple protocols. Pick the one your agent uses.

### MCP (Model Context Protocol)

The recommended path for Claude Desktop, Cursor, and Windsurf:

```bash
# Start Terrarium
terrarium serve customer_support --port 8080

# Auto-patch your agent's config
terrarium attach claude-desktop --port 8080   # or: cursor, windsurf
```

Or export the config snippet manually:

```bash
terrarium config --export claude-desktop --port 8080
```

### REST API

For custom agents, scripts, or any HTTP client:

```bash
# List available tools
curl http://localhost:8080/api/v1/tools?format=openai

# Execute a tool
curl -X POST http://localhost:8080/api/v1/actions/email_send \
  -H "Content-Type: application/json" \
  -d '{"actor_id": "my-agent", "arguments": {"to": "user@example.com", "body": "Hello"}}'
```

### Python SDK

```python
from terrarium.sdk import TerrariumClient

async with TerrariumClient(url="http://localhost:8080", actor_id="my-agent") as terra:
    tools = await terra.tools(fmt="openai")
    result = await terra.call("email_send", to="user@example.com", body="Hello")
    print(result)
```

### Framework Integration

Export tool definitions for your framework of choice:

```bash
terrarium config --export openai-tools      # OpenAI function calling
terrarium config --export anthropic-tools   # Anthropic tool use
terrarium config --export langgraph         # LangGraph adapter
terrarium config --export crewai            # CrewAI adapter
terrarium config --export autogen           # AutoGen adapter
```

---

## Configuration

Terrarium uses a layered TOML configuration system:

| Layer | File | Purpose |
|-------|------|---------|
| Base | `terrarium.toml` | Shipped defaults (committed to repo) |
| Environment | `terrarium.{env}.toml` | Environment-specific overrides |
| Local | `terrarium.local.toml` | Machine-specific, git-ignored |
| Env vars | `TERRARIUM__section__key` | Runtime overrides |

Key configuration sections:

```toml
# LLM providers
[llm.providers.anthropic]
type = "anthropic"
api_key_ref = "ANTHROPIC_API_KEY"

[llm.providers.openai]
type = "openai_compatible"
api_key_ref = "OPENAI_API_KEY"

# Simulation defaults
[simulation]
seed = 42
behavior = "dynamic"

# Server settings
[adapter]
host = "0.0.0.0"
port = 8100
```

See `terrarium.toml` for the complete configuration reference.

---

## Built-in Blueprints

| Blueprint | Description |
|-----------|------------|
| `customer_support` | Support team with email, chat, tickets, and payments |
| `incident_response` | Incident triage with Slack, GitHub, and calendar |
| `open_sandbox` | Minimal world for freeform testing |
| `market_prediction_analysis` | Multi-agent market analysis with predictions |
| `campaign_brainstorm` | Campaign planning with creative collaboration |
| `climate_research_station` | Research data generation and analysis |
| `feature_prioritization` | Feature ranking with structured debate |
| `security_posture_assessment` | Security audit simulation |

```bash
# List all blueprints (including user-created)
terrarium blueprints

# Run any blueprint directly
terrarium run incident_response --preset brainstorm --actors oncall,sre,incident-lead
```

---

## Verified Service Packs

Each verified pack simulates a real service with deterministic state machines:

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
| `alpaca` | Trading | Alpaca API (orders, positions, market data) |
| `browser` | Web | HTTP browsing (GET/POST to custom sites) |

---

## Dashboard

Terrarium includes a React dashboard for observing simulations:

```bash
terrarium dashboard --port 8200
# Open http://localhost:8200
```

The dashboard provides:
- Run history with filtering and search
- Live event streaming via WebSocket
- Governance scorecards and metrics
- Deliverable inspection
- Run comparison (side-by-side diff)

---

## Project Structure

```
terrarium/
  core/           # Types, protocols, event bus, envelope, context
  engines/        # The 10 engines (state, policy, permission, budget, ...)
  pipeline/       # 7-step governance pipeline (DAG executor)
  bus/             # Event bus (inter-engine communication)
  ledger/          # Audit log (observability)
  packs/           # Service packs (verified + profiled)
  kernel/          # Semantic kernel (service classification)
  llm/             # LLM router (multi-provider routing)
  persistence/     # SQLite async persistence layer
  scheduling/      # Time-based event scheduling
  simulation/      # SimulationRunner, EventQueue, config
  actors/          # Actor state, subscriptions, replay
  gateway/         # External request gateway
  sdk.py           # Python SDK client
  cli.py           # CLI entry point (typer)
  app.py           # Application bootstrap
```

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
uv run ruff check terrarium/ tests/

# Format check
uv run ruff format --check terrarium/ tests/

# Type check
uv run mypy terrarium/
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines and [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md) for architectural rules.

---

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code standards, and the pull request process.

---

## License

[MIT](LICENSE)
