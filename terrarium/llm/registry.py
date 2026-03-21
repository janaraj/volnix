"""LLM provider registry for the Terrarium framework.

Manages the lifecycle of all registered LLM provider instances, providing
lookup, initialization, and graceful shutdown.
"""

from __future__ import annotations

from terrarium.llm.config import LLMConfig
from terrarium.llm.provider import LLMProvider
from terrarium.llm.types import ProviderInfo


class ProviderRegistry:
    """Registry of named LLM provider instances."""

    def __init__(self) -> None:
        ...

    def register(self, name: str, provider: LLMProvider) -> None:
        """Register a provider instance under a given name.

        Args:
            name: The unique name for this provider.
            provider: The provider instance to register.
        """
        ...

    def get(self, name: str) -> LLMProvider:
        """Retrieve a registered provider by name.

        Args:
            name: The provider name.

        Returns:
            The :class:`LLMProvider` instance.

        Raises:
            KeyError: If no provider is registered under *name*.
        """
        ...

    def list_providers(self) -> list[ProviderInfo]:
        """Return metadata for all registered providers.

        Returns:
            A list of :class:`ProviderInfo` objects.
        """
        ...

    async def initialize_all(self, config: LLMConfig) -> None:
        """Initialize all providers from the given configuration.

        Instantiates and validates each provider defined in *config*.

        Args:
            config: The LLM configuration containing provider definitions.
        """
        ...

    async def shutdown_all(self) -> None:
        """Gracefully shut down all registered providers."""
        ...
