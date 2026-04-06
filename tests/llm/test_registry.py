"""Tests for volnix.llm.registry -- provider registration and lookup."""

import pytest

from volnix.llm.config import LLMConfig, LLMProviderEntry
from volnix.llm.providers.mock import MockLLMProvider
from volnix.llm.registry import ProviderRegistry
from volnix.llm.types import ProviderInfo


def test_registry_register_provider():
    """Registering a provider stores it under the given name."""
    registry = ProviderRegistry()
    mock = MockLLMProvider()
    registry.register("mock", mock)
    assert registry.get("mock") is mock


def test_registry_get_missing_raises():
    """Getting a non-existent provider raises KeyError."""
    registry = ProviderRegistry()
    with pytest.raises(KeyError, match="no_such_provider"):
        registry.get("no_such_provider")


def test_registry_list_providers():
    """list_providers returns ProviderInfo for all registered providers."""
    registry = ProviderRegistry()
    registry.register("mock1", MockLLMProvider())
    registry.register("mock2", MockLLMProvider())
    infos = registry.list_providers()
    assert len(infos) == 2
    assert all(isinstance(i, ProviderInfo) for i in infos)


@pytest.mark.asyncio
async def test_registry_initialize_from_config(monkeypatch):
    """initialize_all creates providers from config entries."""
    monkeypatch.setenv("MOCK_API_KEY", "test-key")
    config = LLMConfig(
        providers={
            "test_mock": LLMProviderEntry(type="mock"),
        }
    )
    registry = ProviderRegistry()
    await registry.initialize_all(config)
    provider = registry.get("test_mock")
    assert isinstance(provider, MockLLMProvider)


@pytest.mark.asyncio
async def test_registry_factory_types(monkeypatch):
    """Factory creates correct provider types for each config type."""
    monkeypatch.setenv("TEST_KEY", "sk-test")
    config = LLMConfig(
        providers={
            "p_anthropic": LLMProviderEntry(type="anthropic", api_key_ref="TEST_KEY"),
            "p_openai": LLMProviderEntry(
                type="openai_compatible",
                api_key_ref="TEST_KEY",
                base_url="http://localhost/v1",
            ),
            "p_google": LLMProviderEntry(type="google", api_key_ref="TEST_KEY"),
            "p_mock": LLMProviderEntry(type="mock"),
            "p_acp": LLMProviderEntry(
                type="acp", command="codex-acp", auth_method="openai-api-key"
            ),
            "p_cli": LLMProviderEntry(type="cli", command="echo"),
        }
    )
    registry = ProviderRegistry()
    await registry.initialize_all(config)

    from volnix.llm.providers.acp_client import ACPClientProvider
    from volnix.llm.providers.anthropic import AnthropicProvider
    from volnix.llm.providers.cli_subprocess import CLISubprocessProvider
    from volnix.llm.providers.google import GoogleNativeProvider
    from volnix.llm.providers.openai_compat import OpenAICompatibleProvider

    assert isinstance(registry.get("p_anthropic"), AnthropicProvider)
    assert isinstance(registry.get("p_openai"), OpenAICompatibleProvider)
    assert isinstance(registry.get("p_google"), GoogleNativeProvider)
    assert isinstance(registry.get("p_mock"), MockLLMProvider)
    assert isinstance(registry.get("p_acp"), ACPClientProvider)
    assert isinstance(registry.get("p_cli"), CLISubprocessProvider)


@pytest.mark.asyncio
async def test_registry_shutdown_clears():
    """shutdown_all clears the registry."""
    registry = ProviderRegistry()
    registry.register("mock", MockLLMProvider())
    assert len(registry.list_providers()) == 1
    await registry.shutdown_all()
    assert len(registry.list_providers()) == 0
