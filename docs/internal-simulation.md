# Internal Simulation

This guide covers Volnix's internal agent mode: how LLM-powered actors collaborate autonomously within a world, how they activate, communicate, and produce deliverables.

---

## Overview

In internal-only simulations, all actors are LLM-driven. They collaborate through the world's communication services (Slack, email, etc.), respond to each other's messages, and work toward a deliverable. No external agent is needed.

```bash
volnix run market_prediction_analysis \
  --preset prediction \
  --actors economist,data-analyst,strategist
```

This creates a world where three internal actors discuss market conditions on Slack, each contributing their expertise, and the lead actor synthesizes the discussion into a structured prediction deliverable.

---

## How Internal Actors Work

### Activation

After each committed event, the Agency Engine determines which actors should respond. Activation happens through two mechanisms:

**Tier 1: Deterministic Check (no LLM)**

The engine checks if actors should activate based on:
- **Event-affected**: a watched entity was modified
- **Referenced**: the actor was mentioned in the event's data
- **Wait-threshold**: the actor has been waiting too long for a response
- **Frustration-threshold**: the actor's frustration level crossed a threshold
- **Scheduled action**: a previously scheduled action is due

**Subscription-Based Activation (collaborative communication)**

Actors subscribe to services and channels. When an event matches an actor's subscription, they may activate based on sensitivity:

| Sensitivity | Behavior |
|------------|----------|
| `immediate` | Activate right away |
| `batch` | Accumulate N notifications before activating (reduces LLM calls) |
| `passive` | Record the event but don't activate (actor can review later) |

### Action Generation

Activated actors are classified into tiers for LLM calls:

| Tier | When | How |
|------|------|-----|
| **Tier 2 (Batch)** | Low-stakes, routine responses | Multiple actors in one LLM call |
| **Tier 3 (Individual)** | High-stakes, complex situations | Dedicated LLM call per actor |

An actor is promoted to Tier 3 when:
- Frustration exceeds the configured threshold
- The actor's role is in `high_stakes_roles`
- The actor has high deception risk or authority level
- The activation was subscription-triggered (needs full conversation context)

### The LLM Prompt

Each actor's prompt includes:
- **System prompt**: world context, team roster, available actions
- **Actor persona**: role, personality traits, behavior description
- **Recent interactions**: conversation history (last 20 interactions)
- **Pending notifications**: events the actor hasn't responded to
- **Available actions**: what the actor can do (e.g., `chat.postMessage`, `email_send`)
- **Team roster**: who else is in the world (for `intended_for` tagging)

The LLM returns a JSON response:

```json
{
  "action_type": "chat.postMessage",
  "target_service": "slack",
  "payload": {
    "channel_id": "C-general",
    "text": "Based on the Q3 data, I see a 15% uptick in the sector...",
    "intended_for": ["all"]
  },
  "reasoning": "Sharing initial analysis to start the discussion."
}
```

If the actor has nothing to say, it returns `"action_type": "do_nothing"`.

---

## Communication Flow

Internal actors communicate through the world's services, just like real people would:

```
1. Lead actor posts kickstart message to Slack (intended_for: ["all"])
         |
2. All actors with Slack subscriptions are notified
         |
3. Each activated actor reads the message, thinks (LLM), and responds
         |
4. Responses are posted back to Slack
         |
5. Other actors see the responses and may activate again
         |
6. Conversation continues until:
    - The deliverable deadline is reached
    - All actors return do_nothing (idle stop)
    - The tick limit is hit
```

### Intended-For Tagging

Actors can direct messages to specific team members using the `intended_for` field:

```json
{
  "intended_for": ["all"]              // Everyone sees it
  "intended_for": ["economist"]         // Only the economist activates
  "intended_for": ["analyst", "strategist"]  // Two specific actors
}
```

In `tagged` collaboration mode (the default), only tagged actors activate. In `open` mode, all subscribed actors see everything.

---

## Deliverables

Deliverables are structured outputs produced at the end of a simulation. The lead actor (first role in `--actors`) synthesizes the team's conversation into a JSON document.

### Presets

Volnix includes built-in deliverable presets:

