# Terrarium Launch Demos

Two demos showcasing Terrarium from different angles.

## Demo 1: Internal — Customer Support Escalation

**What it shows:** Terrarium as a world engine. 3 internal agents collaborate to handle a support queue with dynamic world events, tiered permissions, policy enforcement, budget tracking, and a team deliverable.

**Engines highlighted:** World Compiler, State, Policy, Permission, Budget, Responder (Tier 1 packs), Animator (dynamic), Agent Adapter, Report Generator.

```bash
# Terminal 1: Start Terrarium with internal agents
cd /path/to/terrarium
bash examples/launch-demo/internal/run.sh

# Terminal 2: Start dashboard
cd terrarium-dashboard && npm run dev
# Open http://localhost:3000
```

See [internal/README.md](internal/README.md) for details.

---

## Demo 2: External — E-commerce Order Management

**What it shows:** Governed AI in 5 minutes. Write YAML, compile, serve, connect any agent (OpenAI SDK, zero imports), governance enforced automatically.

**Engines highlighted:** World Compiler, Permission, Policy, Budget, Responder, Dashboard observability.

```bash
# Option A: All-in-one (compiles + serves + runs agents)
cd /path/to/terrarium
bash examples/launch-demo/external/run.sh

# Option B: Step by step
uv run terrarium serve demo_ecommerce \
  --agents examples/launch-demo/external/agents.yaml --port 8080
# In another terminal:
uv run python examples/launch-demo/external/run.py
```

See [external/README.md](external/README.md) for details.

---

## What to look for in the Dashboard

| Tab | What it shows |
|-----|--------------|
| **Live Console** | Real-time event stream, color-coded (green = OK, red = blocked) |
| **Overview** | Governance score, event counts, actor summary |
| **Deliverable** | Team output (internal demo only) |
| **Scorecard** | Per-agent governance metrics |
| **Events** | Full causal trace with filtering |
| **Entities** | Tickets, charges, refunds, messages created/modified |
| **Conditions** | Reality dimensions (messy preset values) |
