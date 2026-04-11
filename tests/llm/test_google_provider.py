"""Tests for volnix.llm.providers.google -- Google Gemini provider."""

import os

import pytest

from volnix.llm.providers.google import (
    GoogleNativeProvider,
    _sanitize_tool_params_for_gemini,
)
from volnix.llm.types import LLMRequest, LLMUsage

GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY")
skipif_no_google = pytest.mark.skipif(not GOOGLE_KEY, reason="GOOGLE_API_KEY not set")

# Toggle: VOLNIX_RUN_REAL_API_TESTS=1 to enable expensive real API tests
RUN_REAL = os.environ.get("VOLNIX_RUN_REAL_API_TESTS", "").lower() in ("1", "true", "yes")
skipif_no_real = pytest.mark.skipif(not RUN_REAL, reason="VOLNIX_RUN_REAL_API_TESTS not enabled")


def test_google_provider_init():
    """GoogleNativeProvider initialises with api_key and default_model."""
    provider = GoogleNativeProvider(api_key="test-key", default_model="gemini-3-flash-preview")
    assert provider._default_model == "gemini-3-flash-preview"
    assert provider.provider_name == "google"


def test_google_provider_get_info():
    """get_info returns correct Google metadata."""
    provider = GoogleNativeProvider(api_key="test-key")
    info = provider.get_info()
    assert info.type == "google"
    assert info.name == "google"
    assert info.base_url == "https://generativelanguage.googleapis.com"
    assert "gemini-3-flash-preview" in info.available_models


async def test_google_provider_list_models():
    """list_models returns the expected static model list."""
    provider = GoogleNativeProvider(api_key="test-key")
    models = await provider.list_models()
    assert "gemini-3-flash-preview" in models
    assert len(models) >= 3


@pytest.mark.asyncio
async def test_google_provider_error_handling():
    """Provider returns an error response on invalid key."""
    provider = GoogleNativeProvider(api_key="bad-key")
    req = LLMRequest(user_content="test")
    resp = await provider.generate(req)
    assert resp.error is not None
    assert resp.content == ""
    assert resp.provider == "google"
    assert resp.latency_ms >= 0


def test_google_provider_handles_none_usage_tokens():
    """Regression: gemini-3-flash-preview returns None for candidates_token_count.

    Reproduces the exact failure mode from run_3cddf66b187c: the Gemini
    SDK returns a ``usage_metadata`` object where
    ``candidates_token_count`` is set-but-null (``None``). The provider's
    defensive ``getattr(usage_meta, "candidates_token_count", 0)``
    pattern returns ``None`` because the attribute *exists*, just holds
    ``None`` — ``getattr`` default only kicks in on missing attributes.
    The ``None`` then flows into ``LLMUsage(completion_tokens=None)``
    which, prior to the field_validator fix, raised
    ``pydantic.ValidationError`` and the router treated it as
    non-retryable.

    This test asserts the fixed behavior: the same ``getattr`` pattern
    + ``LLMUsage`` construction no longer raises, and ``None`` is
    coerced to ``0`` at the model boundary via the validator.
    """

    class FakeGeminiUsageMeta:
        """Simulates Gemini SDK's usage_metadata with a None candidates count."""

        prompt_token_count = 42
        candidates_token_count = None  # ← the bug shape from run_3cddf66b187c
        total_token_count = 42

    usage_meta = FakeGeminiUsageMeta()

    # The exact pattern used by GoogleNativeProvider in google.py:477-484.
    usage = LLMUsage(
        prompt_tokens=(getattr(usage_meta, "prompt_token_count", 0) if usage_meta else 0),
        completion_tokens=(getattr(usage_meta, "candidates_token_count", 0) if usage_meta else 0),
        total_tokens=(getattr(usage_meta, "total_token_count", 0) if usage_meta else 0),
    )
    # No exception raised. None was coerced to 0.
    assert usage.prompt_tokens == 42
    assert usage.completion_tokens == 0
    assert usage.total_tokens == 42
    assert usage.cost_usd == 0.0


def test_google_provider_handles_completely_null_usage_meta():
    """Edge case: all three Gemini token counts are None.

    Less likely than a single None, but possible if the SDK returns a
    usage_metadata stub with all counters unpopulated (e.g. when the
    generation was truncated before any completion tokens were emitted).
    """

    class FakeGeminiUsageMeta:
        prompt_token_count = None
        candidates_token_count = None
        total_token_count = None

    usage_meta = FakeGeminiUsageMeta()
    usage = LLMUsage(
        prompt_tokens=getattr(usage_meta, "prompt_token_count", 0),
        completion_tokens=getattr(usage_meta, "candidates_token_count", 0),
        total_tokens=getattr(usage_meta, "total_token_count", 0),
    )
    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0
    assert usage.total_tokens == 0


