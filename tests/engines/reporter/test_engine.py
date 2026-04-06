"""Tests for ReportGeneratorEngine -- orchestrator."""

from unittest.mock import AsyncMock

import pytest

from tests.engines.reporter.conftest import (
    make_capability_gap,
    make_permission_denied,
    make_world_event,
)
from volnix.core.types import EventId
from volnix.engines.reporter.engine import ReportGeneratorEngine


@pytest.fixture
async def engine():
    """Create and initialize a ReportGeneratorEngine with mock deps."""
    eng = ReportGeneratorEngine()

    # Mock state engine
    mock_state = AsyncMock()
    mock_state.get_timeline = AsyncMock(return_value=[])
    mock_state.get_causal_chain = AsyncMock(return_value=[])

    eng._dependencies = {"state": mock_state}
    eng._config = {}

    # Initialize sub-components
    await eng._on_initialize()
    return eng


@pytest.mark.asyncio
async def test_generate_full_report_returns_all_sections(engine):
    """Full report should contain scorecard, gap_log, gap_summary, condition_report."""
    report = await engine.generate_full_report()

    assert "scorecard" in report
    assert "gap_log" in report
    assert "gap_summary" in report
    assert "condition_report" in report


@pytest.mark.asyncio
async def test_generate_scorecard_returns_per_actor_collective(engine):
    """Scorecard should have per_actor and collective keys."""
    scorecard = await engine.generate_scorecard()

    assert "per_actor" in scorecard
    assert "collective" in scorecard


@pytest.mark.asyncio
async def test_generate_gap_log_returns_list(engine):
    """Gap log should return a list."""
    gaps = await engine.generate_gap_log()
    assert isinstance(gaps, list)


@pytest.mark.asyncio
async def test_generate_causal_trace_with_mock_state(engine):
    """Causal trace should delegate to renderer and return dict."""
    trace = await engine.generate_causal_trace(EventId("test-event"))
    assert "root_event" in trace
    assert trace["root_event"] == "test-event"


@pytest.mark.asyncio
async def test_generate_condition_report_returns_both_directions(engine):
    """Condition report should have world_to_agent and agent_to_world."""
    report = await engine.generate_condition_report()

    assert "world_to_agent" in report
    assert "agent_to_world" in report


@pytest.mark.asyncio
async def test_generate_with_events(engine):
    """Engine should produce scorecard with actual events in timeline."""
    events = [
        make_world_event(actor_id="agent-1", tick=1),
        make_permission_denied(actor_id="agent-1", tick=2),
        make_capability_gap(actor_id="agent-1", tool="missing_tool", tick=3),
    ]
    engine._dependencies["state"].get_timeline = AsyncMock(return_value=events)

    # Set up actors
    engine._config["_actor_registry"] = None  # Will use fallback empty list

    scorecard = await engine.generate_scorecard()
    assert "per_actor" in scorecard

    gaps = await engine.generate_gap_log()
    assert len(gaps) == 1
    assert gaps[0]["tool"] == "missing_tool"
