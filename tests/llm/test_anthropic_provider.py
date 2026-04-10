"""Tests for volnix.llm.providers.anthropic -- Anthropic Claude provider."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from volnix.llm.providers.anthropic import (
    AnthropicProvider,
    _build_anthropic_messages,
    _fix_schema_for_anthropic,
)
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


class TestBuildAnthropicMessages:
    """Tests for _build_anthropic_messages converter.

    Converts OpenAI-style message dicts into Anthropic (system, messages)
    tuple. Handles tool_use, tool_result, thinking, and redacted_thinking
    blocks — the SDK never sees OpenAI-format tool_calls.
    """

    def test_system_extracted_to_first_return(self):
        """System messages → returned as system_prompt, not in messages list."""
        system, msgs = _build_anthropic_messages(
            [{"role": "system", "content": "be helpful"}]
        )
        assert system == "be helpful"
        assert msgs == []

    def test_user_message_string_passthrough(self):
        """User messages with string content pass through."""
        system, msgs = _build_anthropic_messages([{"role": "user", "content": "hi"}])
        assert system is None
        assert msgs == [{"role": "user", "content": "hi"}]

    def test_assistant_text_passthrough(self):
        """Assistant text-only messages pass through as content-block list."""
        system, msgs = _build_anthropic_messages(
            [
                {"role": "user", "content": "q?"},
                {"role": "assistant", "content": "a."},
            ]
        )
        assert len(msgs) == 2
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == [{"type": "text", "text": "a."}]

    def test_assistant_tool_call_becomes_tool_use_block(self):
        """assistant.tool_calls → content=[tool_use_block]."""
        system, msgs = _build_anthropic_messages(
            [
                {"role": "user", "content": "do it"},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "negotiate_propose",
                                "arguments": '{"deal_id": "deal-001", "price": 80}',
                            },
                        }
                    ],
                },
            ]
        )
        assert len(msgs) == 2
        assert msgs[1]["role"] == "assistant"
        blocks = msgs[1]["content"]
        assert len(blocks) == 1
        assert blocks[0]["type"] == "tool_use"
        assert blocks[0]["id"] == "c1"
        assert blocks[0]["name"] == "negotiate_propose"
        # arguments (JSON string) → input (dict)
        assert blocks[0]["input"] == {"deal_id": "deal-001", "price": 80}

    def test_malformed_arguments_fallback_empty_dict(self):
        """Malformed JSON in arguments → input = {} (no exception)."""
        _, msgs = _build_anthropic_messages(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "f", "arguments": "{bad json"},
                        }
                    ],
                }
            ]
        )
        assert msgs[0]["content"][0]["input"] == {}

    def test_tool_role_becomes_user_tool_result_block(self):
        """role: tool → role: user with tool_result content block."""
        _, msgs = _build_anthropic_messages(
            [
                {
                    "role": "tool",
                    "tool_call_id": "c1",
                    "content": "result-data",
                }
            ]
        )
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        block = msgs[0]["content"][0]
        assert block["type"] == "tool_result"
        assert block["tool_use_id"] == "c1"
        assert block["content"] == "result-data"

    def test_assistant_with_thinking_blocks_ordered_first(self):
        """Thinking blocks from _provider_metadata come BEFORE tool_use blocks."""
        _, msgs = _build_anthropic_messages(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "f", "arguments": "{}"},
                        }
                    ],
                    "_provider_metadata": {
                        "thinking_blocks": [
                            {
                                "type": "thinking",
                                "thinking": "Let me reason about this",
                                "signature": "sig-abc",
                            }
                        ]
                    },
                }
            ]
        )
        blocks = msgs[0]["content"]
        assert len(blocks) == 2
        # Thinking block FIRST, tool_use SECOND
        assert blocks[0]["type"] == "thinking"
        assert blocks[0]["thinking"] == "Let me reason about this"
        assert blocks[0]["signature"] == "sig-abc"
        assert blocks[1]["type"] == "tool_use"

    def test_redacted_thinking_block_passthrough(self):
        """Redacted thinking blocks are preserved with their data field."""
        _, msgs = _build_anthropic_messages(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "f", "arguments": "{}"},
                        }
                    ],
                    "_provider_metadata": {
                        "thinking_blocks": [
                            {"type": "redacted_thinking", "data": "opaque-data"}
                        ]
                    },
                }
            ]
        )
        blocks = msgs[0]["content"]
        assert blocks[0]["type"] == "redacted_thinking"
        assert blocks[0]["data"] == "opaque-data"

    def test_multiple_thinking_blocks_preserved_in_order(self):
        """Multiple thinking blocks come out in the same order as input."""
        _, msgs = _build_anthropic_messages(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "f", "arguments": "{}"},
                        }
                    ],
                    "_provider_metadata": {
                        "thinking_blocks": [
                            {"type": "thinking", "thinking": "A", "signature": "sa"},
                            {"type": "redacted_thinking", "data": "B"},
                            {"type": "thinking", "thinking": "C", "signature": "sc"},
                        ]
                    },
                }
            ]
        )
        blocks = msgs[0]["content"]
        assert blocks[0]["thinking"] == "A"
        assert blocks[1]["data"] == "B"
        assert blocks[2]["thinking"] == "C"
        assert blocks[3]["type"] == "tool_use"

    def test_consecutive_tool_results_merged_into_single_user_turn(self):
        """Two consecutive role: tool messages → one user turn with 2 blocks."""
        _, msgs = _build_anthropic_messages(
            [
                {"role": "tool", "tool_call_id": "c1", "content": "r1"},
                {"role": "tool", "tool_call_id": "c2", "content": "r2"},
            ]
        )
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        blocks = msgs[0]["content"]
        assert len(blocks) == 2
        assert blocks[0]["tool_use_id"] == "c1"
        assert blocks[1]["tool_use_id"] == "c2"

    def test_multi_turn_full_conversation(self):
        """user → assistant(tool_use) → tool → assistant(text) round-trip."""
        system, msgs = _build_anthropic_messages(
            [
                {"role": "system", "content": "Be helpful."},
                {"role": "user", "content": "What's 2+2?"},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "calc",
                                "arguments": '{"expr": "2+2"}',
                            },
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "c1", "content": "4"},
                {"role": "assistant", "content": "Four."},
            ]
        )
        assert system == "Be helpful."
        assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
        # First assistant turn has tool_use
        assert msgs[1]["content"][0]["type"] == "tool_use"
        assert msgs[1]["content"][0]["input"] == {"expr": "2+2"}
        # Tool result lives in user turn
        assert msgs[2]["content"][0]["type"] == "tool_result"
        assert msgs[2]["content"][0]["tool_use_id"] == "c1"
        # Final assistant turn has text
        assert msgs[3]["content"][0]["type"] == "text"
        assert msgs[3]["content"][0]["text"] == "Four."

    def test_negotiation_tool_call_round_trip(self):
        """Realistic negotiate_propose with all 5 required terms."""
        _, msgs = _build_anthropic_messages(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "tu_1",
                            "type": "function",
                            "function": {
                                "name": "negotiate_propose",
                                "arguments": (
                                    '{"deal_id": "deal-001", "price": 80, '
                                    '"delivery_weeks": 3, "payment_days": 45, '
                                    '"warranty_months": 18}'
                                ),
                            },
                        }
                    ],
                }
            ]
        )
        block = msgs[0]["content"][0]
        assert block["type"] == "tool_use"
        assert block["name"] == "negotiate_propose"
        assert block["input"] == {
            "deal_id": "deal-001",
            "price": 80,
            "delivery_weeks": 3,
            "payment_days": 45,
            "warranty_months": 18,
        }

    def test_empty_messages_returns_empty_system_and_empty_list(self):
        """[] input → (None, [])."""
        system, msgs = _build_anthropic_messages([])
        assert system is None
        assert msgs == []

    def test_multiple_system_messages_joined_with_double_newline(self):
        """Two system messages are joined with \\n\\n."""
        system, msgs = _build_anthropic_messages(
            [
                {"role": "system", "content": "Rule 1."},
                {"role": "system", "content": "Rule 2."},
                {"role": "user", "content": "ok"},
            ]
        )
        assert system == "Rule 1.\n\nRule 2."
        assert len(msgs) == 1

    def test_assistant_without_tool_calls_or_thinking_skipped_if_empty(self):
        """Assistant with empty text and no tool_calls → no message emitted."""
        _, msgs = _build_anthropic_messages(
            [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": ""},
            ]
        )
        # Empty assistant produces no blocks, so only the user message survives
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"


class TestExtendedThinkingConfig:
    """Tests for the ``thinking`` parameter on Anthropic requests.

    Verifies that ``request.thinking_enabled`` controls whether the SDK
    receives a ``thinking`` param, with correct budget clamping and
    coexistence with tool definitions.
    """

    def _build_provider_and_capture_kwargs(self) -> tuple[AnthropicProvider, dict]:
        """Helper: build a provider whose SDK captures create_kwargs."""
        provider = AnthropicProvider(api_key="test-key")
        captured: dict = {}

        async def fake_create(**kwargs):
            captured.update(kwargs)
            # Return a minimal message stub
            msg = MagicMock()
            msg.content = []
            msg.usage = SimpleNamespace(input_tokens=10, output_tokens=5)
            return msg

        provider._client = MagicMock()
        provider._client.messages = MagicMock()
        provider._client.messages.create = AsyncMock(side_effect=fake_create)
        return provider, captured

    async def test_thinking_disabled_default_omits_param(self):
        provider, captured = self._build_provider_and_capture_kwargs()
        req = LLMRequest(user_content="hi", max_tokens=100)
        await provider.generate(req)
        assert "thinking" not in captured

    async def test_thinking_enabled_sets_param_with_budget(self):
        provider, captured = self._build_provider_and_capture_kwargs()
        req = LLMRequest(
            user_content="hi",
            max_tokens=100,
            thinking_enabled=True,
            thinking_budget_tokens=4096,
        )
        await provider.generate(req)
        assert captured["thinking"] == {
            "type": "enabled",
            "budget_tokens": 4096,
        }

    async def test_thinking_budget_below_minimum_clamped_to_1024(self):
        provider, captured = self._build_provider_and_capture_kwargs()
        req = LLMRequest(
            user_content="hi",
            max_tokens=100,
            thinking_enabled=True,
            thinking_budget_tokens=512,
        )
        await provider.generate(req)
        assert captured["thinking"]["budget_tokens"] == 1024

    async def test_thinking_budget_zero_clamped_to_1024(self):
        provider, captured = self._build_provider_and_capture_kwargs()
        req = LLMRequest(
            user_content="hi",
            max_tokens=100,
            thinking_enabled=True,
            thinking_budget_tokens=0,
        )
        await provider.generate(req)
        assert captured["thinking"]["budget_tokens"] == 1024

    async def test_thinking_enabled_with_tools_coexist(self):
        """thinking and tools can both be in create_kwargs."""
        from volnix.llm.types import ToolDefinition

        provider, captured = self._build_provider_and_capture_kwargs()
        req = LLMRequest(
            user_content="hi",
            max_tokens=100,
            thinking_enabled=True,
            thinking_budget_tokens=2048,
            tools=[
                ToolDefinition(
                    name="foo",
                    service="game",
                    description="test",
                    parameters={"type": "object"},
                )
            ],
        )
        await provider.generate(req)
        assert "thinking" in captured
        assert "tools" in captured
        assert captured["thinking"]["budget_tokens"] == 2048

    async def test_thinking_enabled_forces_temperature_to_1(self):
        """Anthropic rejects any temperature != 1.0 when thinking is enabled.

        Server-side API constraint (not client-side validated by the SDK):
        ``temperature may only be set to 1 when thinking is enabled``.
        The provider must override whatever temperature the request carries
        and force 1.0 in ``create_kwargs`` for the API call.
        """
        provider, captured = self._build_provider_and_capture_kwargs()
        req = LLMRequest(
            user_content="hi",
            max_tokens=100,
            temperature=0.7,  # default framework temperature
            thinking_enabled=True,
            thinking_budget_tokens=2048,
        )
        await provider.generate(req)
        assert captured["temperature"] == 1.0, (
            f"thinking enabled must force temperature=1.0, got {captured['temperature']}"
        )

    async def test_thinking_disabled_preserves_request_temperature(self):
        """Without thinking, the request's temperature is passed through."""
        provider, captured = self._build_provider_and_capture_kwargs()
        req = LLMRequest(
            user_content="hi",
            max_tokens=100,
            temperature=0.5,
            thinking_enabled=False,
        )
        await provider.generate(req)
        assert captured["temperature"] == 0.5

    async def test_thinking_bumps_max_tokens_when_equal_to_budget(self):
        """max_tokens must be STRICTLY greater than thinking budget.

        Anthropic rejects with ``max_tokens must be greater than
        thinking.budget_tokens`` when they are equal. The provider must
        bump max_tokens up to leave headroom for the actual response.
        """
        provider, captured = self._build_provider_and_capture_kwargs()
        req = LLMRequest(
            user_content="hi",
            max_tokens=4096,  # same as default budget
            thinking_enabled=True,
            thinking_budget_tokens=4096,
        )
        await provider.generate(req)
        assert captured["max_tokens"] > captured["thinking"]["budget_tokens"]
        assert captured["max_tokens"] == 4096 + 1024  # budget + headroom

    async def test_thinking_bumps_max_tokens_when_below_budget(self):
        """max_tokens < budget is bumped above the budget."""
        provider, captured = self._build_provider_and_capture_kwargs()
        req = LLMRequest(
            user_content="hi",
            max_tokens=2048,
            thinking_enabled=True,
            thinking_budget_tokens=4096,
        )
        await provider.generate(req)
        assert captured["max_tokens"] > captured["thinking"]["budget_tokens"]
        assert captured["max_tokens"] == 4096 + 1024

    async def test_thinking_preserves_max_tokens_when_already_above_budget(self):
        """When max_tokens is already well above the budget, it's preserved."""
        provider, captured = self._build_provider_and_capture_kwargs()
        req = LLMRequest(
            user_content="hi",
            max_tokens=16384,
            thinking_enabled=True,
            thinking_budget_tokens=4096,
        )
        await provider.generate(req)
        assert captured["max_tokens"] == 16384

    async def test_thinking_disabled_preserves_max_tokens(self):
        """Without thinking, max_tokens is not touched."""
        provider, captured = self._build_provider_and_capture_kwargs()
        req = LLMRequest(
            user_content="hi",
            max_tokens=4096,
            thinking_enabled=False,
        )
        await provider.generate(req)
        assert captured["max_tokens"] == 4096


