# Blueprints Reference

Volnix ships with pre-built blueprints — world definitions and agent team profiles you can run immediately. This page catalogs all official blueprints and shows how to pair them.

---

## Listing Blueprints

```bash
uv run volnix blueprints
```

All blueprints are in `volnix/blueprints/official/`.

---

## World Definitions

World blueprints define the environment: services, entities, actors (NPCs), policies, and seeds.

| Blueprint | Domain | Behavior | Services | Actors | Policies |
|-----------|--------|----------|----------|--------|----------|
| **customer_support** | Support | Reactive | Gmail, Slack, Zendesk, Stripe | 2 external agents + 1 supervisor + 10 customers | Hold (refunds >$100), Escalate (4h SLA) |
| **demo_support_escalation** | Support | Dynamic | Stripe, Zendesk, Slack | 3 internal agents + customers | Block (refunds >$100), Log (payments) |
| **dynamic_support_center** | Support | Dynamic | Stripe, Zendesk, Slack | 3 frustrated + 2 VIP customers (NPCs) | Block (refunds >$100), Log (payments) |
| **incident_response** | DevOps | Dynamic | Slack, GitHub, Calendar | 1 oncall + commander + SRE lead | Hold (deploy), Escalate (SEV1) |
| **market_prediction_analysis** | Finance | Dynamic | Slack, Twitter, Reddit | None | None |
| **campaign_brainstorm** | Marketing | Dynamic | Slack | None | None |
| **climate_research_station** | Research | Dynamic | Slack, Gmail | None | Hold (evidence), Hold (stats) |
| **feature_prioritization** | Product | Dynamic | Slack | None | Hold (evidence), Log (decision) |
| **security_posture_assessment** | Security | Dynamic | Slack, Zendesk | None | Hold (critical), Escalate (compliance) |
| **support_ticket_triage** | Support | Dynamic | Gmail, Zendesk | 2 agents + 1 lead + 5 customers | Log (triage), Hold (closure) |
| **open_sandbox** | Testing | Static | All (Gmail, Slack, Zendesk, Stripe, GitHub, Calendar) | 1 external agent | None (ungoverned) |
| **demo_ecommerce** | E-commerce | Reactive | Stripe, Zendesk, Slack | External | Block (refunds >$250) |
| **governance_test** | Testing | Reactive | Stripe, Zendesk, Slack | External | Block (refunds >$500), Log (all) |

---

## Agent Team Profiles

Agent team profiles define autonomous internal agents. Pair them with a world definition using `--internal`.

| Profile | Team Size | Roles | Lead | Deliverable | Best Paired With |
|---------|-----------|-------|------|-------------|-----------------|
| **agents_support_team** | 3 | Supervisor, Senior-agent, Triage-agent | Supervisor | Synthesis | `customer_support`, `demo_support_escalation` |
| **agents_dynamic_support** | 3 | Supervisor, Senior-agent, Triage-agent | Supervisor | Synthesis | `dynamic_support_center` |
| **agents_market_analysts** | 3 | Macro-economist, Technical-analyst, Risk-analyst | Macro-economist | Prediction | `market_prediction_analysis` |
| **agents_climate_researchers** | 4 | Lead-researcher, Physicist, Oceanographer, Statistician | Lead-researcher | Synthesis | `climate_research_station` |
| **agents_campaign_creatives** | 3 | Creative-director, Copywriter, Social-media-specialist | Creative-director | Brainstorm | `campaign_brainstorm` |
| **agents_feature_team** | 3 | Product-lead, Engineer, Designer | Product-lead | Decision | `feature_prioritization` |
| **agents_security_team** | 3 | Security-lead, Network-engineer, Compliance-officer | Security-lead | Assessment | `security_posture_assessment` |

---

## Recommended Pairings

### Support & Customer Service

```bash
# Static world, internal team — fastest, no NPC events
uv run volnix serve customer_support \
  --internal volnix/blueprints/official/agents_support_team.yaml \
  --behavior static --port 8080

# Dynamic world with live NPC customers
uv run volnix serve dynamic_support_center \
  --internal volnix/blueprints/official/agents_dynamic_support.yaml \
  --port 8080
```

### Market & Financial Analysis

```bash
uv run volnix serve market_prediction_analysis \
  --internal volnix/blueprints/official/agents_market_analysts.yaml \
  --port 8080
```

### Research & Science

```bash
uv run volnix serve climate_research_station \
  --internal volnix/blueprints/official/agents_climate_researchers.yaml \
  --port 8080
```

### Security Assessment

```bash
uv run volnix serve security_posture_assessment \
  --internal volnix/blueprints/official/agents_security_team.yaml \
  --port 8080
```

### External Agent Testing

```bash
# Open sandbox — ungoverned, all services, no policies
uv run volnix serve open_sandbox --port 8080

# Governance test — strict policies, good for testing agent compliance
uv run volnix serve governance_test --port 8080
```

---

## Creating Your Own Blueprint

### World Definition

Create a YAML file with the `world:` section:

```yaml
world:
  name: "My Custom World"
  description: "A fintech startup handling payment disputes."
  behavior: dynamic
  mode: governed
  reality:
    preset: messy

  services:
    stripe: verified/stripe
    slack: verified/slack
    zendesk: verified/zendesk

  actors:
    - role: angry-merchant
      type: internal
      count: 3
      personality: "Merchants disputing chargebacks aggressively."

  policies:
    - name: "Chargeback review"
      trigger: "chargeback amount exceeds $500"
      enforcement: hold

  seeds:
    - "Merchant filed 3 chargebacks in the last week"
    - "One dispute involves a $2,000 transaction"
```

### Agent Team Profile

Create a separate YAML for the internal team:

```yaml
mission: "Investigate and resolve merchant payment disputes fairly and efficiently."
deliverable: synthesis

agents:
  - role: dispute-lead
    lead: true
    personality: "Fair-minded team lead who balances merchant satisfaction with fraud prevention."
    permissions:
      read: [stripe, slack, zendesk]
      write: [stripe, slack, zendesk]

  - role: fraud-analyst
    personality: "Detail-oriented analyst who checks transaction patterns for fraud signals."
    permissions:
      read: [stripe, zendesk]
      write: [slack]

  - role: merchant-liaison
    personality: "Empathetic communicator who understands merchant frustrations."
    permissions:
      read: [stripe, slack, zendesk]
      write: [slack, zendesk]
```

### Run It

```bash
uv run volnix serve my_world.yaml \
  --internal my_agents.yaml \
  --port 8080
```

---

## Next Steps

- [Creating Worlds](creating-worlds.md) — Full YAML schema reference
- [Internal Agents](internal-agents.md) — How agent teams collaborate
- [Behavior Modes](behavior-modes.md) — Static vs reactive vs dynamic
