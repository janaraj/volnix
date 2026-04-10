"""Anthropic LLM provider for the Volnix framework.

Implements the :class:`~volnix.llm.provider.LLMProvider` interface
using the Anthropic Messages API.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, ClassVar

import anthropic
from anthropic import AsyncAnthropic

from volnix.llm.provider import LLMProvider
from volnix.llm.types import LLMRequest, LLMResponse, LLMUsage, ProviderInfo, ToolCall

logger = logging.getLogger(__name__)


def _build_anthropic_messages(
    messages: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    """Convert OpenAI-style message dicts into Anthropic (system, messages).

    Returns a tuple of ``(system_prompt_or_none, anthropic_messages)``. The
    system prompt is extracted from ``role: system`` messages and joined
    with double newlines. The returned messages list contains only
    ``role: user`` and ``role: assistant`` entries with ``content`` as a
    list of ContentBlockParam dicts (or a plain string for simple cases).

    Conversion rules:

      - ``{role: system, content: X}`` → appended to the system_prompt string
      - ``{role: user, content: X}`` → ``{role: user, content: X}``
      - ``{role: assistant, content: X}`` (text only) → passthrough
      - ``{role: assistant, tool_calls: [...], _provider_metadata: {thinking_blocks: [...]}}``
        → ``{role: assistant, content: [*thinking_blocks, text?, *tool_use_blocks]}``
      - ``{role: tool, tool_call_id, content}``
        → ``{role: user, content: [{type: tool_result, tool_use_id, content}]}``

    Consecutive messages of the same resolved role (after converting
    ``role: tool`` → ``role: user``) are merged into a single message
    with concatenated content blocks, matching Anthropic's API expectation.

    Tool call argument conversion: OpenAI ``arguments`` is a JSON string;
    Anthropic ``input`` is a dict. ``json.loads`` the string; on failure
    fall back to ``{}`` with a debug log.
    """
    system_parts: list[str] = []
    raw_converted: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "") or ""

        if role == "system":
            if content:
                system_parts.append(content)
            continue

        if role == "user":
            raw_converted.append({"role": "user", "content": content})
            continue

        if role == "assistant":
            blocks: list[dict[str, Any]] = []

            # 1. Thinking blocks from _provider_metadata (must come first)
            pmeta = msg.get("_provider_metadata") or {}
            thinking_blocks = pmeta.get("thinking_blocks") or []
            for tb in thinking_blocks:
                if isinstance(tb, dict) and tb.get("type") in (
                    "thinking",
                    "redacted_thinking",
                ):
                    blocks.append(dict(tb))

            # 2. Optional text content
            if content:
                blocks.append({"type": "text", "text": content})

            # 3. Tool-use blocks from tool_calls
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function", {}) or {}
                name = fn.get("name", "") or ""
                raw_args = fn.get("arguments", "") or "{}"
                try:
                    parsed_input = (
                        json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                    )
                    if not isinstance(parsed_input, dict):
                        parsed_input = {}
                except (json.JSONDecodeError, ValueError):
                    logger.debug("Malformed tool arguments for Anthropic: %.80s", raw_args)
                    parsed_input = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id") or "",
                        "name": name,
                        "input": parsed_input,
                    }
                )

            if blocks:
                raw_converted.append({"role": "assistant", "content": blocks})
            continue

        if role == "tool":
            raw_converted.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.get("tool_call_id") or "",
                            "content": content,
                        }
                    ],
                }
            )
            continue

    # Merge consecutive same-role messages into a single content-block list.
    merged: list[dict[str, Any]] = []
    for rm in raw_converted:
        if merged and merged[-1]["role"] == rm["role"]:
            prev_content = merged[-1]["content"]
            this_content = rm["content"]
            if isinstance(prev_content, str):
                prev_content = [{"type": "text", "text": prev_content}]
            if isinstance(this_content, str):
                this_content = [{"type": "text", "text": this_content}]
            merged[-1] = {
                "role": rm["role"],
                "content": prev_content + this_content,
            }
        else:
            merged.append(rm)

    system_prompt = "\n\n".join(system_parts) if system_parts else None
    return system_prompt, merged


def _fix_schema_for_anthropic(schema: Any) -> Any:
    """Recursively fix schemas for Anthropic structured output compatibility.

    Anthropic requires ``additionalProperties: false`` on every object type
    and ``items`` on every array type.
    """
    if not isinstance(schema, dict):
        return schema
    result: dict[str, Any] = {}
    for k, v in schema.items():
        if isinstance(v, dict):
            if v.get("type") == "object" and "additionalProperties" not in v:
                v = {**v, "additionalProperties": False}
            if v.get("type") == "array" and "items" not in v:
                v = {**v, "items": {"type": "object"}}
            result[k] = _fix_schema_for_anthropic(v)
        else:
            result[k] = v
    return result


class AnthropicProvider(LLMProvider):
    """LLM provider backed by the Anthropic Messages API."""

    provider_name: ClassVar[str] = "anthropic"

    def __init__(
        self, api_key: str, default_model: str = "claude-sonnet-4-6", timeout: float = 300.0
    ) -> None:
        self._client = AsyncAnthropic(api_key=api_key, timeout=timeout)
        self._default_model = default_model

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Send a request to the Anthropic API.

        Args:
            request: The LLM request payload.

        Returns:
            The LLM response.
        """
        model = request.model_override or self._default_model
        start = time.monotonic()
        try:
            # Build system parameter with optional prompt caching.
            # Anthropic caches the system prompt prefix server-side when
            # cache_control is set. Subsequent calls with the same prefix
            # are charged at 10% of input cost (90% savings).
            system_content = request.system_prompt or "You are a helpful assistant."
            if request.cache_system_prompt:
                system_param: str | list[dict] = [
                    {
                        "type": "text",
                        "text": system_content,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
            else:
                system_param = system_content

            if request.messages:
                # Convert OpenAI-style messages to Anthropic content blocks.
                # This is where tool_use / tool_result / thinking blocks
                # are built — the raw message dicts never reach the SDK.
                converted_system, converted_msgs = _build_anthropic_messages(request.messages)
                msg_system = converted_system if converted_system is not None else system_param
                msg_list = converted_msgs or [{"role": "user", "content": ""}]
            else:
                msg_system = system_param
                msg_list = [{"role": "user", "content": request.user_content}]

            create_kwargs: dict = dict(
                model=model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                system=msg_system,
                messages=msg_list,
            )

            # Extended thinking: opt in via request.thinking_enabled.
            #
            # Anthropic API constraints (not validated by the SDK types, all
            # enforced server-side with invalid_request_error):
            #   1. budget_tokens must be >= 1024 — clamped here.
            #   2. temperature must equal 1.0 when thinking is enabled —
            #      the request's temperature is overridden for this call.
            #   3. max_tokens must be STRICTLY greater than budget_tokens —
            #      the thinking budget is drawn from the overall output
            #      budget. We bump max_tokens up when needed so the call
            #      always has at least 1024 tokens of room for the final
            #      response on top of the thinking budget.
            #
            # When disabled (default), none of this runs and Claude
            # behaves identically to before.
            if request.thinking_enabled:
                budget = max(request.thinking_budget_tokens, 1024)
                create_kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": budget,
                }
                create_kwargs["temperature"] = 1.0
                # Guarantee headroom above the thinking budget so the
                # final response has tokens to use. Anthropic's docs
                # suggest at least 1024 tokens of headroom is reasonable.
                min_max_tokens = budget + 1024
                if create_kwargs["max_tokens"] <= budget:
                    logger.info(
                        "Anthropic max_tokens (%d) <= thinking budget (%d); "
                        "bumping max_tokens to %d so the response has headroom",
                        create_kwargs["max_tokens"],
                        budget,
                        min_max_tokens,
                    )
                    create_kwargs["max_tokens"] = min_max_tokens
                logger.info(
                    "Anthropic extended thinking enabled "
                    "(budget=%d, max_tokens=%d, temperature=1.0)",
                    budget,
                    create_kwargs["max_tokens"],
                )

            # Structured output: force valid JSON matching the schema.
            # Uses output_config with json_schema format.
            if request.output_schema:
                create_kwargs["output_config"] = {
                    "format": {
                        "type": "json_schema",
                        "schema": _fix_schema_for_anthropic(request.output_schema),
                    }
                }
                schema_type = request.output_schema.get("type", "?")
                logger.info("Anthropic structured output enabled (schema type=%s)", schema_type)

            if request.tools:
                # Normalize each tool's input_schema — Anthropic requires
                # ``additionalProperties: false`` on every object type and
                # ``items`` on every array type. Schemas that happen to
                # already comply are a no-op; schemas missing those fields
                # are fixed before the SDK call to avoid BadRequestError.
                create_kwargs["tools"] = [
                    {
                        "name": t.name,
                        "description": t.description,
                        "input_schema": _fix_schema_for_anthropic(t.parameters),
                    }
                    for t in request.tools
                ]
                tc_map = {
                    "auto": {"type": "auto"},
                    "required": {"type": "any"},
                    "none": {"type": "none"},
                }
                create_kwargs["tool_choice"] = tc_map.get(
                    request.tool_choice or "required", {"type": "any"}
                )

            try:
                message = await self._client.messages.create(**create_kwargs)
            except anthropic.BadRequestError as schema_exc:
                err_msg = str(schema_exc).lower()
                if "output_config" in create_kwargs and (
                    "schema" in err_msg or "too complex" in err_msg or "not supported" in err_msg
                ):
                    logger.warning(
                        "Anthropic schema rejected (%s) — retrying without structured output",
                        str(schema_exc)[:100],
                    )
                    del create_kwargs["output_config"]
                    message = await self._client.messages.create(**create_kwargs)
                else:
                    raise
            latency = (time.monotonic() - start) * 1000

            # Parse text, tool_use, thinking, and redacted_thinking blocks.
            # Thinking blocks are stashed into ``provider_metadata`` so the
            # agency engine can round-trip them on the next tool-loop turn
            # (Claude rejects follow-up requests whose history contains
            # tool_use blocks without their preceding thinking signatures).
            content = ""
            parsed_tool_calls: list[ToolCall] | None = None
            thinking_blocks_out: list[dict[str, Any]] = []
            for block in message.content:
                btype = getattr(block, "type", None)
                if btype == "text":
                    content = block.text
                elif btype == "tool_use":
                    if parsed_tool_calls is None:
                        parsed_tool_calls = []
                    tool_input = block.input if isinstance(block.input, dict) else {}
                    parsed_tool_calls.append(
                        ToolCall(
                            name=block.name,
                            arguments=tool_input,
                            id=getattr(block, "id", ""),
                        )
                    )
                elif btype == "thinking":
                    thinking_blocks_out.append(
                        {
                            "type": "thinking",
                            "thinking": getattr(block, "thinking", ""),
                            "signature": getattr(block, "signature", ""),
                        }
                    )
                elif btype == "redacted_thinking":
                    thinking_blocks_out.append(
                        {
                            "type": "redacted_thinking",
                            "data": getattr(block, "data", ""),
                        }
                    )
                elif hasattr(block, "text"):
                    # Defensive fallback for SDK variants that don't set
                    # ``type`` but do carry a ``text`` attribute.
                    content = block.text

            response_provider_metadata: dict[str, Any] | None = None
            if thinking_blocks_out:
                response_provider_metadata = {"thinking_blocks": thinking_blocks_out}

            usage = LLMUsage(
                prompt_tokens=message.usage.input_tokens,
                completion_tokens=message.usage.output_tokens,
                total_tokens=message.usage.input_tokens + message.usage.output_tokens,
                cost_usd=self._estimate_cost(
                    model, message.usage.input_tokens, message.usage.output_tokens
                ),
            )
            # Parse structured output when schema was requested
            parsed_structured = None
            if request.output_schema and content:
                try:
                    parsed_structured = json.loads(content)
                    items = len(parsed_structured) if isinstance(parsed_structured, list) else 1
                    logger.info(
                        "Anthropic structured output parsed: %d items, %d chars",
                        items,
                        len(content),
                    )
                except json.JSONDecodeError:
                    logger.warning(
                        "Anthropic structured output was not valid JSON (%d chars)", len(content)
                    )

            return LLMResponse(
                content=content,
                structured_output=parsed_structured,
                tool_calls=parsed_tool_calls,
                usage=usage,
                model=model,
                provider="anthropic",
                latency_ms=latency,
                provider_metadata=response_provider_metadata,
            )
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            return LLMResponse(
                content="",
                usage=LLMUsage(),
                model=model,
                provider="anthropic",
                latency_ms=latency,
                error=f"{type(e).__name__}: {str(e)[:500]}",
            )

    async def validate_connection(self) -> bool:
        """Validate connectivity to the Anthropic API.

        Returns:
            ``True`` if reachable with valid credentials.
        """
        try:
            # Minimal request to verify credentials
            await self._client.messages.create(
                model=self._default_model,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False

    # Known models — override via subclass or config for new models
    KNOWN_MODELS: list[str] = [
        "claude-sonnet-4-6",
        "claude-opus-4-6",
        "claude-haiku-4-5",
    ]

    # Cost per 1M tokens: (input_usd, output_usd)
    COST_TABLE: dict[str, tuple[float, float]] = {
        "claude-sonnet-4-6": (3.0, 15.0),
        "claude-opus-4-6": (5.0, 25.0),
        "claude-haiku-4-5": (1.0, 5.0),
    }

    async def list_models(self) -> list[str]:
        """List available Anthropic models.

        Returns:
            A list of model identifier strings.
        """
        return list(self.KNOWN_MODELS)

    def get_info(self) -> ProviderInfo:
        """Return provider metadata.

        Returns:
            A :class:`ProviderInfo` describing this Anthropic provider.
        """
        return ProviderInfo(
            name="anthropic",
            type="anthropic",
            base_url="https://api.anthropic.com",
            available_models=list(self.KNOWN_MODELS),
        )

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate the cost of a request in USD.

        Args:
            model: The model identifier.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.

        Returns:
            Estimated cost in US dollars.
        """
        in_cost, out_cost = self.COST_TABLE.get(model, (3.0, 15.0))
        return (input_tokens * in_cost + output_tokens * out_cost) / 1_000_000
