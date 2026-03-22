#!/usr/bin/env bash
# Terrarium Provider Test Runner
# Tests all configured LLM providers with real API calls.
# Called by: terrarium check --test (CLI command, Phase H1)
#
# Usage:
#   bash scripts/test-providers.sh              # test all with available keys
#   bash scripts/test-providers.sh --mock-only  # only mock tests (no API keys needed)
#
# Prerequisites:
#   - API keys set in environment (see .env.example)
#   - ACP servers running (see scripts/start-acp.sh)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="${TERRARIUM_PYTHON:-$PROJECT_DIR/.venv/bin/python}"
PYTEST="$PYTHON -m pytest"

# Load .env if exists
if [ -f "$PROJECT_DIR/.env" ]; then
    echo "Loading .env..."
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

echo "══════════════════════════════════════════════════════════"
echo "  Terrarium — Provider Test Runner"
echo "══════════════════════════════════════════════════════════"
echo ""

if [ "${1:-}" = "--mock-only" ]; then
    echo "Running mock-only tests (no API keys needed)..."
    echo ""
    $PYTEST tests/llm/ -v --tb=short -k "not real and not _generate_real"
    exit $?
fi

# Enable real API tests
export TERRARIUM_RUN_REAL_API_TESTS=1

echo "── Mock + Unit Tests ──"
$PYTEST tests/llm/ -v --tb=short -k "not real" 2>&1 | tail -5
echo ""

echo "── Real API Tests ──"
echo ""

# Anthropic
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    echo "Testing Anthropic (real API)..."
    $PYTEST tests/llm/test_anthropic_provider.py -v --tb=short -k "real" 2>&1 | tail -3
else
    echo "  ⏭  Anthropic — ANTHROPIC_API_KEY not set, skipping"
fi
echo ""

# OpenAI
if [ -n "${OPENAI_API_KEY:-}" ]; then
    echo "Testing OpenAI (real API)..."
    $PYTEST tests/llm/test_openai_compat.py -v --tb=short -k "real" 2>&1 | tail -3
else
    echo "  ⏭  OpenAI — OPENAI_API_KEY not set, skipping"
fi
echo ""

# Google
if [ -n "${GOOGLE_API_KEY:-}" ]; then
    echo "Testing Google (real API)..."
    $PYTEST tests/llm/test_google_provider.py -v --tb=short -k "real" 2>&1 | tail -3
else
    echo "  ⏭  Google — GOOGLE_API_KEY not set, skipping"
fi
echo ""

# ACP
if [ -n "${ACP_SERVER_URL:-}" ]; then
    echo "Testing ACP (real server)..."
    $PYTEST tests/llm/test_acp_client.py -v --tb=short -k "real" 2>&1 | tail -3
else
    echo "  ⏭  ACP — ACP_SERVER_URL not set, skipping"
fi
echo ""

echo "══════════════════════════════════════════════════════════"
echo "  Done. Set missing keys in .env to test more providers."
echo "══════════════════════════════════════════════════════════"
