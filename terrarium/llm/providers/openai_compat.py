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

from typing import ClassVar

from terrarium.llm.provider import LLMProvider
from terrarium.llm.types import LLMRequest, LLMResponse, ProviderInfo


class OpenAICompatibleProvider(LLMProvider):
    """LLM provider for any OpenAI-compatible Chat Completions API."""

    provider_name: ClassVar[str] = "openai_compatible"

    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        default_model: str = "gpt-4o",
    ) -> None:
        ...

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Send a request to the OpenAI-compatible endpoint.

        Args:
            request: The LLM request payload.

        Returns:
            The LLM response.
        """
        ...

    async def validate_connection(self) -> bool:
        """Validate connectivity to the OpenAI-compatible endpoint.

        Returns:
            ``True`` if reachable with valid credentials.
        """
        ...

    async def list_models(self) -> list[str]:
        """List available models from the endpoint.

        Returns:
            A list of model identifier strings.
        """
        ...

    def get_info(self) -> ProviderInfo:
        """Return provider metadata.

        Returns:
            A :class:`ProviderInfo` describing this provider instance.
        """
        ...