@skipif_no_google
@skipif_no_real
@pytest.mark.asyncio
async def test_google_real_generate():
    """Real Google API call -- enable with VOLNIX_RUN_REAL_API_TESTS=1."""
    provider = GoogleNativeProvider(api_key=GOOGLE_KEY)
    resp = await provider.generate(
        LLMRequest(
            system_prompt="Reply with exactly the word 'volnix'",
            user_content="What word?",
            max_tokens=50,
        )
    )
    assert resp.error is None
    assert "volnix" in resp.content.lower()


# ---------------------------------------------------------------------------
# Multi-turn message conversion helper tests
# ---------------------------------------------------------------------------


class TestBuildContentsFromMessages:
    """Tests for GoogleNativeProvider._build_contents_from_messages.

    Validates the conversion from OpenAI-format messages to Gemini Content list
    + system_instruction, following the Gemini SDK's AFC convention
    (role="user" for function responses, NOT "tool").
    """

    def test_system_only(self):
        """System message goes to system_instruction; contents gets placeholder."""
        contents, sys_instr = GoogleNativeProvider._build_contents_from_messages(
            [{"role": "system", "content": "Be helpful."}]
        )
        assert sys_instr == "Be helpful."
        assert len(contents) == 1
        assert contents[0].role == "user"
        assert contents[0].parts[0].text == " "

    def test_multiple_system_messages_joined(self):
        """Multiple system messages are joined with double newlines."""
        _, sys_instr = GoogleNativeProvider._build_contents_from_messages(
            [
                {"role": "system", "content": "You are helpful."},
                {"role": "system", "content": "You are concise."},
            ]
        )
        assert sys_instr == "You are helpful.\n\nYou are concise."

    def test_user_message(self):
        """User message becomes Content with text part."""
        contents, sys_instr = GoogleNativeProvider._build_contents_from_messages(
            [{"role": "user", "content": "Hello"}]
        )
        assert sys_instr == ""
        assert len(contents) == 1
        assert contents[0].role == "user"
        assert contents[0].parts[0].text == "Hello"

    def test_assistant_tool_call(self):
        """Assistant tool_calls become model Content with function_call parts."""
        import json as _json

        contents, _ = GoogleNativeProvider._build_contents_from_messages(
            [
                {"role": "user", "content": "Do it"},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "do_thing",
                                "arguments": _json.dumps({"x": 1}),
                            },
                        }
                    ],
                },
            ]
        )
        assert len(contents) == 2
        assert contents[1].role == "model"
        fc = contents[1].parts[0].function_call
        assert fc.name == "do_thing"
        assert fc.args == {"x": 1}
        assert fc.id == "call_1"

    def test_tool_response_with_id_matching(self):
        """Tool response becomes user Content with function_response part.

        Verifies:
          - role="user" (not "tool") per Gemini SDK AFC convention
          - name resolved from prior assistant tool_call via id match
          - id preserved for call↔response matching
        """
        contents, _ = GoogleNativeProvider._build_contents_from_messages(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "do_thing", "arguments": "{}"},
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "content": '{"ok": true}',
                },
            ]
        )
        # contents[0] = assistant (model), contents[1] = tool (user)
        assert contents[1].role == "user"
        fr = contents[1].parts[0].function_response
        assert fr.name == "do_thing"  # resolved via id lookup
        assert fr.response == {"ok": True}
        assert fr.id == "call_1"  # matches the call id

    def test_tool_response_non_json_wrapped(self):
        """Plain-text tool response is wrapped in {'result': ...}."""
        contents, _ = GoogleNativeProvider._build_contents_from_messages(
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
                },
                {"role": "tool", "tool_call_id": "c1", "content": "plain text"},
            ]
        )
        fr = contents[1].parts[0].function_response
        assert fr.response == {"result": "plain text"}

    def test_tool_response_json_array_wrapped(self):
        """JSON array tool response wrapped in {'result': [...]}."""
        contents, _ = GoogleNativeProvider._build_contents_from_messages(
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
                },
                {"role": "tool", "tool_call_id": "c1", "content": "[1, 2, 3]"},
            ]
        )
        fr = contents[1].parts[0].function_response
        assert fr.response == {"result": [1, 2, 3]}

    def test_malformed_tool_arguments(self):
        """Malformed JSON in tool arguments becomes empty dict."""
        contents, _ = GoogleNativeProvider._build_contents_from_messages(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "f", "arguments": "{not json"},
                        }
                    ],
                },
            ]
        )
        assert contents[0].parts[0].function_call.args == {}

    def test_empty_messages_placeholder(self):
        """Empty messages list produces fallback placeholder and empty sys_instr."""
        contents, sys_instr = GoogleNativeProvider._build_contents_from_messages([])
        assert sys_instr == ""
        assert len(contents) == 1
        assert contents[0].role == "user"
        assert contents[0].parts[0].text == " "

    def test_multiple_parallel_tool_calls(self):
        """Multiple tool_calls in one assistant msg → multiple parts in one Content."""
        contents, _ = GoogleNativeProvider._build_contents_from_messages(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "f1", "arguments": "{}"},
                        },
                        {
                            "id": "c2",
                            "type": "function",
                            "function": {"name": "f2", "arguments": "{}"},
                        },
                    ],
                },
            ]
        )
        assert len(contents) == 1
        assert len(contents[0].parts) == 2
        assert contents[0].parts[0].function_call.name == "f1"
        assert contents[0].parts[1].function_call.name == "f2"

    def test_assistant_with_text_and_tool_call(self):
        """Assistant with both text and tool_calls → both as parts in one Content."""
        contents, _ = GoogleNativeProvider._build_contents_from_messages(
            [
                {
                    "role": "assistant",
                    "content": "Let me check.",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "f", "arguments": "{}"},
                        }
                    ],
                },
            ]
        )
        parts = contents[0].parts
        assert len(parts) == 2
        assert parts[0].function_call is not None
        assert parts[1].text == "Let me check."

    def test_multi_turn_full_conversation(self):
        """Full multi-turn: system → user → assistant(tool_call) → tool → assistant(text)."""
        messages = [
            {"role": "system", "content": "Be helpful."},
            {"role": "user", "content": "What's the weather?"},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"city": "SF"}',
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": '{"temp": 72}'},
            {"role": "assistant", "content": "It's 72 degrees."},
        ]
        contents, sys_instr = GoogleNativeProvider._build_contents_from_messages(messages)
        assert sys_instr == "Be helpful."
        # Role sequence: user → model(call) → user(response) → model(text)
        assert [c.role for c in contents] == ["user", "model", "user", "model"]
        # First user message
        assert contents[0].parts[0].text == "What's the weather?"
        # Assistant call with id preserved
        assert contents[1].parts[0].function_call.name == "get_weather"
        assert contents[1].parts[0].function_call.id == "c1"
        # Tool response with matching id
        assert contents[2].parts[0].function_response.id == "c1"
        assert contents[2].parts[0].function_response.response == {"temp": 72}
        # Final assistant text
        assert contents[3].parts[0].text == "It's 72 degrees."


