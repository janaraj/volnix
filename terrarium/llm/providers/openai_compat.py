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

import time
from typing import ClassVar

import openai
from openai import AsyncOpenAI

from terrarium.llm.provider import LLMProvider
from terrarium.llm.types import LLMRequest, LLMResponse, LLMUsage, ProviderInfo


class OpenAICompatibleProvider(LLMProvider):
    """LLM provider for any OpenAI-compatible Chat Completions API."""

    provider_name: ClassVar[str] = "openai_compatible"

    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        default_model: str = "gpt-5.4-mini",
    ) -> None:
        # OpenAI SDK requires a non-empty api_key string.
        # For local endpoints (Ollama, vLLM) that don't need auth,
        # we use a placeholder that satisfies the SDK's validation.
        self._client = AsyncOpenAI(
            api_key=api_key if api_key else "local-no-auth-needed",
            base_url=base_url,
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

            # Newer OpenAI models (gpt-5.x, o-series) use max_completion_tokens
            # instead of max_tokens. Try the new parameter first, fall back to old.
            try:
                response = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,  # type: ignore[arg-type]
                    max_completion_tokens=request.max_tokens,
                    temperature=request.temperature,
                )
            except (openai.BadRequestError, TypeError, KeyError):
                response = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,  # type: ignore[arg-type]
                    max_tokens=request.max_tokens,
                    temperature=request.temperature,
                )
            latency = (time.monotonic() - start) * 1000
            content = response.choices[0].message.content if response.choices else ""
            usage_data = response.usage
            usage = LLMUsage(
                prompt_tokens=usage_data.prompt_tokens if usage_data else 0,
                completion_tokens=usage_data.completion_tokens if usage_data else 0,
                total_tokens=usage_data.total_tokens if usage_data else 0,
            )
            return LLMResponse(
                content=content or "",
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
