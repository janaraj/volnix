# Behavior Modes

Volnix worlds have three behavior modes that control whether the world evolves between agent actions. The mode is set in the world YAML and can be overridden at runtime.

---

## The Three Modes

| Mode | Animator | World Evolution | Reproducibility |
|------|----------|----------------|----------------|
| **static** | OFF | World frozen after compilation. Only agent actions change state. | Fully deterministic. Same inputs = same outputs. |
| **reactive** | Cause-effect only | World responds to agent actions and inaction. No autonomous events. | Same agent actions = same reactions. |
| **dynamic** | Fully active | World generates organic events — NPCs create tickets, follow up, escalate, complain. | Seeds provide similar character but not exact replay. |

### Setting the Mode

In your world YAML:

```yaml
world:
  name: "Customer Support"
  behavior: dynamic        # static | reactive | dynamic
```

Override at runtime with the `--behavior` flag:

```bash
# Run the same compiled world in static mode (no NPC events)
uv run volnix serve --world world_83a6d1e351f5 \
  --internal agents_support_team.yaml \
  --behavior static \
  --port 8080
```

This lets you test the same world under different conditions without recompilation.

---

## Static Mode

The simplest mode. After compilation, the world is frozen:

- No NPC events. No new tickets appear. No customers follow up.
- Agents work only with the data that exists at compilation time.
- Fully deterministic — running twice with the same agents produces identical results.
- Best for: benchmarking, testing governance rules, reproducible evaluation.

```bash
uv run volnix serve customer_support --behavior static --port 8080
```

---

## Reactive Mode

The world responds to agent actions but doesn't generate autonomous events:

- If an agent resolves a ticket, the customer might respond (cause → effect).
- If an agent ignores a ticket too long, the customer might escalate (inaction → consequence).
- No autonomous events — if agents do nothing, the world stays still.
- Same agent actions produce the same reactions.
- Best for: training agents where you want consequences but not surprises.

---

## Dynamic Mode

The world is fully alive. The **Animator engine** generates organic events between agent turns:

- NPCs create new tickets, post follow-up messages, escalate issues.
- Events happen regardless of agent actions — the world has its own heartbeat.
- Agents must react to both existing work and new incoming events.
- Best for: realistic simulations, stress testing, evaluating agent coordination.

```bash
uv run volnix serve dynamic_support_center \
  --internal agents_dynamic_support.yaml \
  --behavior dynamic \
  --port 8080
```

---

## The Animator Engine

The Animator is the engine that makes dynamic (and reactive) worlds come alive. It generates **organic events** — actions taken by NPC actors defined in the world.

### How It Works

1. The world YAML defines NPC actors with roles and personalities:
   ```yaml
   actors:
     - role: frustrated-customer
       type: internal
       count: 3
       personality: "Impatient customers who file tickets and escalate when ignored."
     - role: vip-customer
       type: internal
       count: 2
       personality: "High-value customers with complex billing issues."
   ```

2. Each "tick" of the simulation, the Animator:
   - Calls the LLM with the world context, NPC actors, and available tools
   - The LLM generates organic events (e.g., "frustrated-customer creates a new ticket")
   - Events execute through the governance pipeline like any other action
   - Internal agents are notified and can react

3. The Animator maintains a history of recent organic events and passes it to the LLM each tick, so it varies the actor and action type across ticks.

### Configuration

Animator settings can be defined in the world YAML:

```yaml
world:
  behavior: dynamic
  animator:
    creativity: medium           # low | medium | high
    creativity_budget_per_tick: 1 # Max organic events per tick
    event_frequency: medium      # How often events occur
    escalation_on_inaction: true  # NPCs escalate if agents don't respond
```

Or in `volnix.toml` for global defaults:

```toml
[simulation_runner]
animator_tick_interval = 5       # Ticks between animator fires (prevents feedback loops)
```

### Tick Interval

The `animator_tick_interval` controls how often the Animator generates events relative to agent actions. In internal-only simulations, each committed agent action = 1 tick. With `animator_tick_interval = 5`:

- Tick 0: Animator fires (1 organic event)
- Ticks 1-4: Agents work (no animator)
- Tick 5: Animator fires again (1 organic event)
- ...

This prevents feedback loops where organic events trigger agent responses that trigger more organic events.

### Actor Variety

The Animator rotates through different NPC actors across ticks. It passes a history of recent organic events to the LLM so it doesn't repeat the same actor/action:

```
## Previous Organic Events (from earlier ticks)
Recent organic events (vary the actor and action):
- frustrated-customer: tickets.create (zendesk)
- vip-customer: tickets.create (zendesk)
- frustrated-customer: tickets.comment_create (zendesk)
```

This produces a natural variety — frustrated customers create tickets, VIP customers ask billing questions, and follow-ups arrive on existing issues.

---

## Comparison: Static vs Dynamic Run

Running the same support world with a 3-agent internal team:

| Metric | Static | Dynamic |
|--------|--------|---------|
| Organic NPC events | 0 | ~6 |
| Total events processed | ~25 | ~30 |
| New tickets during run | 0 | 3-5 |
| Agent activations | ~15 | ~20 |
| Deliverable produced | Yes | Yes |
| Run duration | ~60s | ~90s |
| LLM calls | ~30 | ~45 |

Static mode is faster and cheaper. Dynamic mode tests how agents handle incoming work while processing existing tasks.

---

## Next Steps

- [Internal Agents](internal-agents.md) — How agent teams collaborate
- [Creating Worlds](creating-worlds.md) — Define your own world with actors and behavior
- [Configuration](configuration.md) — Tune animator and simulation settings
