"""Tests for volnix.llm.tracker -- LLM usage tracking and cost accounting."""

from unittest.mock import AsyncMock

import pytest

from volnix.core.types import ActorId
from volnix.llm.tracker import UsageTracker
from volnix.llm.types import LLMRequest, LLMResponse, LLMUsage


def _make_response(
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    cost_usd: float = 0.001,
    provider: str = "mock",
    model: str = "mock-model-1",
) -> LLMResponse:
    """Helper to create a mock response with usage data."""
    return LLMResponse(
        content="test response",
        usage=LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=cost_usd,
        ),
        model=model,
        provider=provider,
        latency_ms=10.0,
    )


@pytest.mark.asyncio
async def test_tracker_record_to_ledger():
    """Record appends an LLMCallEntry to the ledger."""
    mock_ledger = AsyncMock()
    mock_ledger.append = AsyncMock(return_value=1)
    tracker = UsageTracker(ledger=mock_ledger)
    req = LLMRequest(user_content="hello")
    resp = _make_response()
    await tracker.record(req, resp, "test_engine")
    mock_ledger.append.assert_awaited_once()
    entry = mock_ledger.append.call_args[0][0]
    assert entry.entry_type == "llm_call"
    assert entry.provider == "mock"
    assert entry.engine_name == "test_engine"


@pytest.mark.asyncio
async def test_tracker_usage_by_actor():
    """Usage is tracked per actor when actor_id is provided."""
    tracker = UsageTracker()
    req = LLMRequest(user_content="hello")
    actor = ActorId("agent-1")
    await tracker.record(req, _make_response(cost_usd=0.01), "engine", actor_id=actor)
    await tracker.record(req, _make_response(cost_usd=0.02), "engine", actor_id=actor)
    usage = await tracker.get_usage_by_actor(actor)
    assert usage.prompt_tokens == 200
    assert usage.cost_usd == pytest.approx(0.03)


@pytest.mark.asyncio
async def test_tracker_usage_by_engine():
    """Usage is aggregated per engine."""
    tracker = UsageTracker()
    req = LLMRequest(user_content="hello")
    await tracker.record(req, _make_response(prompt_tokens=50), "responder")
    await tracker.record(req, _make_response(prompt_tokens=75), "responder")
    usage = await tracker.get_usage_by_engine("responder")
    assert usage.prompt_tokens == 125


@pytest.mark.asyncio
async def test_tracker_total_usage():
    """Total usage sums all records."""
    tracker = UsageTracker()
    req = LLMRequest(user_content="hello")
    await tracker.record(req, _make_response(prompt_tokens=10, completion_tokens=5), "e1")
    await tracker.record(req, _make_response(prompt_tokens=20, completion_tokens=10), "e2")
    total = await tracker.get_total_usage()
    assert total.prompt_tokens == 30
    assert total.completion_tokens == 15
    assert total.total_tokens == 45


@pytest.mark.asyncio
async def test_tracker_cost_by_actor():
    """get_cost_by_actor returns total USD cost for the actor."""
    tracker = UsageTracker()
    req = LLMRequest(user_content="hello")
    actor = ActorId("agent-2")
    await tracker.record(req, _make_response(cost_usd=0.05), "e1", actor_id=actor)
    await tracker.record(req, _make_response(cost_usd=0.15), "e2", actor_id=actor)
    cost = await tracker.get_cost_by_actor(actor)
    assert cost == pytest.approx(0.20)


@pytest.mark.asyncio
async def test_tracker_without_ledger():
    """Tracker works without a ledger -- no errors, still tracks in memory."""
    tracker = UsageTracker(ledger=None)
    req = LLMRequest(user_content="hello")
    await tracker.record(req, _make_response(), "engine_x")
    usage = await tracker.get_usage_by_engine("engine_x")
    assert usage.total_tokens > 0
    # No ledger interaction, but no exceptions either
