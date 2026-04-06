# Internal Agents

Internal agents are LLM-powered actors that collaborate autonomously within a Volnix world. They investigate, communicate, and produce deliverables without any external input. This guide covers how to define agent teams, configure the lead agent, understand collaboration flow, and produce deliverables.

---

## Overview

```
World (compiled from YAML)
  |
  +-- Services (Zendesk, Slack, Stripe, ...)
  +-- Entities (tickets, customers, charges, ...)
  +-- Policies (block refunds > $100, escalate SLA breach, ...)
  |
Internal Agent Team (from --internal YAML)
  |
  +-- Lead Agent (delegates, monitors, synthesizes)
  +-- Sub-Agent 1 (investigates, shares findings)
  +-- Sub-Agent 2 (investigates, shares findings)
  |
  v
Deliverable (synthesis, prediction, decision, ...)
```

Internal agents use the same tools and go through the same 7-step governance pipeline as external agents. The difference: they are activated automatically by the Agency Engine and collaborate via a shared team channel.

---

## Defining an Agent Team

Agent teams are defined in a separate YAML file and paired with a world definition at runtime.

```yaml
# agents_support_team.yaml
mission: >
  Handle the support queue as a team. Investigate every open ticket,
  resolve customer issues, process legitimate refunds, and produce
  a comprehensive evaluation of the support operation.

deliverable: synthesis          # Type: synthesis | prediction | decision | brainstorm | assessment

agents:
  - role: supervisor
    lead: true                  # This agent coordinates the team
    personality: >
      Experienced support manager who delegates effectively
      and synthesizes team findings into actionable reports.
    permissions:
      read: [zendesk, stripe, slack]
      write: [zendesk, stripe, slack]
    budget:
      api_calls: 50
      spend_usd: 500

  - role: senior-agent
    personality: >
      Thorough investigator with deep product knowledge.
      Digs into billing discrepancies and customer history.
    permissions:
      read: [zendesk, stripe, slack]
      write: [zendesk, stripe, slack]
    budget:
      api_calls: 100
      spend_usd: 500

  - role: triage-agent
    personality: >
      Fast categorizer who prioritizes by urgency and routes
      tickets to the right team member.
    permissions:
      read: [zendesk, slack]
      write: [zendesk, slack]
    budget:
      api_calls: 80
      spend_usd: 300
```

### Running It

```bash
# Pair with a world blueprint
uv run volnix serve customer_support \
  --internal agents_support_team.yaml \
  --port 8080

# Or with an existing compiled world
uv run volnix serve --world world_83a6d1e351f5 \
  --internal agents_support_team.yaml \
  --port 8080
```

