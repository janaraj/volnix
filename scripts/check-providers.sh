#!/usr/bin/env bash
# Terrarium Provider Check
# Checks which LLM providers are available on this system.
# Called by: terrarium check (CLI command, Phase H1)

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "══════════════════════════════════════════════════════════"
echo "  Terrarium — Provider Availability Check"
echo "══════════════════════════════════════════════════════════"
echo ""

# ── API Providers ──────────────────────────────────────────────

echo "── API Providers ──"
echo ""

if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    echo -e "  ${GREEN}✓${NC} Anthropic API    — key set (${#ANTHROPIC_API_KEY} chars)"
else
    echo -e "  ${RED}✗${NC} Anthropic API    — ANTHROPIC_API_KEY not set"
fi

if [ -n "${OPENAI_API_KEY:-}" ]; then
    echo -e "  ${GREEN}✓${NC} OpenAI API       — key set (${#OPENAI_API_KEY} chars)"
else
    echo -e "  ${RED}✗${NC} OpenAI API       — OPENAI_API_KEY not set"
fi

if [ -n "${GOOGLE_API_KEY:-}" ]; then
    echo -e "  ${GREEN}✓${NC} Google API       — key set"
else
    echo -e "  ${RED}✗${NC} Google API       — GOOGLE_API_KEY not set"
fi

echo ""

# ── CLI Tools ──────────────────────────────────────────────────

echo "── CLI Tools (local) ──"
echo ""

if command -v claude &>/dev/null; then
    CLAUDE_PATH=$(which claude)
    echo -e "  ${GREEN}✓${NC} Claude Code CLI  — $CLAUDE_PATH"
else
    echo -e "  ${RED}✗${NC} Claude Code CLI  — not installed"
fi

if command -v codex &>/dev/null; then
    CODEX_PATH=$(which codex)
    echo -e "  ${GREEN}✓${NC} Codex CLI        — $CODEX_PATH"
else
    echo -e "  ${RED}✗${NC} Codex CLI        — not installed"
fi

if command -v gemini &>/dev/null; then
    GEMINI_PATH=$(which gemini)
    echo -e "  ${GREEN}✓${NC} Gemini CLI       — $GEMINI_PATH"
else
    echo -e "  ${YELLOW}~${NC} Gemini CLI       — not installed (optional)"
fi

echo ""

# ── ACP Servers ────────────────────────────────────────────────

echo "── ACP Servers ──"
echo ""

if command -v npx &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} npx available    — $(which npx)"
else
    echo -e "  ${RED}✗${NC} npx not found    — install Node.js to use ACP servers"
fi

# Check if ACP servers are running
for port in 3000 3001 3002; do
    if curl -s --max-time 2 "http://localhost:$port/health" &>/dev/null || \
       curl -s --max-time 2 "http://localhost:$port/ping" &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} ACP server       — running on port $port"
    fi
done

if [ -n "${ACP_CLAUDE_URL:-}" ]; then
    echo -e "  ${GREEN}✓${NC} Claude ACP URL   — $ACP_CLAUDE_URL"
fi
if [ -n "${ACP_CODEX_URL:-}" ]; then
    echo -e "  ${GREEN}✓${NC} Codex ACP URL    — $ACP_CODEX_URL"
fi

echo ""

# ── Python SDKs ────────────────────────────────────────────────

echo "── Python SDKs ──"
echo ""

PYTHON="${TERRARIUM_PYTHON:-.venv/bin/python}"

for pkg in anthropic openai "google.genai" acp_sdk acp; do
    if $PYTHON -c "import $pkg" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $pkg"
    else
        echo -e "  ${RED}✗${NC} $pkg — not installed"
    fi
done

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  To set API keys: cp .env.example .env && edit .env"
echo "  To start ACP:    bash scripts/start-acp.sh"
echo "  To run tests:    bash scripts/test-providers.sh"
echo "══════════════════════════════════════════════════════════"
