#!/usr/bin/env bash
set -euo pipefail

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  TERRARIUM DEMO: Customer Support Escalation (Internal)     ║"
echo "║                                                             ║"
echo "║  3 agents • dynamic world • governed • messy reality        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Agents:"
echo "  supervisor    — full access, leads team, approves refunds"
echo "  senior-agent  — resolves issues, can read but not write stripe"
echo "  triage-agent  — categorizes tickets, no payment access"
echo ""
echo "Governance:"
echo "  • Permissions: tiered access per agent"
echo "  • Policy: refunds over \$100 blocked"
echo "  • Budget: api_calls + spend_usd per agent"
echo "  • Behavior: dynamic (world generates events between turns)"
echo ""
echo "Dashboard: http://localhost:3000"
echo ""

cd "$(dirname "$0")/../../.."
uv run terrarium serve demo_support_escalation \
  --internal agents_support_team \
  --port 8080