class TestResolveContentsAndConfig:
    """Tests for GoogleNativeProvider._resolve_contents_and_config.

    Validates that the helper correctly handles all 4 combinations:
    (cached|non-cached) x (single-turn|multi-turn).
    """

    def test_single_turn_non_cached_sets_system_instruction(self):
        """Single-turn, non-cached: system_prompt → config.system_instruction."""
        provider = GoogleNativeProvider(api_key="test")
        config: dict = {}
        req = LLMRequest(system_prompt="Be nice.", user_content="Hi")
        result = provider._resolve_contents_and_config(req, config, cached=False)
        assert result == "Hi"
        assert config["system_instruction"] == "Be nice."

    def test_single_turn_cached_skips_system_instruction(self):
        """Single-turn, cached: system_instruction NOT set (already in cache)."""
        provider = GoogleNativeProvider(api_key="test")
        config: dict = {"cached_content": "cache_abc"}
        req = LLMRequest(system_prompt="Be nice.", user_content="Hi")
        result = provider._resolve_contents_and_config(req, config, cached=True)
        assert result == "Hi"
        assert "system_instruction" not in config

    def test_multi_turn_non_cached_sets_system_instruction(self):
        """Multi-turn, non-cached: system from messages → config."""
        provider = GoogleNativeProvider(api_key="test")
        config: dict = {}
        req = LLMRequest(
            messages=[
                {"role": "system", "content": "Be helpful."},
                {"role": "user", "content": "Hi"},
            ]
        )
        result = provider._resolve_contents_and_config(req, config, cached=False)
        assert isinstance(result, list)
        assert config["system_instruction"] == "Be helpful."

    def test_multi_turn_cached_skips_system_instruction(self):
        """Multi-turn, cached: system from messages is dropped (cache has it)."""
        provider = GoogleNativeProvider(api_key="test")
        config: dict = {"cached_content": "cache_abc"}
        req = LLMRequest(
            messages=[
                {"role": "system", "content": "Be helpful."},
                {"role": "user", "content": "Hi"},
            ]
        )
        result = provider._resolve_contents_and_config(req, config, cached=True)
        assert isinstance(result, list)
        assert "system_instruction" not in config
        # But the message contents still get built
        assert len(result) >= 1

    def test_multi_turn_preserves_tool_calls(self):
        """Multi-turn conversion preserves function calls and responses."""
        provider = GoogleNativeProvider(api_key="test")
        config: dict = {}
        req = LLMRequest(
            messages=[
                {"role": "user", "content": "Do it"},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "f", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "c1", "content": '{"ok": true}'},
            ]
        )
        result = provider._resolve_contents_and_config(req, config, cached=False)
        assert isinstance(result, list)
        assert len(result) == 3
        # Assistant's tool call preserved
        assert result[1].parts[0].function_call.name == "f"
        # Tool response with matching id
        assert result[2].parts[0].function_response.id == "c1"


