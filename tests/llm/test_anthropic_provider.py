"""Tests for volnix.llm.providers.anthropic -- Anthropic Claude provider."""

import os

import pytest

from volnix.llm.providers.anthropic import AnthropicProvider, _strip_framework_keys
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


class TestStripFrameworkKeys:
    """Tests for _strip_framework_keys.

    Defensively removes framework-only keys (e.g., provider_metadata used for
    Gemini thought_signature round-trip) from tool_call entries before the
    messages reach the Anthropic SDK.
    """

    def test_strips_provider_metadata_from_tool_calls(self):
        """provider_metadata key in tool_calls entry is stripped."""
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "f", "arguments": "{}"},
                        "provider_metadata": {"thought_signature": "abc=="},
                    }
                ],
            },
        ]
        result = _strip_framework_keys(messages)
        sanitized_tc = result[0]["tool_calls"][0]
        assert "provider_metadata" not in sanitized_tc
        assert sanitized_tc["id"] == "c1"
        assert sanitized_tc["function"] == {"name": "f", "arguments": "{}"}

    def test_passthrough_when_no_tool_calls(self):
        """Messages without tool_calls are passed through unchanged."""
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        result = _strip_framework_keys(messages)
        assert result == messages

    def test_does_not_mutate_input(self):
        """Sanitizer does not mutate the original tool_call dicts."""
        original_tc = {
            "id": "c1",
            "type": "function",
            "function": {"name": "f", "arguments": "{}"},
            "provider_metadata": {"thought_signature": "abc=="},
        }
        messages = [{"role": "assistant", "tool_calls": [original_tc]}]
        _strip_framework_keys(messages)
        assert "provider_metadata" in original_tc


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
