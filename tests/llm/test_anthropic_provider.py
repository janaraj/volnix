"""Tests for volnix.llm.providers.anthropic -- Anthropic Claude provider."""

import os

import pytest

from volnix.llm.providers.anthropic import AnthropicProvider
from volnix.llm.types import LLMRequest

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
skipif_no_anthropic = pytest.mark.skipif(not ANTHROPIC_KEY, reason="ANTHROPIC_API_KEY not set")

# Toggle: VOLNIX_RUN_REAL_API_TESTS=1 to enable expensive real API tests
RUN_REAL = os.environ.get("VOLNIX_RUN_REAL_API_TESTS", "").lower() in ("1", "true", "yes")
skipif_no_real = pytest.mark.skipif(not RUN_REAL, reason="VOLNIX_RUN_REAL_API_TESTS not enabled")


def test_anthropic_provider_init():
    """AnthropicProvider initialises with api_key and default_model."""
    provider = AnthropicProvider(api_key="test-key", default_model="claude-haiku-4-5")
    assert provider._default_model == "claude-haiku-4-5"
    assert provider.provider_name == "anthropic"


@skipif_no_anthropic
@pytest.mark.asyncio
async def test_anthropic_provider_generate_real():
    """Integration: send a real request to Anthropic (skipped without key)."""
    provider = AnthropicProvider(api_key=ANTHROPIC_KEY)
    req = LLMRequest(user_content="Say 'pong'", max_tokens=16)
    resp = await provider.generate(req)
    assert resp.content
    assert resp.usage.total_tokens > 0
    assert resp.provider == "anthropic"


@pytest.mark.asyncio
async def test_anthropic_provider_validate_no_key():
    """Validate connection returns False with an invalid key."""
    provider = AnthropicProvider(api_key="invalid-key-xxx")
    result = await provider.validate_connection()
    assert result is False


@pytest.mark.asyncio
async def test_anthropic_provider_error_handling():
    """Provider returns an error response on exception."""
    provider = AnthropicProvider(api_key="bad-key")
    req = LLMRequest(user_content="test")
    resp = await provider.generate(req)
    assert resp.error is not None
    assert resp.content == ""
    assert resp.provider == "anthropic"
    assert resp.latency_ms >= 0


def test_anthropic_provider_cost_estimation():
    """Cost estimation uses the correct per-model rates."""
    provider = AnthropicProvider(api_key="test-key")
    # claude-sonnet-4-6: input=$3/1M, output=$15/1M
    cost = provider._estimate_cost("claude-sonnet-4-6", 1000, 500)
    expected = (1000 * 3.0 + 500 * 15.0) / 1_000_000
    assert abs(cost - expected) < 1e-10

    # Unknown model falls back to sonnet pricing
    cost_unknown = provider._estimate_cost("unknown-model", 1000, 500)
    assert abs(cost_unknown - expected) < 1e-10


@skipif_no_anthropic
@skipif_no_real
@pytest.mark.asyncio
async def test_anthropic_real_generate():
    """Real Anthropic API call -- enable with VOLNIX_RUN_REAL_API_TESTS=1."""
    provider = AnthropicProvider(api_key=ANTHROPIC_KEY)
    resp = await provider.generate(
        LLMRequest(
            system_prompt="Reply with exactly the word 'volnix'",
            user_content="What word?",
            max_tokens=50,
        )
    )
    assert resp.error is None
    assert "volnix" in resp.content.lower()
    assert resp.usage.prompt_tokens > 0
    assert resp.usage.completion_tokens > 0