class TestThoughtSignatureRoundTrip:
    """Tests for Gemini thought_signature round-trip through provider_metadata.

    Gemini 3 thinking models return thought_signature bytes on function_call
    parts. When echoed back in a subsequent request, the signature must be
    present or Gemini returns 400 INVALID_ARGUMENT. These tests validate the
    message → Content rebuild path in _build_contents_from_messages.
    """

    def test_assistant_tool_call_with_thought_signature_restored(self):
        """Assistant tool_call with base64-encoded thought_signature is restored to Part."""
        import base64 as _b64

        sig_bytes = b"\x01\x02\x03SIG_BYTES\xff\xfe"
        sig_b64 = _b64.b64encode(sig_bytes).decode("ascii")
        contents, _ = GoogleNativeProvider._build_contents_from_messages(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "do_thing", "arguments": '{"x": 1}'},
                            "provider_metadata": {"thought_signature": sig_b64},
                        }
                    ],
                },
            ]
        )
        assert len(contents) == 1
        part = contents[0].parts[0]
        assert part.function_call.name == "do_thing"
        assert part.function_call.args == {"x": 1}
        assert part.thought_signature == sig_bytes

    def test_assistant_tool_call_without_metadata_no_signature(self):
        """Assistant tool_call without provider_metadata produces Part without signature."""
        contents, _ = GoogleNativeProvider._build_contents_from_messages(
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
                },
            ]
        )
        part = contents[0].parts[0]
        assert part.function_call.name == "f"
        assert part.thought_signature is None

    def test_assistant_tool_call_malformed_signature_base64_is_ignored(self):
        """Malformed base64 in thought_signature is dropped without crashing."""
        contents, _ = GoogleNativeProvider._build_contents_from_messages(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "f", "arguments": "{}"},
                            "provider_metadata": {"thought_signature": "!!!not-valid-base64!!!"},
                        }
                    ],
                },
            ]
        )
        part = contents[0].parts[0]
        assert part.function_call.name == "f"
        assert part.thought_signature is None

    def test_assistant_tool_call_non_dict_metadata_is_ignored(self):
        """Non-dict provider_metadata is ignored without error."""
        contents, _ = GoogleNativeProvider._build_contents_from_messages(
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "f", "arguments": "{}"},
                            "provider_metadata": "not-a-dict",
                        }
                    ],
                },
            ]
        )
        part = contents[0].parts[0]
        assert part.function_call.name == "f"
        assert part.thought_signature is None


