"""OpenAI-compatible LLM provider for the Terrarium framework.

Implements the :class:`~terrarium.llm.provider.LLMProvider` interface using
the OpenAI Chat Completions API format.  Works with any service exposing the
OpenAI-compatible endpoint, including:

- OpenAI
- Google Gemini (via OpenAI-compatible endpoint)
- Together AI
- Groq
- Ollama
- vLLM
"""

from __future__ import annotations

import logging
import time
from typing import Any, ClassVar

import openai
from openai import AsyncOpenAI

from terrarium.llm.provider import LLMProvider
from terrarium.llm.types import LLMRequest, LLMResponse, LLMUsage, ProviderInfo

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(LLMProvider):
    """LLM provider for any OpenAI-compatible Chat Completions API."""

    provider_name: ClassVar[str] = "openai_compatible"

    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        default_model: str = "gpt-5.4-mini",
        timeout: float = 300.0,
    ) -> None:
        # OpenAI SDK requires a non-empty api_key string.
        # For local endpoints (Ollama, vLLM) that don't need auth,
        # we use a placeholder that satisfies the SDK's validation.
        import httpx
        self._client = AsyncOpenAI(
            api_key=api_key if api_key else "local-no-auth-needed",
            base_url=base_url,
            timeout=httpx.Timeout(connect=10.0, read=timeout, write=10.0, pool=10.0),
        )
        self._default_model = default_model
        self._base_url = base_url

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Send a request to the OpenAI-compatible endpoint.

        Args:
            request: The LLM request payload.

        Returns:
            The LLM response.
        """
        model = request.model_override or self._default_model
        start = time.monotonic()
        try:
            messages: list[dict[str, str]] = []
            if request.system_prompt:
                messages.append({"role": "system", "content": request.system_prompt})
            messages.append({"role": "user", "content": request.user_content})

            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": request.temperature,
            }

            # Prompt cache key groups calls sharing the same system prompt prefix.
            # All actors in a simulation share the same world system prompt,
            # so they share cache hits. Different worlds get different keys.
            if request.cache_system_prompt and request.system_prompt:
                import hashlib
                kwargs["prompt_cache_key"] = hashlib.sha256(
                    request.system_prompt.encode()
                ).hexdigest()[:16]

            # Native tool calling: pass tool definitions so the LLM returns
            # structured tool_calls instead of raw JSON text.
            if request.tools:
                kwargs["tools"] = [
                    {
                        "type": "function",
                        "function": {
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.parameters,
                        },
                    }
                    for t in request.tools
                ]
                kwargs["tool_choice"] = "required"

            # Newer OpenAI models (gpt-5.x, o-series) use max_completion_tokens
            # instead of max_tokens. Try the new parameter first, fall back to old.
            kwargs["max_completion_tokens"] = request.max_tokens
            try:
                response = await self._client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
            except (openai.BadRequestError, TypeError, KeyError):
                # Fall back: remove new-style params unsupported by older models/endpoints
                kwargs.pop("max_completion_tokens", None)
                kwargs.pop("prompt_cache_retention", None)
                kwargs["max_tokens"] = request.max_tokens
                response = await self._client.chat.completions.create(**kwargs)  # type: ignore[arg-type]

            latency = (time.monotonic() - start) * 1000
            message = response.choices[0].message if response.choices else None
            content = message.content if message and message.content else ""

            # Parse native tool calls from response
            parsed_tool_calls = None
            if message and message.tool_calls:
                import json as _json
                from terrarium.llm.types import ToolCall
                parsed_tool_calls = []
                for tc in message.tool_calls:
                    try:
                        args = (
                            _json.loads(tc.function.arguments)
                            if isinstance(tc.function.arguments, str)
                            else tc.function.arguments or {}
                        )
                    except _json.JSONDecodeError:
                        args = {}
                    parsed_tool_calls.append(
                        ToolCall(name=tc.function.name, arguments=args)
                    )

            usage_data = response.usage

            # Extract cached token count for observability
            cached_tokens = 0
            if usage_data and hasattr(usage_data, "prompt_tokens_details"):
                details = usage_data.prompt_tokens_details
                if details and hasattr(details, "cached_tokens"):
                    cached_tokens = details.cached_tokens or 0

            usage = LLMUsage(
                prompt_tokens=usage_data.prompt_tokens if usage_data else 0,
                completion_tokens=usage_data.completion_tokens if usage_data else 0,
                total_tokens=usage_data.total_tokens if usage_data else 0,
            )

            if cached_tokens > 0:
                logger.info(
                    "OpenAI cache hit: %d/%d prompt tokens cached",
                    cached_tokens, usage.prompt_tokens,
                )

            return LLMResponse(
                content=content or "",
                tool_calls=parsed_tool_calls,
                usage=usage,
                model=model,
                provider="openai_compatible",
                latency_ms=latency,
            )
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            return LLMResponse(
                content="",
                usage=LLMUsage(),
                model=model,
                provider="openai_compatible",
                latency_ms=latency,
                error=f"{type(e).__name__}: {str(e)[:500]}",
            )

    async def validate_connection(self) -> bool:
        """Validate connectivity to the OpenAI-compatible endpoint.

        Returns:
            ``True`` if reachable with valid credentials.
        """
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False

    async def list_models(self) -> list[str]:
        """List available models from the endpoint.

        Returns:
            A list of model identifier strings.
        """
        try:
            models = await self._client.models.list()
            return [m.id for m in models.data]
        except Exception:
            return [self._default_model]

    def get_info(self) -> ProviderInfo:
        """Return provider metadata.

        Returns:
            A :class:`ProviderInfo` describing this provider instance.
        """
        return ProviderInfo(
            name="openai_compatible",
            type="openai_compatible",
            base_url=self._base_url,
            available_models=[self._default_model],
        )