| Preset | Output Schema |
|--------|--------------|
| `prediction` | Predictions with confidence levels, methodology, risk factors |
| `brainstorm` | Ideas with feasibility scores, pros/cons, prioritization |
| `decision` | Options analysis, recommendation, dissenting views |
| `recommendation` | Ranked recommendations with rationale |
| `assessment` | Findings, risk levels, remediation steps |
| `synthesis` | General summary with key themes and takeaways |

```bash
volnix run climate_research_station \
  --preset assessment \
  --actors lead-researcher,climate-scientist,data-analyst
```

### How Deliverables Work

1. At compile time, the lead actor gets a `scheduled_action` set to fire at tick `N * (1 - synthesis_buffer_pct)` (e.g., tick 13 out of 15)
2. When the deadline tick arrives, the Agency Engine activates the lead actor with the `produce_deliverable` action
3. The lead actor's prompt includes the full conversation history and the deliverable schema
4. The LLM synthesizes the discussion into a structured JSON matching the schema
5. The simulation ends with `DELIVERABLE_PRODUCED`

### Viewing Deliverables

```bash
# Terminal
volnix report last

# API
curl http://localhost:8080/api/v1/runs/{run_id}/deliverable

# Dashboard
# Navigate to the run and click the "Deliverable" tab
```

---

## Simulation Lifecycle

### End Conditions

Internal-only simulations can end for these reasons:

| Condition | Description |
|-----------|-------------|
| `DELIVERABLE_PRODUCED` | The lead actor produced the deliverable |
| `IDLE_STOP` | All actors returned do_nothing for N consecutive ticks |
| `TICK_LIMIT` | Hard tick limit reached (default: 200, typically overridden) |
| `MAX_EVENTS_REACHED` | Total committed events hit the safety cap |
| `MAX_TIME_REACHED` | Logical time exceeded the maximum |
| `QUEUE_EMPTY` | No pending actions and no scheduled future work |

### Time Advancement

In internal-only simulations, logical time advances by `tick_interval_seconds` (default: 60s) per committed event. Each event = 1 tick.

When the event queue is empty but scheduled actions exist in the future, the runner fast-forwards time to the next scheduled action. This ensures deliverable deadlines are always reached, even if the conversation naturally pauses.

### Idle Detection

If actors produce `do_nothing` actions for `idle_stop_ticks` consecutive ticks (default: 5), the simulation stops with `IDLE_STOP`. This prevents infinite loops when actors have nothing more to say.

---

## Configuration

Key settings for internal simulations:

```toml
# volnix.toml

[simulation_runner]
max_ticks = 30                      # Hard tick limit
max_total_events = 50               # Max committed events

[agency]
max_concurrent_actor_calls = 20     # Parallel LLM calls
collaboration_mode = "tagged"       # "tagged" | "open"
collaboration_enabled = true        # Enable subscription activation
synthesis_buffer_pct = 0.10         # Reserve 10% of ticks for deliverable
max_recent_interactions = 20        # Conversation history per actor
```

---

## Running Internal Simulations

### Basic

```bash
volnix run customer_support \
  --actors support-lead,agent-1,supervisor
```

### With Deliverable

```bash
volnix run market_prediction_analysis \
  --preset prediction \
  --actors economist,analyst,strategist
```

### With Server (observe via dashboard)

```bash
volnix run market_prediction_analysis \
  --preset prediction \
  --actors economist,analyst,strategist \
  --serve --port 8080
```

Then open the dashboard:

```bash
volnix dashboard --port 8200
```

### With Custom Reality

```bash
volnix run feature_prioritization \
  --preset decision \
  --actors product-lead,engineer,designer \
  --behavior dynamic
```

---

## Tips

- **3-5 actors is the sweet spot** -- fewer than 3 limits discussion diversity; more than 5 increases LLM cost without proportional benefit
- **The first actor is the lead** -- they produce the deliverable, so choose the role that should synthesize
- **Use `tagged` mode for efficiency** -- actors only activate when addressed, reducing unnecessary LLM calls
- **Watch the conversation** -- run with `--serve` and use the dashboard to observe how actors interact in real time
- **Adjust `max_ticks`** -- more ticks = longer discussion = richer deliverable, but also more LLM spend
- **Set `synthesis_buffer_pct`** -- this reserves time at the end for the lead actor to synthesize. 10% (default) means 10% of ticks are reserved for deliverable production
