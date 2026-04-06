# External Demo: E-commerce Order Management

From zero to governed AI in 5 minutes. Two external agents connect via OpenAI SDK — Volnix enforces governance automatically.

## Quick start

```bash
# All-in-one: compiles world, starts server, runs agents
cd /path/to/volnix
bash examples/launch-demo/external/run.sh
```

Or step by step:

```bash
# Terminal 1: Start Volnix
uv run volnix serve demo_ecommerce \
  --agents examples/launch-demo/external/agents.yaml --port 8080

# Terminal 2: Run agents
uv run python examples/launch-demo/external/run.py

# Terminal 3: Dashboard
cd volnix-dashboard && npm run dev
```

## The world (20 lines of YAML)

```yaml
world:
  name: "E-commerce Support"
  services:
    stripe: verified/stripe
    zendesk: verified/zendesk
    slack: verified/slack
  policies:
    - name: "Block large refunds"
      trigger:
        action: "create_refund"
        condition: "input.amount > 25000"
      enforcement: block
      reason: "Refunds over $250 require manager approval"
  seeds:
    - "Customer Bob filed refund request for $45"
    - "Customer Carol reports wrong item shipped"
  reality:
    preset: messy
  mode: governed
  behavior: reactive
```

## Two agents, different outcomes

| Action | support-bot | admin |
|--------|------------|-------|
| `tickets.list` | OK | OK |
| `create_refund($45)` | BLOCKED_AT_PERMISSION | OK |
| `create_refund($500)` | BLOCKED_AT_PERMISSION | BLOCKED_AT_POLICY |
| `chat.postMessage` | OK | OK |

Same tasks, different governance outcomes. The support-bot can't write to Stripe (permission). The admin can, but policy caps refunds at $250.

## How it works

1. **YAML blueprint** defines the world: services, policies, seeds, reality
2. **`volnix serve`** compiles the world (generates entities from seeds) and starts the server
3. **Agents connect** via standard OpenAI SDK — zero Volnix imports needed
4. **Governance enforced** automatically: permission → policy → budget → responder → commit
5. **Dashboard** shows everything: events, scorecard, entities, budget status

## Files

- World: `volnix/blueprints/official/demo_ecommerce.yaml`
- Agents: `examples/launch-demo/external/agents.yaml`
- Script: `examples/launch-demo/external/run.py`