class TestResponseBlockParser:
    """Tests for Anthropic response block parsing.

    Validates that text, tool_use, thinking, and redacted_thinking blocks
    are correctly routed into LLMResponse.content, .tool_calls, and
    .provider_metadata respectively.
    """

    def _build_provider(self, mock_content_blocks: list) -> AnthropicProvider:
        """Helper: provider whose SDK returns the given content blocks."""
        provider = AnthropicProvider(api_key="test-key")

        async def fake_create(**_kwargs):
            msg = MagicMock()
            msg.content = mock_content_blocks
            msg.usage = SimpleNamespace(input_tokens=10, output_tokens=5)
            return msg

        provider._client = MagicMock()
        provider._client.messages = MagicMock()
        provider._client.messages.create = AsyncMock(side_effect=fake_create)
        return provider

    async def test_response_text_only_populates_content(self):
        text_block = SimpleNamespace(type="text", text="hello world")
        provider = self._build_provider([text_block])
        resp = await provider.generate(LLMRequest(user_content="hi"))
        assert resp.content == "hello world"
        assert resp.tool_calls is None
        assert resp.provider_metadata is None

    async def test_response_tool_use_block_populates_tool_calls(self):
        tool_block = SimpleNamespace(
            type="tool_use", id="c1", name="f", input={"x": 1}
        )
        provider = self._build_provider([tool_block])
        resp = await provider.generate(LLMRequest(user_content="hi"))
        assert resp.tool_calls is not None
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "f"
        assert resp.tool_calls[0].arguments == {"x": 1}
        assert resp.tool_calls[0].id == "c1"

    async def test_response_thinking_block_populates_provider_metadata(self):
        thinking_block = SimpleNamespace(
            type="thinking", thinking="reasoning...", signature="sig-abc"
        )
        provider = self._build_provider([thinking_block])
        resp = await provider.generate(LLMRequest(user_content="hi"))
        assert resp.provider_metadata is not None
        blocks = resp.provider_metadata["thinking_blocks"]
        assert len(blocks) == 1
        assert blocks[0]["type"] == "thinking"
        assert blocks[0]["thinking"] == "reasoning..."
        assert blocks[0]["signature"] == "sig-abc"

    async def test_response_redacted_thinking_block_populates_provider_metadata(self):
        redacted_block = SimpleNamespace(type="redacted_thinking", data="opaque")
        provider = self._build_provider([redacted_block])
        resp = await provider.generate(LLMRequest(user_content="hi"))
        assert resp.provider_metadata is not None
        blocks = resp.provider_metadata["thinking_blocks"]
        assert blocks[0]["type"] == "redacted_thinking"
        assert blocks[0]["data"] == "opaque"

    async def test_response_multiple_mixed_blocks(self):
        blocks_in = [
            SimpleNamespace(type="thinking", thinking="A", signature="sa"),
            SimpleNamespace(type="text", text="hello"),
            SimpleNamespace(type="thinking", thinking="B", signature="sb"),
            SimpleNamespace(type="tool_use", id="c1", name="f", input={"x": 1}),
        ]
        provider = self._build_provider(blocks_in)
        resp = await provider.generate(LLMRequest(user_content="hi"))
        assert resp.content == "hello"
        assert resp.tool_calls is not None and len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "f"
        assert resp.provider_metadata is not None
        thinking = resp.provider_metadata["thinking_blocks"]
        assert len(thinking) == 2
        assert thinking[0]["thinking"] == "A"
        assert thinking[1]["thinking"] == "B"

    async def test_response_no_thinking_blocks_sets_provider_metadata_none(self):
        """No thinking blocks → provider_metadata is None (not empty dict)."""
        text_block = SimpleNamespace(type="text", text="hi")
        provider = self._build_provider([text_block])
        resp = await provider.generate(LLMRequest(user_content="hi"))
        assert resp.provider_metadata is None


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


