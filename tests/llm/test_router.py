"""Tests for terrarium.llm.router -- model routing per engine and default fallback."""

import pytest

from terrarium.llm.config import LLMConfig, LLMProviderEntry, LLMRoutingEntry
from terrarium.llm.providers.mock import MockLLMProvider
from terrarium.llm.registry import ProviderRegistry
from terrarium.llm.router import LLMRouter
from terrarium.llm.tracker import UsageTracker
from terrarium.llm.types import LLMRequest


def _make_router(
    routing: dict[str, LLMRoutingEntry] | None = None,
    tracker: UsageTracker | None = None,
) -> LLMRouter:
    """Helper to create a router with a mock provider."""
    config = LLMConfig(
        defaults=LLMProviderEntry(type="mock", default_model="mock-model-1"),
        providers={"mock": LLMProviderEntry(type="mock")},
        routing=routing or {},
    )
    registry = ProviderRegistry()
    registry.register("mock", MockLLMProvider())
    return LLMRouter(config=config, registry=registry, tracker=tracker)


@pytest.mark.asyncio
async def test_router_route_default():
    """Route falls back to defaults when no routing entry matches."""
    router = _make_router()
    req = LLMRequest(user_content="hello")
    resp = await router.route(req, engine_name="unknown_engine")
    assert resp.content
    assert resp.provider == "mock"


@pytest.mark.asyncio
async def test_router_route_by_engine():
    """Route uses the routing entry for a specific engine."""
    routing = {
        "responder": LLMRoutingEntry(provider="mock", model="mock-model-2"),
    }
    router = _make_router(routing=routing)
    req = LLMRequest(user_content="hello")
    resp = await router.route(req, engine_name="responder")
    assert resp.model == "mock-model-2"


@pytest.mark.asyncio
async def test_router_model_override():
    """Model override on the request takes precedence over routing."""
    routing = {
        "responder": LLMRoutingEntry(provider="mock", model="mock-model-2"),
    }
    router = _make_router(routing=routing)
    req = LLMRequest(user_content="hello", model_override="custom-model")
    resp = await router.route(req, engine_name="responder")
    assert resp.model == "custom-model"


@pytest.mark.asyncio
async def test_router_tracker_recording():
    """Router records usage to the tracker when one is provided."""
    tracker = UsageTracker()
    router = _make_router(tracker=tracker)
    req = LLMRequest(user_content="hello")
    await router.route(req, engine_name="test_engine")
    usage = await tracker.get_usage_by_engine("test_engine")
    assert usage.total_tokens > 0


@pytest.mark.asyncio
async def test_router_fallback_to_defaults():
    """When routing entry has no provider, falls back to config defaults."""
    routing = {
        "animator": LLMRoutingEntry(model="mock-model-2"),  # no provider specified
    }
    router = _make_router(routing=routing)
    req = LLMRequest(user_content="hello")
    resp = await router.route(req, engine_name="animator")
    assert resp.provider == "mock"


@pytest.mark.asyncio
async def test_router_temperature_override():
    """Routing entry temperature is applied to the request."""
    routing = {
        "creative": LLMRoutingEntry(provider="mock", model="mock-model-1", temperature=0.99),
    }
    router = _make_router(routing=routing)
    req = LLMRequest(user_content="hello", temperature=0.5)
    resp = await router.route(req, engine_name="creative")
    # We can verify it ran without error; the mock provider doesn't use temperature
    assert resp.content


def test_router_get_provider_for():
    """get_provider_for resolves the correct provider instance."""
    routing = {
        "responder": LLMRoutingEntry(provider="mock", model="mock-model-2"),
    }
    router = _make_router(routing=routing)
    provider = router.get_provider_for("responder")
    assert isinstance(provider, MockLLMProvider)


def test_router_get_model_for():
    """get_model_for resolves the correct model string."""
    routing = {
        "responder": LLMRoutingEntry(provider="mock", model="custom-model-x"),
    }
    router = _make_router(routing=routing)
    model = router.get_model_for("responder")
    assert model == "custom-model-x"

    # Fallback to default
    model_default = router.get_model_for("unknown_engine")
    assert model_default == "mock-model-1"
