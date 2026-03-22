#!/usr/bin/env bash
# Terrarium ACP Server Launcher
# Starts ACP server adapters for locally-installed CLI tools.
# Called by: terrarium setup (CLI command, Phase H1)
#
# Prerequisites:
#   - Node.js + npx installed
#   - Claude Code CLI: npm install -g @anthropic/claude-code
#   - Codex CLI: npm install -g @openai/codex
#
# Usage:
#   bash scripts/start-acp.sh              # start all available
#   bash scripts/start-acp.sh claude       # start claude only
#   bash scripts/start-acp.sh codex        # start codex only

set -euo pipefail

SELECTED="${1:-all}"
PIDS=()

cleanup() {
    echo ""
    echo "Shutting down ACP servers..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    echo "Done."
}
trap cleanup EXIT INT TERM

start_claude_acp() {
    if command -v claude &>/dev/null; then
        echo "Starting Claude Agent ACP server on port 3000..."
        npx @zed-industries/claude-agent-acp --port 3000 &
        PIDS+=($!)
        echo "  PID: ${PIDS[-1]}"
        export ACP_CLAUDE_URL="http://localhost:3000"
    else
        echo "Claude CLI not installed — skipping Claude ACP server"
    fi
}

start_codex_acp() {
    if command -v codex &>/dev/null; then
        echo "Starting Codex ACP server on port 3001..."
        npx @zed-industries/codex-acp --port 3001 &
        PIDS+=($!)
        echo "  PID: ${PIDS[-1]}"
        export ACP_CODEX_URL="http://localhost:3001"
    else
        echo "Codex CLI not installed — skipping Codex ACP server"
    fi
}

echo "══════════════════════════════════════════════════════════"
echo "  Terrarium — ACP Server Launcher"
echo "══════════════════════════════════════════════════════════"
echo ""

case "$SELECTED" in
    claude)
        start_claude_acp
        ;;
    codex)
        start_codex_acp
        ;;
    all)
        start_claude_acp
        start_codex_acp
        ;;
    *)
        echo "Usage: $0 [claude|codex|all]"
        exit 1
        ;;
esac

echo ""
echo "ACP servers running. Press Ctrl+C to stop."
echo ""

# Wait for all background processes
wait
