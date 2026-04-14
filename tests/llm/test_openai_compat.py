"""Tests for volnix.llm.providers.openai_compat -- OpenAI-compatible provider."""

import os

import pytest

from volnix.llm.providers.openai_compat import (
    OpenAICompatibleProvider,
    _repair_tool_call_pairing,
    _sanitize_messages_for_openai,
)
from volnix.llm.types import LLMRequest

OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
skipif_no_openai = pytest.mark.skipif(not OPENAI_KEY, reason="OPENAI_API_KEY not set")

# Toggle: VOLNIX_RUN_REAL_API_TESTS=1 to enable expensive real API tests
RUN_REAL = os.environ.get("VOLNIX_RUN_REAL_API_TESTS", "").lower() in ("1", "true", "yes")
skipif_no_real = pytest.mark.skipif(not RUN_REAL, reason="VOLNIX_RUN_REAL_API_TESTS not enabled")


def test_openai_compat_init():
    """OpenAICompatibleProvider initialises with key, base_url, model."""
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        default_model="gpt-5.4-mini",
    )
    assert provider._default_model == "gpt-5.4-mini"
    assert provider._base_url == "https://api.openai.com/v1"
    assert provider.provider_name == "openai_compatible"


def test_openai_compat_custom_base_url():
    """Provider accepts a custom base_url for Ollama / vLLM / etc."""
    provider = OpenAICompatibleProvider(
        api_key=None,
        base_url="http://localhost:11434/v1",
        default_model="llama3.2",
    )
    assert provider._base_url == "http://localhost:11434/v1"
    info = provider.get_info()
    assert info.base_url == "http://localhost:11434/v1"
    assert info.type == "openai_compatible"


def test_openai_compat_no_api_key_for_ollama():
    """Provider works without an API key (e.g. local Ollama)."""
    provider = OpenAICompatibleProvider(
        api_key=None,
        base_url="http://localhost:11434/v1",
    )
    # Should not raise -- "local-no-auth-needed" is used as placeholder
    assert provider is not None


@skipif_no_openai
@skipif_no_real
@pytest.mark.asyncio
async def test_openai_compat_generate_real():
    """Integration: send a real request to OpenAI (skipped without key + opt-in)."""
    provider = OpenAICompatibleProvider(
        api_key=OPENAI_KEY,
        base_url="https://api.openai.com/v1",
    )
    req = LLMRequest(user_content="Say 'pong'", max_tokens=16)
    resp = await provider.generate(req)
    assert resp.content
    assert resp.provider == "openai_compatible"


@pytest.mark.asyncio
async def test_openai_compat_error_handling():
    """Provider returns an error response on connection failure."""
    provider = OpenAICompatibleProvider(
        api_key="bad-key",
        base_url="http://127.0.0.1:1/v1",
    )
    req = LLMRequest(user_content="test")
    resp = await provider.generate(req)
    assert resp.error is not None
    assert resp.content == ""
    assert resp.provider == "openai_compatible"
    assert resp.latency_ms >= 0


