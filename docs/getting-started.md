# Getting Started

This guide walks you through installing Volnix, running your first simulation, and connecting an AI agent.

---

## 1. Install Volnix

**Requirements:** Python 3.12+

```bash
# With pip
pip install volnix

# With uv (recommended for faster installs)
uv pip install volnix

# From source (for development)
git clone https://github.com/janaraj/volnix.git
cd volnix
uv sync --all-extras
```

## 2. Configure an LLM Provider

Volnix uses LLMs for world compilation (generating entities, data, actor personalities) and for internal actor responses. You need at least one provider configured.

```bash
# Pick one (or more):
export ANTHROPIC_API_KEY=sk-ant-...    # Claude
export OPENAI_API_KEY=sk-proj-...      # OpenAI
export GOOGLE_API_KEY=AIza...          # Google Gemini
```

You can also use local providers like Ollama (no API key needed) or CLI-based providers like `claude` or `codex` that use their own authentication. See [configuration.md](configuration.md) for details.

**Verify your setup:**

```bash
volnix check
```

This shows your Python version, installed packages, and which LLM providers are available.

## 3. Explore Built-in Blueprints

Volnix ships with pre-built world blueprints you can run immediately:

```bash
volnix blueprints
```

You'll see blueprints like `customer_support`, `incident_response`, `open_sandbox`, `market_prediction_analysis`, and more.

## 4. Run Your First Simulation

### Option A: Internal Agents (autonomous multi-agent simulation)

Internal agents are LLM-powered actors that collaborate within the world without external input. This is the fastest way to see Volnix in action:

```bash
# Run a 3-agent support team — compiles the world and runs immediately
uv run volnix run demo_support_escalation \
  --internal volnix/blueprints/official/agents_support_team.yaml
```

This compiles the `demo_support_escalation` blueprint, runs a 3-agent team (supervisor, senior-agent, triage-agent), and prints a report when they finish. They collaborate via Slack, investigate tickets, process refunds, and produce a deliverable. The run takes about 60-120 seconds depending on your LLM provider.

Add `--serve --port 8080` to also expose MCP/HTTP endpoints while the simulation runs (useful for connecting additional observers or external tools).

You can also run with a dynamic world where NPC customers generate new events:

```bash
uv run volnix run dynamic_support_center \
  --internal volnix/blueprints/official/agents_dynamic_support.yaml
```

See [internal-agents.md](internal-agents.md) for the full guide on agent teams, lead coordination, and deliverables.

### Option B: External Agent (connect your own AI agent)

Start Volnix as a server and connect your own agent via any supported protocol:

```bash
# Terminal 1: Start the server
uv run volnix serve customer_support --port 8080
```

```bash
# Terminal 2: Connect using the OpenAI SDK (or Anthropic, Gemini, MCP, etc.)
cd examples/openai-sdk
uv run python main.py
```

The agent fetches tools from Volnix in its native format and interacts with the simulated world. See [agent-integration.md](agent-integration.md) for all supported protocols and [examples/](../examples/) for working code.

## 5. View Results

### Terminal report (printed automatically after `volnix run`)

The CLI prints a governance scorecard after every run. To re-read any past run:

```bash
uv run volnix report last
```

### Run artifacts

Every run saves artifacts to `~/.volnix/runs/<run_id>/`:

| File | Contents |
|------|----------|
| `report.json` | Full report: scorecard, gap log, condition analysis |
| `scorecard.json` | Per-actor behavioral scores |
| `decision_trace.json` | Activation timeline — what each agent did, why governance intervened, what committed, information coverage |
| `event_log.json` | Raw event log in chronological order |
| `config.json` | Blueprint config snapshot for this run |

The decision trace is the most informative artifact for understanding agent behavior:

```bash
# Inspect the decision trace for the last run
cat ~/.volnix/runs/$(ls -t ~/.volnix/runs | head -1)/decision_trace.json | python3 -m json.tool | head -60
```

### Dashboard

For a richer view with event timelines, scorecards, and deliverable inspection:

```bash
cd volnix-dashboard && npm run dev
```

Open `http://localhost:3000` in your browser. The dashboard shows all historical runs with filtering, search, and side-by-side comparison.

## 6. Create Your Own World

### From natural language

```bash
volnix create "An e-commerce customer service team using Zendesk for tickets, \
  Gmail for email, and Stripe for payments. Include a supervisor who approves \
  refunds over $100." \
  --reality messy \
  --output my_world.yaml
```

This generates a YAML world definition. Review and customize it, then run:

```bash
volnix run my_world.yaml
```

### From YAML directly

Create a file `my_world.yaml`:

```yaml
world:
  name: "My First World"
  description: "A simple world for testing."
  behavior: reactive            # static | reactive | dynamic
  mode: governed                # governed | ungoverned
  reality:
    preset: messy               # ideal | messy | hostile

  services:
    slack: verified/slack
    gmail: verified/gmail

  actors:
    - role: agent
      type: external
      count: 1
      permissions:
        read: [slack, gmail]
        write: [slack, gmail]
      budget:
        api_calls: 200

  seeds:
    - "Three unread emails from different customers"
```

```bash
volnix serve my_world.yaml --port 8080
```

## 7. Next Steps

- [Internal Agents](internal-agents.md) — agent teams, lead coordination, deliverables
- [Creating Worlds](creating-worlds.md) — full YAML schema, reality dimensions, behavior modes
- [Behavior Modes](behavior-modes.md) — static vs reactive vs dynamic, Animator engine
- [Agent Integration](agent-integration.md) — MCP, REST API, Python SDK, framework adapters
- [Blueprints Reference](blueprints-reference.md) — complete catalog of blueprints and pairings
- [Configuration](configuration.md) — TOML config layers, LLM provider setup, server settings
- [Architecture](architecture.md) — the 10 engines, 7-step pipeline, event bus, and design principles
