"""Anthropic LLM provider for the Terrarium framework.

Implements the :class:`~terrarium.llm.provider.LLMProvider` interface
using the Anthropic Messages API.
"""

from __future__ import annotations

import json
import logging
import time
from typing import ClassVar

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

from terrarium.llm.provider import LLMProvider
from terrarium.llm.types import LLMRequest, LLMResponse, LLMUsage, ProviderInfo, ToolCall


class AnthropicProvider(LLMProvider):
    """LLM provider backed by the Anthropic Messages API."""

    provider_name: ClassVar[str] = "anthropic"

    def __init__(self, api_key: str, default_model: str = "claude-sonnet-4-6", timeout: float = 300.0) -> None:
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

            create_kwargs: dict = dict(
                model=model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                system=system_param,
                messages=[{"role": "user", "content": request.user_content}],
            )
            # Structured output: force valid JSON matching the schema.
            # Uses output_config with json_schema format.
            if request.output_schema:
                create_kwargs["output_config"] = {
                    "format": {
                        "type": "json_schema",
                        "schema": request.output_schema,
                    }
                }
                schema_type = request.output_schema.get("type", "?")
                logger.info("Anthropic structured output enabled (schema type=%s)", schema_type)

            if request.tools:
                create_kwargs["tools"] = [
                    {
                        "name": t.name,
                        "description": t.description,
                        "input_schema": t.parameters,
                    }
                    for t in request.tools
                ]
                create_kwargs["tool_choice"] = {"type": "any"}

            message = await self._client.messages.create(**create_kwargs)
            latency = (time.monotonic() - start) * 1000

            # Parse text and tool_use blocks from the response content.
            content = ""
            parsed_tool_calls: list[ToolCall] | None = None
            for block in message.content:
                if hasattr(block, "text"):
                    content = block.text
                elif hasattr(block, "type") and block.type == "tool_use":
                    if parsed_tool_calls is None:
                        parsed_tool_calls = []
                    parsed_tool_calls.append(
                        ToolCall(name=block.name, arguments=block.input)
                    )
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
                    logger.info("Anthropic structured output parsed: %d items, %d chars", items, len(content))
                except json.JSONDecodeError:
                    logger.warning("Anthropic structured output was not valid JSON (%d chars)", len(content))

            return LLMResponse(
                content=content,
                structured_output=parsed_structured,
                tool_calls=parsed_tool_calls,
                usage=usage,
                model=model,
                provider="anthropic",
                latency_ms=latency,
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