class TestSanitizeToolParamsForGemini:
    """Tests for _sanitize_tool_params_for_gemini.

    Gemini's function-declaration API rejects any JSON Schema key outside
    its allowed set. This sanitizer keeps only supported keys, recursing
    into nested ``properties`` and ``items``. Standard JSON Schema keys
    like ``additionalProperties`` (required by Anthropic, ignored by
    OpenAI, rejected by Gemini) must be stripped.
    """

    def test_strips_additional_properties_at_top_level(self):
        schema = {
            "type": "object",
            "required": ["x"],
            "properties": {"x": {"type": "integer"}},
            "additionalProperties": False,
        }
        out = _sanitize_tool_params_for_gemini(schema)
        assert "additionalProperties" not in out
        assert out["type"] == "object"
        assert out["required"] == ["x"]
        assert out["properties"] == {"x": {"type": "integer"}}

    def test_strips_additional_properties_nested(self):
        """Nested ``properties`` are recursively cleaned."""
        schema = {
            "type": "object",
            "properties": {
                "nested": {
                    "type": "object",
                    "properties": {"inner": {"type": "string"}},
                    "additionalProperties": False,
                }
            },
            "additionalProperties": False,
        }
        out = _sanitize_tool_params_for_gemini(schema)
        assert "additionalProperties" not in out
        assert "additionalProperties" not in out["properties"]["nested"]
        assert out["properties"]["nested"]["properties"]["inner"]["type"] == "string"

    def test_strips_additional_properties_in_array_items(self):
        """``items`` schemas are also recursively cleaned."""
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "additionalProperties": False,
            },
        }
        out = _sanitize_tool_params_for_gemini(schema)
        assert "additionalProperties" not in out["items"]
        assert out["items"]["properties"]["id"]["type"] == "string"

    def test_keeps_allowed_keys(self):
        """Known-good JSON Schema keys are preserved."""
        schema = {
            "type": "object",
            "description": "a thing",
            "required": ["price"],
            "properties": {
                "price": {
                    "type": "number",
                    "description": "price per unit",
                    "minimum": 0,
                    "maximum": 1000,
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "status": {
                    "type": "string",
                    "enum": ["open", "closed"],
                },
            },
        }
        out = _sanitize_tool_params_for_gemini(schema)
        # Fully-compliant schema is an identity (property values are
        # themselves recursively sanitized but all their keys are allowed)
        assert out["type"] == "object"
        assert out["description"] == "a thing"
        assert out["required"] == ["price"]
        assert out["properties"]["price"]["minimum"] == 0
        assert out["properties"]["price"]["maximum"] == 1000
        assert out["properties"]["tags"]["items"]["type"] == "string"
        assert out["properties"]["status"]["enum"] == ["open", "closed"]

    def test_drops_unknown_top_level_keys(self):
        """Anything not in the allowlist is dropped."""
        schema = {
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "$schema": "http://json-schema.org/draft-07/schema#",
            "definitions": {},
            "examples": [{"x": 1}],
        }
        out = _sanitize_tool_params_for_gemini(schema)
        assert "$schema" not in out
        assert "definitions" not in out
        assert "examples" not in out
        assert out["type"] == "object"
        assert out["properties"] == {"x": {"type": "integer"}}

    def test_non_dict_input_returned_unchanged(self):
        """Primitive inputs pass through untouched."""
        assert _sanitize_tool_params_for_gemini("string") == "string"
        assert _sanitize_tool_params_for_gemini(42) == 42
        assert _sanitize_tool_params_for_gemini(None) is None
        assert _sanitize_tool_params_for_gemini([1, 2, 3]) == [1, 2, 3]

    def test_negotiation_tool_schemas_survive_sanitization(self):
        """End-to-end: the actual NEGOTIATION_TOOLS schemas sanitize cleanly."""
        from volnix.game.evaluators.negotiation import NEGOTIATION_TOOLS

        for tool in NEGOTIATION_TOOLS:
            out = _sanitize_tool_params_for_gemini(tool.parameters)
            # No forbidden keys at top level
            assert "additionalProperties" not in out, (
                f"{tool.name} still has additionalProperties after sanitize"
            )
            # No forbidden keys in nested properties either
            for prop_name, prop_schema in out.get("properties", {}).items():
                if isinstance(prop_schema, dict):
                    assert "additionalProperties" not in prop_schema, (
                        f"{tool.name}.{prop_name} has additionalProperties"
                    )
            # Core structure survives
            assert out["type"] == "object"
            assert "required" in out
            assert "properties" in out
            # Propose / counter still require all five terms
            if tool.name in ("negotiate_propose", "negotiate_counter"):
                assert set(out["required"]) == {
                    "deal_id",
                    "price",
                    "delivery_weeks",
                    "payment_days",
                    "warranty_months",
                }
