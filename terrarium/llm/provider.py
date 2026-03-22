"""Abstract base class for LLM providers.

All concrete providers (Anthropic, OpenAI-compatible, Google, ACP, CLI, mock)
implement this interface so that the router and registry can treat them
uniformly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from terrarium.llm.types import LLMRequest, LLMResponse, ProviderInfo


class LLMProvider(ABC):
    """Abstract base class that all LLM providers must implement."""

    provider_name: ClassVar[str] = ""

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Send a request to the LLM and return the response.

        Args:
            request: The LLM request payload.

        Returns:
            The LLM response including content, usage, and latency.
        """
        ...

    async def validate_connection(self) -> bool:
        """Check that the provider is reachable and credentials are valid.

        Returns:
            ``True`` if the connection is healthy, ``False`` otherwise.
        """
        return True

    async def list_models(self) -> list[str]:
        """List the models available from this provider.

        Returns:
            A list of model identifier strings.
        """
        return []

    def get_info(self) -> ProviderInfo:
        """Return metadata about this provider instance.

        Returns:
            A :class:`ProviderInfo` with provider details.
        """
        return ProviderInfo(name=self.provider_name, type=self.provider_name)
