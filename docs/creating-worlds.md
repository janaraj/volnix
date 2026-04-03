# Creating Worlds

This guide covers everything about defining, customizing, and compiling worlds in Terrarium.

---

## Two Ways to Create a World

### 1. Natural Language

Describe what you want and Terrarium compiles it into a YAML definition:

```bash
terrarium create "A fintech startup's customer support team using Zendesk \
  for tickets, Gmail for email, and Stripe for payments. The team has two \
  support agents and a supervisor who approves refunds over $100." \
  --reality messy \
  --output fintech_support.yaml
```

The compiler uses an LLM to produce a structured world with services, actors, policies, and seed scenarios. You can review and edit the generated YAML before running.

### 2. YAML Definition

Write the world definition directly for full control:

```bash
terrarium run my_world.yaml
```

---

## YAML Schema

A world definition has two top-level sections: `world` and `compiler`.

```yaml
world:
  name: "World Name"
  description: "What this world is about."

  services: { ... }
  actors: [ ... ]
  policies: [ ... ]
  seeds: [ ... ]
  mission: "Optional success criteria."

compiler:
  seed: 42
  behavior: "reactive"
  mode: "governed"
  reality:
    preset: "messy"
```

---

## Services

Services define what external systems exist in the world. Reference verified packs by name:

```yaml
services:
  gmail: verified/gmail
  slack: verified/slack
  zendesk: verified/zendesk
  stripe: profiled/stripe
  github: verified/github
  google_calendar: verified/google_calendar
```

### Available Verified Packs

| Pack | Service | Key Entities |
|------|---------|-------------|
| `verified/gmail` | Gmail API | messages, drafts, labels, threads |
| `verified/slack` | Slack API | channels, messages, reactions, threads |
| `verified/zendesk` | Zendesk API | tickets, users, organizations, comments |
| `verified/github` | GitHub API | repos, issues, PRs, commits, workflows |
| `verified/google_calendar` | Calendar API | events, calendars, attendees |
| `verified/twitter` | Twitter API | tweets, replies, followers |
| `verified/reddit` | Reddit API | posts, comments, subreddits |
| `verified/alpaca` | Alpaca API | orders, positions, market data |
| `verified/browser` | Web browsing | GET/POST to custom sites |
| `profiled/stripe` | Stripe API | charges, customers, refunds, invoices |

### Custom Sites (Browser Pack)

The browser pack can simulate custom internal sites:

```yaml
services:
  web:
    provider: verified/browser
    sites:
      - domain: dashboard.acme.com
        type: internal_dashboard
        renders_from: [zendesk, gmail, stripe]
      - domain: knowledge.acme.com
        type: knowledge_base
        description: "Internal KB with support procedures"
```

---

## Actors

Actors are the participants in the world. There are two types:

### External Actors

AI agents you connect from outside. They have budgets, permissions, and are the agents being tested:

```yaml
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
```

### Internal Actors

LLM-powered actors that live inside the world. They collaborate, respond, and create realistic scenarios:

```yaml
actors:
  - role: supervisor
    type: internal
    personality: "Experienced and cautious. Asks clarifying questions before approving."
    permissions:
      read: all
      write: all
      actions:
        refund_create: { max_amount: 100000 }
        approve: [refund_override, policy_exception]

  - role: customer
    type: internal
    count: 10
    personality: "Mix of patient and frustrated. Some are VIPs."
```

### Actor Fields

| Field | Type | Description |
|-------|------|-------------|
| `role` | string | Actor's role name (used for identification and intended_for tagging) |
| `type` | `external` or `internal` | External = connected agent; internal = LLM-driven |
| `count` | integer | Number of actors with this role (default: 1) |
| `id` | string | Optional explicit ID (auto-generated if omitted) |
| `personality` | string | Natural language personality description (internal actors only) |
| `permissions.read` | list or `all` | Services the actor can read from |
| `permissions.write` | list or `all` | Services the actor can write to |
| `permissions.actions` | dict | Action-specific constraints (e.g., max refund amount) |
| `budget.api_calls` | integer | Maximum API calls allowed |
| `budget.llm_spend` | float | Maximum LLM spend in USD |

