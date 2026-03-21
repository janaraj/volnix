"""Anthropic LLM provider for the Terrarium framework.

Implements the :class:`~terrarium.llm.provider.LLMProvider` interface
using the Anthropic Messages API.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.llm.provider import LLMProvider
from terrarium.llm.types import LLMRequest, LLMResponse, ProviderInfo


class AnthropicProvider(LLMProvider):
    """LLM provider backed by the Anthropic Messages API."""

    provider_name: ClassVar[str] = "anthropic"

    def __init__(self, api_key: str, default_model: str = "claude-sonnet-4-20250514") -> None:
        ...

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Send a request to the Anthropic API.

        Args:
            request: The LLM request payload.

        Returns:
            The LLM response.
        """
        ...

    async def validate_connection(self) -> bool:
        """Validate connectivity to the Anthropic API.

        Returns:
            ``True`` if reachable with valid credentials.
        """
        ...

    async def list_models(self) -> list[str]:
        """List available Anthropic models.

        Returns:
            A list of model identifier strings.
        """
        ...

    def get_info(self) -> ProviderInfo:
        """Return provider metadata.

        Returns:
            A :class:`ProviderInfo` describing this Anthropic provider.
        """
        ...
