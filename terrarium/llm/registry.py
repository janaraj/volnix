"""LLM provider registry for the Terrarium framework.

Manages the lifecycle of all registered LLM provider instances, providing
lookup, initialization, and graceful shutdown.
"""

from __future__ import annotations

import logging

from terrarium.llm.config import LLMConfig, LLMProviderEntry

logger = logging.getLogger(__name__)
from terrarium.llm.provider import LLMProvider
from terrarium.llm.secrets import ChainResolver, EnvVarResolver, SecretResolver
from terrarium.llm.types import ProviderInfo


class ProviderRegistry:
    """Registry of named LLM provider instances."""

    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, name: str, provider: LLMProvider) -> None:
        """Register a provider instance under a given name.

        Args:
            name: The unique name for this provider.
            provider: The provider instance to register.
        """
        self._providers[name] = provider

    def get(self, name: str) -> LLMProvider:
        """Retrieve a registered provider by name.

        Args:
            name: The provider name.

        Returns:
            The :class:`LLMProvider` instance.

        Raises:
            KeyError: If no provider is registered under *name*.
        """
        if name not in self._providers:
            raise KeyError(f"No provider registered under name '{name}'")
        return self._providers[name]

    def list_providers(self) -> list[ProviderInfo]:
        """Return metadata for all registered providers.

        Returns:
            A list of :class:`ProviderInfo` objects.
        """
        return [provider.get_info() for provider in self._providers.values()]

    async def initialize_all(
        self,
        config: LLMConfig,
        secret_resolver: SecretResolver | None = None,
    ) -> None:
        """Initialize all providers from the given configuration.

        Instantiates each provider defined in *config* using the appropriate
        factory method, resolving API keys through the *secret_resolver*.

        Args:
            config: The LLM configuration containing provider definitions.
            secret_resolver: Optional resolver for API keys.  Defaults to
                :class:`EnvVarResolver`.
        """
        # Clean up existing providers before re-initializing
        if self._providers:
            await self.shutdown_all()
        resolver = secret_resolver or EnvVarResolver()
        for name, entry in config.providers.items():
            # Skip providers whose required API key is not available
            if entry.api_key_ref and not resolver.resolve(entry.api_key_ref):
                logger.debug(
                    "Skipping provider '%s': %s not set", name, entry.api_key_ref,
                )
                continue
            try:
                provider = self._create_provider(name, entry, resolver)
                self.register(name, provider)
            except Exception as exc:
                logger.warning(
                    "Failed to initialize provider '%s': %s (skipping)", name, exc,
                )

    def _create_provider(
        self,
        name: str,
        entry: LLMProviderEntry,
        resolver: SecretResolver,
    ) -> LLMProvider:
        """Instantiate a provider from its configuration entry.

        Args:
            name: The provider name.
            entry: The provider configuration.
            resolver: Secret resolver for API keys.

        Returns:
            An initialized :class:`LLMProvider` instance.

        Raises:
            ValueError: If the provider type is unknown.
        """
        api_key = resolver.resolve(entry.api_key_ref) if entry.api_key_ref else None

        if entry.type == "anthropic":
            from terrarium.llm.providers.anthropic import AnthropicProvider

            return AnthropicProvider(
                api_key=api_key or "",
                default_model=entry.default_model or "claude-sonnet-4-6",
                timeout=entry.timeout_seconds,
            )
        elif entry.type == "openai_compatible":
            from terrarium.llm.providers.openai_compat import OpenAICompatibleProvider

            return OpenAICompatibleProvider(
                api_key=api_key,
                base_url=entry.base_url or "",
                default_model=entry.default_model or "gpt-5.4-mini",
                timeout=entry.timeout_seconds,
            )
        elif entry.type == "google":
            from terrarium.llm.providers.google import GoogleNativeProvider

            return GoogleNativeProvider(
                api_key=api_key or "",
                default_model=entry.default_model or "gemini-3-flash-preview",
                timeout=entry.timeout_seconds,
            )
        elif entry.type == "acp":
            from terrarium.llm.providers.acp_client import ACPClientProvider

            return ACPClientProvider(
                command=entry.command,
                args=entry.args or [],
                auth_method=entry.auth_method,
                timeout=entry.timeout_seconds,
            )
        elif entry.type == "cli":
            from terrarium.llm.providers.cli_subprocess import CLISubprocessProvider

            return CLISubprocessProvider(
                command=entry.command,
                args=entry.args,
                default_model=entry.default_model,
                timeout=entry.timeout_seconds,
            )
        elif entry.type == "mock":
            from terrarium.llm.providers.mock import MockLLMProvider

            return MockLLMProvider()
        else:
            valid_types = ["anthropic", "openai_compatible", "google", "acp", "cli", "mock"]
            raise ValueError(
                f"Unknown provider type: '{entry.type}'. Valid types: {valid_types}"
            )

    async def shutdown_all(self) -> None:
        """Gracefully shut down all registered providers.

        Calls ``close()`` on each provider that supports it, then clears
        the internal registry.
        """
        for name, provider in self._providers.items():
            if hasattr(provider, 'close') and callable(provider.close):
                try:
                    await provider.close()
                except Exception:
                    pass  # best-effort cleanup
        self._providers.clear()