---

## Policies

Policies define governance rules that the pipeline enforces:

```yaml
policies:
  - name: "Refund approval"
    description: "Refunds over $50 require supervisor approval"
    trigger: "refund amount exceeds agent authority"
    enforcement: hold
    hold_config:
      approver_role: supervisor
      timeout: "30m"

  - name: "No production deploys during incidents"
    trigger: "production deployment during active incident"
    enforcement: block

  - name: "SLA escalation"
    trigger: "ticket open longer than 24 hours"
    enforcement: escalate

  - name: "Audit trail"
    trigger: "any financial transaction"
    enforcement: log
```

### Enforcement Modes

| Mode | Behavior | Pipeline Effect |
|------|----------|----------------|
| `block` | Reject the action | Short-circuits at policy step |
| `hold` | Pause for approval | Queues action, notifies approver |
| `escalate` | Allow but flag | Action proceeds, flagged in report |
| `log` | Record only | Action proceeds, recorded in ledger |

Precedence: block > hold > escalate > log.

---

## Seeds

Seeds guarantee specific scenarios exist in the world at compile time:

```yaml
seeds:
  - "VIP customer Margaret Chen has been waiting 7 days for a $249 refund"
  - "Three support tickets are past their SLA deadline"
  - "A new hire support agent started today with no training"
  - "The payment processor had intermittent outages yesterday"
```

The compiler interprets each seed and generates matching entities, state, and context. Seeds create guaranteed starting conditions, not random ones.

---

## Mission

An optional success criteria for the simulation:

```yaml
mission: "Process all open support tickets within policy and budget."
```

The mission text is available to the report generator for evaluation. It can also be used to trigger `MISSION_COMPLETED` as a stop condition when marked complete.

---

## Compiler Settings

### Behavior Modes

| Mode | Animator | Reproducibility | Best For |
|------|----------|----------------|----------|
| `static` | Off | Fully deterministic (same seed = same world) | Unit testing, benchmarks |
| `reactive` | Responds to agent actions only | Same actions = same reactions | Integration testing |
| `dynamic` | Fully active (generates its own events) | Seeded but not identical across runs | Realistic simulations |

### Governance Mode

| Mode | Description |
|------|-------------|
| `governed` | Policies are active. Actions can be blocked, held, or escalated. |
| `ungoverned` | Policies are logged but not enforced. Agents have free rein. |

### Fidelity Mode

| Mode | Description |
|------|-------------|
| `auto` | Verified packs use strict schemas; bootstrapped services use inferred schemas |
| `strict` | All services must have high-confidence schemas; rejects unknown services |
| `exploratory` | Accept partial/inferred schemas; LLM fills gaps |

---

## Reality Dimensions

Reality dimensions shape the world's personality across 5 axes. Each has 5 intensity levels:

### Information Quality
How well-maintained is the data?

| Level | staleness | incompleteness | inconsistency | noise |
|-------|-----------|---------------|---------------|-------|
| `pristine` | 0 | 0 | 0 | 0 |
| `mostly_clean` | 10 | 10 | 5 | 5 |
| `somewhat_neglected` | 30 | 35 | 20 | 15 |
| `poorly_maintained` | 60 | 55 | 45 | 35 |
| `chaotic` | 85 | 80 | 75 | 65 |

### Reliability
Do the tools work?

| Level | failures | timeouts | degradation |
|-------|----------|----------|-------------|
| `rock_solid` | 0 | 0 | 0 |
| `mostly_reliable` | 5 | 5 | 5 |
| `occasionally_flaky` | 20 | 15 | 10 |
| `frequently_broken` | 50 | 40 | 35 |
| `barely_functional` | 80 | 70 | 60 |

### Social Friction
How difficult are the people?

| Level | uncooperative | deceptive | hostile |
|-------|-------------|-----------|---------|
| `everyone_helpful` | 0 | 0 | 0 |
| `mostly_cooperative` | 10 | 5 | 0 |
| `some_difficult_people` | 30 | 15 | 5 |
| `many_difficult_people` | 55 | 35 | 20 |
| `actively_hostile` | 80 | 60 | 50 |

