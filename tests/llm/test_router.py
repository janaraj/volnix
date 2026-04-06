"""Tests for volnix.llm.router -- model routing per engine and default fallback."""

import time

import pytest

from volnix.llm.config import LLMConfig, LLMProviderEntry, LLMRoutingEntry
from volnix.llm.provider import LLMProvider
from volnix.llm.providers.mock import MockLLMProvider
from volnix.llm.registry import ProviderRegistry
from volnix.llm.router import LLMRouter
from volnix.llm.tracker import UsageTracker
from volnix.llm.types import LLMRequest, LLMResponse, ProviderInfo


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


# ── Retry tests ─────────────────────────────────────────────


class _FailThenSucceedProvider(LLMProvider):
    """Provider that fails N times, then succeeds."""

    provider_name = "fail_then_succeed"

    def __init__(self, fail_responses: list[LLMResponse], success_response: LLMResponse):
        self._fail_responses = list(fail_responses)
        self._success = success_response
        self.call_count = 0

    def info(self) -> ProviderInfo:
        return ProviderInfo(name="fail_then_succeed", default_model="test")

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.call_count += 1
        if self._fail_responses:
            return self._fail_responses.pop(0)
        return self._success


def _empty_response() -> LLMResponse:
    return LLMResponse(content="", provider="test", model="test")


def _error_response(error: str) -> LLMResponse:
    return LLMResponse(content="", provider="test", model="test", error=error)


def _success_response(content: str = "ok") -> LLMResponse:
    return LLMResponse(content=content, provider="test", model="test")


def _make_retry_router(
    provider: LLMProvider,
    max_retries: int = 3,
    backoff_base: float = 0.01,  # tiny backoff for fast tests
) -> LLMRouter:
    config = LLMConfig(
        defaults=LLMProviderEntry(type="fail_then_succeed", default_model="test"),
        providers={},
        routing={},
        max_retries=max_retries,
        retry_backoff_base=backoff_base,
    )
    registry = ProviderRegistry()
    registry.register("fail_then_succeed", provider)
    return LLMRouter(config=config, registry=registry)


@pytest.mark.asyncio
async def test_retry_on_empty_response():
    """Empty response (no content, no error) triggers retry."""
    provider = _FailThenSucceedProvider(
        fail_responses=[_empty_response(), _empty_response()],
        success_response=_success_response("hello"),
    )
    router = _make_retry_router(provider)
    resp = await router.route(LLMRequest(user_content="test"), engine_name="test")
    assert resp.content == "hello"
    assert provider.call_count == 3  # 2 failures + 1 success


@pytest.mark.asyncio
async def test_retry_on_transient_error():
    """Transient errors (timeout, rate limit, 5xx) trigger retry."""
    provider = _FailThenSucceedProvider(
        fail_responses=[_error_response("rate limit exceeded (429)")],
        success_response=_success_response("recovered"),
    )
    router = _make_retry_router(provider)
    resp = await router.route(LLMRequest(user_content="test"), engine_name="test")
    assert resp.content == "recovered"
    assert provider.call_count == 2


@pytest.mark.asyncio
async def test_no_retry_on_success():
    """Successful response is not retried."""
    provider = _FailThenSucceedProvider(
        fail_responses=[],
        success_response=_success_response("first try"),
    )
    router = _make_retry_router(provider)
    resp = await router.route(LLMRequest(user_content="test"), engine_name="test")
    assert resp.content == "first try"
    assert provider.call_count == 1


@pytest.mark.asyncio
async def test_no_retry_on_non_transient_error():
    """Non-transient errors (auth, invalid request) are not retried."""
    provider = _FailThenSucceedProvider(
        fail_responses=[_error_response("authentication failed: invalid API key")],
        success_response=_success_response("never reached"),
    )
    router = _make_retry_router(provider)
    resp = await router.route(LLMRequest(user_content="test"), engine_name="test")
    assert resp.error == "authentication failed: invalid API key"
    assert provider.call_count == 1


@pytest.mark.asyncio
async def test_max_retries_exhausted():
    """Returns last response when max retries are exhausted."""
    provider = _FailThenSucceedProvider(
        fail_responses=[_empty_response()] * 10,  # more than max_retries
        success_response=_success_response("never reached"),
    )
    router = _make_retry_router(provider, max_retries=2)
    resp = await router.route(LLMRequest(user_content="test"), engine_name="test")
    assert resp.content == ""  # last empty response
    assert provider.call_count == 3  # 1 initial + 2 retries


@pytest.mark.asyncio
async def test_retry_backoff_timing():
    """Verify retries have exponential backoff delay."""
    provider = _FailThenSucceedProvider(
        fail_responses=[_empty_response(), _empty_response()],
        success_response=_success_response("ok"),
    )
    router = _make_retry_router(provider, backoff_base=0.05)
    t0 = time.monotonic()
    await router.route(LLMRequest(user_content="test"), engine_name="test")
    elapsed = time.monotonic() - t0
    # backoff: 0.05 * 2^0 + 0.05 * 2^1 = 0.05 + 0.10 = 0.15s minimum
    assert elapsed >= 0.1  # some tolerance


@pytest.mark.asyncio
async def test_retry_on_timeout_error():
    """Timeout errors are retried."""
    provider = _FailThenSucceedProvider(
        fail_responses=[_error_response("LLM call timed out after 30s")],
        success_response=_success_response("recovered"),
    )
    router = _make_retry_router(provider)
    resp = await router.route(LLMRequest(user_content="test"), engine_name="test")
    assert resp.content == "recovered"
    assert provider.call_count == 2


@pytest.mark.asyncio
async def test_retry_on_server_error():
    """Server errors (500, 502, 503) are retried."""
    for code in ["500", "502", "503", "504"]:
        provider = _FailThenSucceedProvider(
            fail_responses=[_error_response(f"Server error: {code}")],
            success_response=_success_response("ok"),
        )
        router = _make_retry_router(provider)
        resp = await router.route(LLMRequest(user_content="test"), engine_name="test")
        assert resp.content == "ok", f"Failed for {code}"
