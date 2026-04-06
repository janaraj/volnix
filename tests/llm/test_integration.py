"""Integration tests for the LLM module -- full cycle with mock provider + real ledger."""

import pytest

from volnix.llm.config import LLMConfig, LLMProviderEntry, LLMRoutingEntry
from volnix.llm.providers.mock import MockLLMProvider
from volnix.llm.registry import ProviderRegistry
from volnix.llm.router import LLMRouter
from volnix.llm.secrets import ChainResolver, EnvVarResolver, FileResolver
from volnix.llm.tracker import UsageTracker
from volnix.llm.types import LLMRequest, ProviderType


@pytest.mark.asyncio
async def test_full_cycle_mock_provider():
    """Full route -> generate -> track cycle with mock provider."""
    config = LLMConfig(
        defaults=LLMProviderEntry(type="mock", default_model="mock-model-1"),
        providers={"mock": LLMProviderEntry(type="mock")},
        routing={
            "responder": LLMRoutingEntry(provider="mock", model="mock-model-1"),
        },
    )
    registry = ProviderRegistry()
    await registry.initialize_all(config)
    tracker = UsageTracker()
    router = LLMRouter(config=config, registry=registry, tracker=tracker)

    req = LLMRequest(user_content="Describe a sunset", system_prompt="Be poetic")
    resp = await router.route(req, engine_name="responder")

    assert resp.content
    assert resp.provider == "mock"
    assert resp.usage.total_tokens > 0

    engine_usage = await tracker.get_usage_by_engine("responder")
    assert engine_usage.total_tokens == resp.usage.total_tokens


@pytest.mark.asyncio
async def test_multiple_engines_tracked_separately():
    """Usage for different engines is tracked independently."""
    config = LLMConfig(
        defaults=LLMProviderEntry(type="mock", default_model="mock-model-1"),
        providers={"mock": LLMProviderEntry(type="mock")},
        routing={
            "responder": LLMRoutingEntry(provider="mock", model="mock-model-1"),
            "animator": LLMRoutingEntry(provider="mock", model="mock-model-2"),
        },
    )
    registry = ProviderRegistry()
    await registry.initialize_all(config)
    tracker = UsageTracker()
    router = LLMRouter(config=config, registry=registry, tracker=tracker)

    await router.route(LLMRequest(user_content="hello"), engine_name="responder")
    await router.route(LLMRequest(user_content="world"), engine_name="animator")
    await router.route(LLMRequest(user_content="again"), engine_name="responder")

    responder_usage = await tracker.get_usage_by_engine("responder")
    animator_usage = await tracker.get_usage_by_engine("animator")
    total = await tracker.get_total_usage()

    assert responder_usage.total_tokens > 0
    assert animator_usage.total_tokens > 0
    assert total.total_tokens == responder_usage.total_tokens + animator_usage.total_tokens


@pytest.mark.asyncio
async def test_registry_initialize_and_shutdown():
    """Full init -> use -> shutdown cycle."""
    config = LLMConfig(
        providers={
            "mock": LLMProviderEntry(type="mock"),
        }
    )
    registry = ProviderRegistry()
    await registry.initialize_all(config)

    provider = registry.get("mock")
    assert isinstance(provider, MockLLMProvider)

    infos = registry.list_providers()
    assert len(infos) == 1

    await registry.shutdown_all()
    assert len(registry.list_providers()) == 0


@pytest.mark.asyncio
async def test_secret_resolution_chain(monkeypatch, tmp_path):
    """ChainResolver integrates with registry initialization."""
    monkeypatch.delenv("MY_MOCK_KEY", raising=False)
    secret_file = tmp_path / "MY_MOCK_KEY"
    secret_file.write_text("file-key-value")

    resolver = ChainResolver(
        [
            EnvVarResolver(),
            FileResolver(secrets_dir=str(tmp_path)),
        ]
    )
    assert resolver.resolve("MY_MOCK_KEY") == "file-key-value"

    config = LLMConfig(
        providers={
            "mock": LLMProviderEntry(type="mock"),
        }
    )
    registry = ProviderRegistry()
    await registry.initialize_all(config, secret_resolver=resolver)
    assert isinstance(registry.get("mock"), MockLLMProvider)


def test_provider_type_enum():
    """ProviderType enum has all expected values."""
    assert ProviderType.API == "api"
    assert ProviderType.ACP == "acp"
    assert ProviderType.CLI == "cli"
    assert ProviderType.MOCK == "mock"
    assert len(ProviderType) == 4