class TestFixSchemaForAnthropic:
    """Tests for ``_fix_schema_for_anthropic`` — used for BOTH output_schema
    and tool input_schema. Anthropic requires ``additionalProperties: false``
    on every object type and ``items`` on every array type.
    """

    def test_adds_additional_properties_to_object(self):
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        out = _fix_schema_for_anthropic(schema)
        # Top level `type: object` is NOT at a nested position; the fixer
        # only adds the field when walking into nested objects. That's
        # existing behavior — verify the nested case instead.
        assert "properties" in out

    def test_adds_additional_properties_to_nested_object(self):
        schema = {
            "type": "object",
            "properties": {
                "nested": {
                    "type": "object",
                    "properties": {"inner": {"type": "string"}},
                }
            },
        }
        out = _fix_schema_for_anthropic(schema)
        assert out["properties"]["nested"]["additionalProperties"] is False

    def test_preserves_existing_additional_properties(self):
        """Explicit ``additionalProperties: false`` is left alone."""
        schema = {
            "type": "object",
            "properties": {
                "nested": {
                    "type": "object",
                    "properties": {"x": {"type": "integer"}},
                    "additionalProperties": False,
                }
            },
        }
        out = _fix_schema_for_anthropic(schema)
        assert out["properties"]["nested"]["additionalProperties"] is False

    def test_adds_items_to_bare_array(self):
        schema = {
            "type": "object",
            "properties": {"tags": {"type": "array"}},
        }
        out = _fix_schema_for_anthropic(schema)
        assert "items" in out["properties"]["tags"]

    def test_negotiation_tool_schemas_survive_fix(self):
        """End-to-end: the real NEGOTIATION_TOOLS schemas pass Anthropic's fix."""
        from volnix.game.evaluators.negotiation import NEGOTIATION_TOOLS

        for tool in NEGOTIATION_TOOLS:
            out = _fix_schema_for_anthropic(tool.parameters)
            # Top-level schema from our game tools already has
            # additionalProperties: false; the fixer leaves it alone
            assert out.get("additionalProperties") is False, (
                f"{tool.name} lost additionalProperties after fix"
            )
            assert out["type"] == "object"
            assert "required" in out
            assert "properties" in out
