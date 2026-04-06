"""Tests for volnix.engines.animator.generator -- OrganicGenerator.

Covers: budget enforcement, LLM failure handling, event parsing.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from volnix.engines.animator.config import AnimatorConfig
from volnix.engines.animator.context import AnimatorContext
from volnix.engines.animator.generator import OrganicGenerator
from volnix.engines.world_compiler.plan import WorldPlan
from volnix.llm.types import LLMResponse


def _utc():
    return datetime(2026, 3, 22, 12, 0, 0, tzinfo=UTC)


def _make_context() -> AnimatorContext:
    """Create a minimal AnimatorContext for testing."""
    plan = WorldPlan(
        name="test-world",
        description="A test world",
        behavior="dynamic",
    )
    return AnimatorContext(plan)


def _make_config(**overrides) -> AnimatorConfig:
    """Create an AnimatorConfig for testing."""
    return AnimatorConfig(**overrides)


# ---------------------------------------------------------------------------
# Budget enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_zero_budget_returns_empty():
    """Zero budget -> returns [] without calling LLM."""
    mock_router = AsyncMock()
    gen = OrganicGenerator(
        llm_router=mock_router,
        context=_make_context(),
        config=_make_config(),
    )

    result = await gen.generate(_utc(), budget=0)
    assert result == []
    mock_router.route.assert_not_called()


@pytest.mark.asyncio
async def test_generate_respects_budget_limit():
    """Generator caps returned events at budget."""
    mock_router = AsyncMock()
    # LLM returns 5 events
    events = [
        {
            "actor_id": f"npc{i}",
            "service_id": "world",
            "action": f"a{i}",
            "input_data": {},
            "sub_type": "organic",
        }
        for i in range(5)
    ]
    mock_router.route = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(events),
            provider="mock",
            model="mock",
            latency_ms=0,
        )
    )

    gen = OrganicGenerator(
        llm_router=mock_router,
        context=_make_context(),
        config=_make_config(),
    )

    result = await gen.generate(_utc(), budget=2)
    assert len(result) <= 2


# ---------------------------------------------------------------------------
# LLM failure handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_llm_failure_returns_empty():
    """If LLM call fails, returns [] (not crash)."""
    mock_router = AsyncMock()
    mock_router.route = AsyncMock(side_effect=Exception("LLM down"))

    gen = OrganicGenerator(
        llm_router=mock_router,
        context=_make_context(),
        config=_make_config(),
    )

    result = await gen.generate(_utc(), budget=3)
    assert result == []


# ---------------------------------------------------------------------------
# Correct event parsing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_parses_json_array():
    """Generator correctly parses a JSON array response from LLM."""
    mock_router = AsyncMock()
    events = [
        {
            "actor_id": "npc1",
            "service_id": "gmail",
            "action": "send_msg",
            "input_data": {"to": "agent@test.com"},
            "sub_type": "organic",
        },
        {
            "actor_id": "npc2",
            "service_id": "world",
            "action": "status_update",
            "input_data": {},
            "sub_type": "organic",
        },
    ]
    mock_router.route = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(events),
            provider="mock",
            model="mock",
            latency_ms=0,
        )
    )

    gen = OrganicGenerator(
        llm_router=mock_router,
        context=_make_context(),
        config=_make_config(),
    )

    result = await gen.generate(_utc(), budget=5)
    assert len(result) == 2
    assert result[0]["actor_id"] == "npc1"
    assert result[1]["action"] == "status_update"


@pytest.mark.asyncio
async def test_generate_handles_single_object_response():
    """Generator handles LLM returning a single object instead of array."""
    mock_router = AsyncMock()
    event = {
        "actor_id": "npc1",
        "service_id": "world",
        "action": "single_event",
        "input_data": {},
        "sub_type": "organic",
    }
    mock_router.route = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(event),
            provider="mock",
            model="mock",
            latency_ms=0,
        )
    )

    gen = OrganicGenerator(
        llm_router=mock_router,
        context=_make_context(),
        config=_make_config(),
    )

    result = await gen.generate(_utc(), budget=3)
    assert len(result) == 1
    assert result[0]["action"] == "single_event"


@pytest.mark.asyncio
async def test_generate_with_recent_actions():
    """Generator passes recent_actions to the template."""
    mock_router = AsyncMock()
    mock_router.route = AsyncMock(
        return_value=LLMResponse(
            content="[]",
            provider="mock",
            model="mock",
            latency_ms=0,
        )
    )

    gen = OrganicGenerator(
        llm_router=mock_router,
        context=_make_context(),
        config=_make_config(),
    )

    recent = [{"action": "email_send", "actor_id": "agent-1"}]
    result = await gen.generate(_utc(), budget=2, recent_actions=recent)
    assert result == []
    # Verify LLM was called (template rendered with recent_actions)
    mock_router.route.assert_called_once()