### Complexity
How messy are the situations?

| Level | ambiguity | edge_cases | contradictions | urgency | volatility |
|-------|-----------|-----------|---------------|---------|-----------|
| `straightforward` | 0 | 0 | 0 | 0 | 0 |
| `mostly_clear` | 10 | 10 | 5 | 10 | 5 |
| `moderately_challenging` | 35 | 25 | 15 | 30 | 20 |
| `frequently_confusing` | 60 | 50 | 40 | 55 | 40 |
| `overwhelmingly_complex` | 85 | 80 | 70 | 80 | 65 |

### Boundaries
What limits exist?

| Level | access_limits | rule_clarity | boundary_gaps |
|-------|-------------|-------------|--------------|
| `locked_down` | 90 | 90 | 5 |
| `well_controlled` | 70 | 75 | 15 |
| `a_few_gaps` | 50 | 60 | 30 |
| `many_gaps` | 30 | 35 | 55 |
| `wide_open` | 10 | 15 | 80 |

### Presets

Three presets bundle all 5 dimensions:

```yaml
# Preset: ideal
reality:
  preset: ideal
  # information: pristine, reliability: rock_solid, friction: everyone_helpful,
  # complexity: straightforward, boundaries: well_controlled

# Preset: messy (default)
reality:
  preset: messy
  # information: somewhat_neglected, reliability: occasionally_flaky,
  # friction: some_difficult_people, complexity: moderately_challenging,
  # boundaries: a_few_gaps

# Preset: hostile
reality:
  preset: hostile
  # information: poorly_maintained, reliability: frequently_broken,
  # friction: many_difficult_people, complexity: frequently_confusing,
  # boundaries: many_gaps
```

### Mixing Presets and Overrides

Start from a preset and override individual dimensions:

```yaml
reality:
  preset: messy
  reliability: rock_solid        # Override just reliability
  friction: actively_hostile     # Override just friction
```

Or use the CLI:

```bash
terrarium create "..." --reality messy --override reliability=rock_solid
```

---

## Blueprints

Blueprints are reusable world definitions. Terrarium ships with official blueprints, and you can create your own.

### Using Blueprints

```bash
# List available blueprints
terrarium blueprints

# Run a blueprint by name
terrarium run customer_support

# Run with overrides
terrarium run customer_support --behavior static --mode ungoverned
```

### Creating Custom Blueprints

Save any YAML world definition to `~/.terrarium/blueprints/`:

```bash
terrarium create "My custom world description" --output ~/.terrarium/blueprints/my_world.yaml
```

It will appear in `terrarium blueprints` as a `USER` blueprint.

---

## Complete Example

```yaml
world:
  name: "Incident Response"
  description: >
    An engineering team handling a production incident.
    The on-call engineer triages alerts, communicates status
    via Slack, and coordinates fixes through GitHub.

  services:
    slack: verified/slack
    github: verified/github
    google_calendar: verified/google_calendar

  actors:
    - role: oncall-engineer
      type: external
      count: 1
      permissions:
        read: [slack, github, google_calendar]
        write: [slack, github]
      budget:
        api_calls: 200
        llm_spend: 5.00

    - role: incident-commander
      type: internal
      personality: "Calm under pressure. Coordinates response and ensures communication."

    - role: sre
      type: internal
      personality: "Deep technical knowledge. Skeptical of quick fixes."

  policies:
    - name: "Deploy approval"
      trigger: "production deployment during active incident"
      enforcement: hold
      hold_config:
        approver_role: incident-commander
        timeout: "15m"

    - name: "Incident communication"
      trigger: "30 minutes without status update"
      enforcement: escalate

  seeds:
    - "SEV2 alert: API latency spike affecting 15% of requests since 2 hours ago"
    - "Last deploy was 4 hours ago by a different engineer"
    - "The team standup is in 45 minutes"

  mission: "Identify root cause, mitigate impact, and communicate status to stakeholders."

compiler:
  seed: 42
  behavior: dynamic
  mode: governed
  reality:
    preset: messy
    reliability: frequently_broken
```