The `--internal` flag tells Volnix to load the agent team, exclude NPC actors from the Agency Engine (they're driven by the Animator instead), and schedule the lead's activation lifecycle.

---

## The Lead Agent

The agent with `lead: true` is the team coordinator. It does NOT investigate deeply — it orchestrates.

### 4-Phase Lifecycle

| Phase | When | What the Lead Does |
|-------|------|-------------------|
| **1. Delegate** | First activation | Posts delegation message assigning tasks to each team member by role. Brief overview only (1-2 reads). Then waits. |
| **2. Monitor** | Team messages arrive | Reviews findings, validates accuracy, directs agents to dig deeper if incomplete, assigns new work if new events arrived. |
| **3. Buffer** | Approaching event limit | Instructs all agents to stop new investigations, finalize current work, and share final findings immediately. |
| **4. Synthesize** | Scheduled deadline | Generates the final deliverable from the full team conversation. This is a separate LLM call — not part of the tool-calling loop. |

### Phase Detection

Phases are determined automatically by `activation_reason`:

| `activation_reason` | `activation_messages` | Phase |
|---------------------|----------------------|-------|
| `continue_work` | Empty (first time) | Phase 1: Delegate |
| `continue_work` / `subscription_match` | Has prior messages | Phase 2: Monitor |
| `request_findings` | Any | Phase 3: Buffer |
| `produce_deliverable` | N/A (separate call) | Phase 4: Synthesize |

### Simulation Progress Awareness

The lead agent sees a **Simulation State** section in its prompt:

```
## Simulation State
29/50 events processed (58%)
```

This helps the lead make informed decisions about when to push for findings vs. allow more investigation.

---

## Sub-Agent Behavior

Sub-agents (non-lead) follow a standard cycle:

1. **INVESTIGATE** — Read relevant data using available tools
2. **SHARE** — Post findings in the team channel so the lead can see
3. **ACT** — Update records, process requests, resolve issues
4. **RESPOND** — Reply to messages from the lead marked `[TO YOU]`

Sub-agents use **multi-turn tool loops** — each activation maintains a conversation across multiple tool calls (up to `max_tool_calls_per_activation`, default 20). The conversation persists across re-activations so agents don't lose context.

---

## Collaboration Flow

```
1. Kickstart event posted to team channel
   |
2. Lead activates (Phase 1) → posts delegation message
   |
3. Sub-agents activate (triggered by delegation message)
   |-- Senior-agent: reads tickets, investigates billing
   |-- Triage-agent: categorizes tickets, assigns priority
   |
4. Sub-agents share findings in team channel
   |
5. Lead activates (Phase 2) → reviews findings, directs next steps
   |
6. [If dynamic mode] Animator generates NPC events (new tickets, follow-ups)
   |-- Sub-agents react to new events
   |
7. Lead activates (Phase 3) → requests final findings from all
   |
8. Lead generates deliverable (Phase 4)
```

### Communication

All agents communicate through a shared **team channel** (auto-created, e.g. `C06_GENERAL`). Messages use the `intended_for` field to address specific teammates:

```json
{
  "action_type": "chat.postMessage",
  "target_service": "slack",
  "payload": { "text": "Senior-agent: please investigate ticket TKT-003 billing discrepancy" },
  "intended_for": ["senior-agent"]
}
```

Messages marked `[TO YOU]` in an agent's prompt indicate they've been specifically addressed.

---

## Deliverables

Each team mission produces a structured deliverable. The type is set in the agent YAML:

| Type | Output | Use Case |
|------|--------|----------|
| `synthesis` | Comprehensive analysis report | Support evaluation, research summary |
| `prediction` | Directional forecast with confidence | Market analysis, risk assessment |
| `decision` | Ranked recommendation with rationale | Feature prioritization, vendor selection |
| `brainstorm` | Collection of distinct ideas | Campaign planning, ideation |
| `assessment` | Scored audit with findings | Security posture, compliance check |

The deliverable is generated at a scheduled deadline (`max_ticks - 1`). The lead's `goal_context` and the full team conversation are passed to a dedicated LLM call that produces structured JSON output.

### Viewing Deliverables

```bash
# After a run completes
uv run volnix show <run_id>

# Or via the dashboard at http://localhost:3000
```

The deliverable JSON is saved alongside the run artifacts in `~/.volnix/data/runs/<run_id>/`.

---

## Available Agent Team Blueprints

| Profile | Team | Roles | Deliverable | Pair With |
|---------|------|-------|-------------|-----------|
| `agents_support_team` | 3 | Supervisor, Senior-agent, Triage-agent | Synthesis | `customer_support`, `demo_support_escalation` |
| `agents_dynamic_support` | 3 | Supervisor, Senior-agent, Triage-agent | Synthesis | `dynamic_support_center` |
| `agents_market_analysts` | 3 | Macro-economist, Technical-analyst, Risk-analyst | Prediction | `market_prediction_analysis` |
| `agents_climate_researchers` | 4 | Lead-researcher, Physicist, Oceanographer, Statistician | Synthesis | `climate_research_station` |
| `agents_campaign_creatives` | 3 | Creative-director, Copywriter, Social-media-specialist | Brainstorm | `campaign_brainstorm` |
| `agents_feature_team` | 3 | Product-lead, Engineer, Designer | Decision | `feature_prioritization` |
| `agents_security_team` | 3 | Security-lead, Network-engineer, Compliance-officer | Assessment | `security_posture_assessment` |

All blueprints are in `volnix/blueprints/official/`.

---

## Configuration

Key settings in `volnix.toml` that affect internal agents:

```toml
[agency]
max_tool_calls_per_activation = 20    # Max tool calls per agent activation
tool_choice_mode = "auto"             # auto | required | none

[simulation_runner]
max_total_events = 50                 # Event budget (safety limit)
max_ticks = 200                       # Hard tick limit
animator_tick_interval = 5            # Ticks between animator fires
```

---

## Next Steps

- [Creating Worlds](creating-worlds.md) — Define your own world YAML
- [Behavior Modes](behavior-modes.md) — Static vs reactive vs dynamic
- [Blueprints Reference](blueprints-reference.md) — Full catalog of blueprints
- [Agent Integration](agent-integration.md) — Connect external agents instead
