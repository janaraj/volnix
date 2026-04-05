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

### Option A: Internal Agents (autonomous simulation)

Internal agents are LLM-powered actors that collaborate within the world without external input. This is the fastest way to see Volnix in action:

```bash
volnix run customer_support \
  --preset brainstorm \
  --actors support-lead,support-agent,supervisor
```

This compiles the `customer_support` blueprint, creates internal actors for each role, and runs a simulation where they collaborate via Slack and process tickets. The entire run takes about 30-60 seconds depending on your LLM provider.

### Option B: External Agent (you connect an AI agent)

Start Volnix as a server and connect your own agent:

```bash
# Terminal 1: Start the server
volnix serve customer_support --port 8080
```

```bash
# Terminal 2: Connect Claude Desktop (or Cursor, Windsurf)
volnix attach claude-desktop --port 8080
```

Now open Claude Desktop and ask it to check emails, read tickets, or process a refund. Claude sees Volnix's tools as MCP tools and interacts with the simulated world.

When you're done, detach:

```bash
volnix detach claude-desktop
```

## 5. View Results

### Terminal report

```bash
volnix report last
```

This prints a governance scorecard showing actions taken, policies triggered, budget usage, and capability gaps.

### Dashboard

For a richer view with event timelines, scorecards, and deliverable inspection:

```bash
volnix dashboard --port 8200
```

Open `http://localhost:8200` in your browser. The dashboard shows all historical runs with filtering, search, and side-by-side comparison.

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
volnix run my_world.yaml --serve --port 8080
```

### From YAML directly

Create a file `my_world.yaml`:

```yaml
world:
  name: "My First World"
  description: "A simple world for testing."

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

compiler:
  seed: 42
  behavior: reactive
  mode: governed
  reality:
    preset: messy
```

```bash
volnix serve my_world.yaml --port 8080
```

## 7. Next Steps

- [Creating Worlds](creating-worlds.md) — full YAML schema, reality dimensions, behavior modes
- [Agent Integration](agent-integration.md) — MCP, REST API, Python SDK, framework adapters
- [Configuration](configuration.md) — TOML config layers, LLM provider setup, server settings
- [Architecture](architecture.md) — the 10 engines, 7-step pipeline, event bus, and design principles
- [Internal Simulation](internal-simulation.md) — how internal agents collaborate, activate, and produce deliverables