class TestSanitizeMessagesForOpenAI:
    """Tests for _sanitize_messages_for_openai.

    OpenAI's chat completions API rejects unknown fields in tool_call entries
    with "Additional properties are not allowed". The sanitizer ensures that
    framework-only keys (e.g., provider_metadata for Gemini thought_signature
    round-trip) are stripped before the messages reach the SDK.
    """

    def test_strips_provider_metadata_from_tool_calls(self):
        """provider_metadata key in tool_calls entry is stripped."""
        messages = [
            {"role": "user", "content": "hi"},
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
            {"role": "tool", "tool_call_id": "c1", "content": "result"},
        ]
        result = _sanitize_messages_for_openai(messages)
        assert len(result) == 3
        # provider_metadata dropped from tool_call entry
        sanitized_tc = result[1]["tool_calls"][0]
        assert "provider_metadata" not in sanitized_tc
        # Standard fields retained
        assert sanitized_tc["id"] == "c1"
        assert sanitized_tc["type"] == "function"
        assert sanitized_tc["function"] == {"name": "f", "arguments": "{}"}
        # Other messages untouched
        assert result[0] == {"role": "user", "content": "hi"}
        assert result[2] == {
            "role": "tool",
            "tool_call_id": "c1",
            "content": "result",
        }

    def test_passthrough_when_no_tool_calls(self):
        """Messages without tool_calls are passed through unchanged."""
        messages = [
            {"role": "system", "content": "be nice"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        result = _sanitize_messages_for_openai(messages)
        assert result == messages

    def test_does_not_mutate_input(self):
        """Sanitizer does not mutate the original message dicts."""
        original_tc = {
            "id": "c1",
            "type": "function",
            "function": {"name": "f", "arguments": "{}"},
            "provider_metadata": {"thought_signature": "abc=="},
        }
        messages = [{"role": "assistant", "tool_calls": [original_tc]}]
        _sanitize_messages_for_openai(messages)
        # Original tool_call dict still has provider_metadata
        assert "provider_metadata" in original_tc
        assert messages[0]["tool_calls"][0] is original_tc

    def test_multiple_tool_calls_all_sanitized(self):
        """All tool_calls in a single message are sanitized."""
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "f1", "arguments": "{}"},
                        "provider_metadata": {"thought_signature": "a=="},
                    },
                    {
                        "id": "c2",
                        "type": "function",
                        "function": {"name": "f2", "arguments": "{}"},
                        "provider_metadata": {"thought_signature": "b=="},
                    },
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "r1"},
            {"role": "tool", "tool_call_id": "c2", "content": "r2"},
        ]
        result = _sanitize_messages_for_openai(messages)
        for tc in result[0]["tool_calls"]:
            assert "provider_metadata" not in tc

    def test_strips_underscore_prefixed_top_level_keys(self):
        """Top-level ``_provider_metadata`` (framework-only) is stripped.

        Anthropic stashes extended-thinking blocks here via
        ``_provider_metadata``. It must never reach OpenAI's SDK.
        """
        messages = [
            {
                "role": "assistant",
                "content": "hi",
                "_provider_metadata": {"thinking_blocks": [{"type": "thinking"}]},
            },
        ]
        result = _sanitize_messages_for_openai(messages)
        assert "_provider_metadata" not in result[0]
        assert result[0] == {"role": "assistant", "content": "hi"}

    def test_strips_underscore_key_alongside_tool_calls(self):
        """Both the top-level underscore key AND tool_call metadata are stripped."""
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
                "_provider_metadata": {"thinking_blocks": []},
            },
            {"role": "tool", "tool_call_id": "c1", "content": "r1"},
        ]
        result = _sanitize_messages_for_openai(messages)
        assert "_provider_metadata" not in result[0]
        assert "provider_metadata" not in result[0]["tool_calls"][0]

    def test_non_underscore_custom_keys_preserved(self):
        """Only ``_``-prefixed keys are stripped; other custom keys pass through."""
        messages = [
            {
                "role": "assistant",
                "content": "hi",
                "custom_tag": "x",
                "weight": 0.5,
            }
        ]
        result = _sanitize_messages_for_openai(messages)
        # custom_tag and weight are not underscore-prefixed → preserved
        assert result[0]["custom_tag"] == "x"
        assert result[0]["weight"] == 0.5


class TestRepairToolCallPairing:
    """OpenAI-specific tool_call ↔ tool-response pairing invariant."""

    def test_passes_through_plain_messages(self):
        msgs = [
            {"role": "system", "content": "you are x"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        assert _repair_tool_call_pairing(msgs) == msgs

    def test_keeps_complete_tool_call_block(self):
        msgs = [
            {"role": "user", "content": "search"},
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "result"},
            {"role": "assistant", "content": "done"},
        ]
        assert _repair_tool_call_pairing(msgs) == msgs

    def test_drops_incomplete_assistant_with_unanswered_tool_call(self):
        # Assistant declared c1 AND c2 but only c1 got a response.
        msgs = [
            {"role": "user", "content": "go"},
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}},
                    {"id": "c2", "type": "function", "function": {"name": "g", "arguments": "{}"}},
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "r1"},
            {"role": "user", "content": "next"},
        ]
        out = _repair_tool_call_pairing(msgs)
        assert out == [
            {"role": "user", "content": "go"},
            {"role": "user", "content": "next"},
        ]

    def test_drops_stray_tool_message(self):
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "tool", "tool_call_id": "nowhere", "content": "orphan"},
            {"role": "assistant", "content": "hello"},
        ]
        out = _repair_tool_call_pairing(msgs)
        assert out == [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]

    def test_preserves_multiple_blocks(self):
        msgs = [
            {"role": "user", "content": "u1"},
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "a1", "type": "function", "function": {"name": "f", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "a1", "content": "r1"},
            {"role": "assistant", "content": "mid"},
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "a2", "type": "function", "function": {"name": "f", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "a2", "content": "r2"},
        ]
        assert _repair_tool_call_pairing(msgs) == msgs

    def test_drops_duplicate_tool_responses(self):
        # Duplicate tool response for same id — keep only the first.
        msgs = [
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "r1"},
            {"role": "tool", "tool_call_id": "c1", "content": "r1-dup"},
        ]
        out = _repair_tool_call_pairing(msgs)
        assert len(out) == 2
        assert out[1]["content"] == "r1"


@skipif_no_openai
@skipif_no_real
@pytest.mark.asyncio
async def test_openai_real_generate():
    """Real OpenAI API call -- enable with VOLNIX_RUN_REAL_API_TESTS=1."""
    provider = OpenAICompatibleProvider(
        api_key=OPENAI_KEY,
        base_url="https://api.openai.com/v1",
    )
    resp = await provider.generate(
        LLMRequest(
            system_prompt="Reply with exactly the word 'volnix'",
            user_content="What word?",
            max_tokens=50,
        )
    )
    assert resp.error is None
    assert "volnix" in resp.content.lower()
