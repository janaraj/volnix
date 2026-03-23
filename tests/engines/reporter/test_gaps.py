"""Tests for GapAnalyzer -- capability gap classification."""
import pytest

from terrarium.core import GapResponse
from terrarium.engines.reporter.capability_gaps import GapAnalyzer
from tests.engines.reporter.conftest import (
    make_capability_gap,
    make_world_event,
)


@pytest.fixture
def analyzer() -> GapAnalyzer:
    return GapAnalyzer()


@pytest.mark.asyncio
async def test_no_gaps_empty_list(analyzer):
    """No capability gap events → empty list."""
    events = [make_world_event(tick=1)]
    gaps = await analyzer.analyze(events)
    assert gaps == []


@pytest.mark.asyncio
async def test_gap_followed_by_escalation(analyzer):
    """Gap followed by escalation action → ESCALATED."""
    events = [
        make_capability_gap(actor_id="agent-1", tool="fancy_tool", tick=1),
        make_world_event(actor_id="agent-1", action="escalate_to_supervisor", tick=2),
    ]
    gaps = await analyzer.analyze(events)
    assert len(gaps) == 1
    assert gaps[0]["response"] == GapResponse.ESCALATED.value
    assert gaps[0]["tool"] == "fancy_tool"


@pytest.mark.asyncio
async def test_gap_followed_by_alternative_tool(analyzer):
    """Gap followed by world event → ADAPTED."""
    events = [
        make_capability_gap(actor_id="agent-1", tool="fancy_tool", tick=1),
        make_world_event(actor_id="agent-1", action="use_basic_tool", tick=2),
    ]
    gaps = await analyzer.analyze(events)
    assert len(gaps) == 1
    assert gaps[0]["response"] == GapResponse.ADAPTED.value


@pytest.mark.asyncio
async def test_gap_with_no_followup(analyzer):
    """Gap with no following events → SKIPPED."""
    events = [
        make_capability_gap(actor_id="agent-1", tool="fancy_tool", tick=1),
    ]
    gaps = await analyzer.analyze(events)
    assert len(gaps) == 1
    assert gaps[0]["response"] == GapResponse.SKIPPED.value


@pytest.mark.asyncio
async def test_gap_different_actor_skipped(analyzer):
    """Gap followed by events from a different actor → SKIPPED."""
    events = [
        make_capability_gap(actor_id="agent-1", tool="fancy_tool", tick=1),
        make_world_event(actor_id="agent-2", action="some_action", tick=2),
    ]
    gaps = await analyzer.analyze(events)
    assert len(gaps) == 1
    assert gaps[0]["response"] == GapResponse.SKIPPED.value


@pytest.mark.asyncio
async def test_gap_summary_counts(analyzer):
    """Summary should have correct total and by_response counts."""
    events = [
        make_capability_gap(actor_id="agent-1", tool="tool_a", tick=1),
        make_world_event(actor_id="agent-1", action="escalate_supervisor", tick=2),
        make_capability_gap(actor_id="agent-1", tool="tool_b", tick=3),
        # No followup for second gap
    ]
    summary = await analyzer.get_gap_summary(events)
    assert summary["total"] == 2
    assert summary["by_response"][GapResponse.ESCALATED.value] == 1
    assert summary["by_response"][GapResponse.SKIPPED.value] == 1


@pytest.mark.asyncio
async def test_gap_tick_and_agent_captured(analyzer):
    """Gap records should capture tick and agent correctly."""
    events = [
        make_capability_gap(actor_id="agent-2", tool="special_tool", tick=5),
    ]
    gaps = await analyzer.analyze(events)
    assert len(gaps) == 1
    assert gaps[0]["tick"] == "5"
    assert gaps[0]["agent"] == "agent-2"
