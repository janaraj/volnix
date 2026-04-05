#!/usr/bin/env bash
set -euo pipefail

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  VOLNIX DEMO: E-commerce Order Management (External)     ║"
echo "║                                                             ║"
echo "║  2 agents • reactive world • governed • messy reality       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "Agents:"
echo "  support-bot  — read all, write zendesk+slack only"
echo "  admin        — full access, policy-limited"
echo ""
echo "Governance:"
echo "  • Permissions: support-bot can't write stripe"
echo "  • Policy: refunds over \$250 blocked"
echo "  • Budget: api_calls + spend_usd per agent"
echo ""

cd "$(dirname "$0")/../../.."

echo "Step 1: Starting Volnix server (compiles if needed)..."
uv run volnix serve demo_ecommerce \
  --agents examples/launch-demo/external/agents.yaml \
  --port 8080 &
SERVER_PID=$!

echo "Waiting for server..."
for i in $(seq 1 30); do
  if curl -s localhost:8080/api/v1/tools > /dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo ""
echo "Step 2: Running agents (OpenAI SDK, zero Volnix imports)..."
echo ""
uv run python examples/launch-demo/external/run.py

echo ""
echo "Dashboard: http://localhost:3000"
echo "Press Ctrl+C to stop server."
wait $SERVER_PID
