# Internal Demo: Customer Support Escalation

A 3-agent support team handles a messy queue autonomously. The world is dynamic — events happen between agent turns.

## Quick start

```bash
# Start Volnix with internal agents (compiles world automatically)
cd /path/to/volnix
bash examples/launch-demo/internal/run.sh

# Start dashboard in another terminal
cd volnix-dashboard && npm run dev
```

## What happens

Three agents with different roles and permissions work together:

| Agent | Role | Stripe Access | Budget |
|-------|------|--------------|--------|
| **supervisor** (lead) | Approves refunds, produces summary | read + write | 50 calls, $500 |
| **senior-agent** | Resolves issues, documents steps | read only | 40 calls, $100 |
| **triage-agent** | Categorizes tickets, routes to team | none | 30 calls |

## Governance in action

- **Permission blocks**: triage-agent tries to read charges → blocked (no stripe access)
- **Policy blocks**: any agent tries refund > $100 → blocked by policy
- **Budget depletion**: agents run out of api_calls as they work
- **Dynamic events**: new tickets and customer responses appear between turns

## Dashboard walkthrough

1. **Live Console** — Watch events stream in real-time as agents work
2. **Events** — See the causal trace: who did what, in what order, what was blocked
3. **Entities** — Inspect tickets, charges, refunds, and Slack messages
4. **Deliverable** — The shift summary produced by the supervisor
5. **Scorecard** — Per-agent governance score (compliance rate)
6. **Conditions** — Reality dimensions: messy preset means stale data, incomplete records

## Files

- World: `volnix/blueprints/official/demo_support_escalation.yaml`
- Agents: `volnix/blueprints/official/agents_support_team.yaml`
