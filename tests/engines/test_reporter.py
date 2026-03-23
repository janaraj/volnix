"""Tests for terrarium.engines.reporter — scorecards, gap logs, causal traces, diffs."""
import pytest
from unittest.mock import AsyncMock

from terrarium.core.types import EventId
from terrarium.engines.reporter.engine import ReportGeneratorEngine
from tests.engines.reporter.conftest import (
    make_capability_gap,
    make_permission_denied,
    make_world_event,
)


async def _make_engine(events=None):
    """Helper: create and initialize a ReportGeneratorEngine with mock state."""
    eng = ReportGeneratorEngine()
    mock_state = AsyncMock()
    mock_state.get_timeline = AsyncMock(return_value=events or [])
    mock_state.get_causal_chain = AsyncMock(return_value=[])
    eng._dependencies = {"state": mock_state}
    eng._config = {}
    await eng._on_initialize()
    return eng


@pytest.mark.asyncio
async def test_reporter_scorecard():
    """Scorecard generation produces per_actor and collective keys."""
    eng = await _make_engine([make_world_event(tick=1)])
    result = await eng.generate_scorecard()
    assert "per_actor" in result
    assert "collective" in result


@pytest.mark.asyncio
async def test_reporter_gap_log():
    """Gap log returns list with correct count."""
    events = [
        make_capability_gap(actor_id="agent-1", tool="t1", tick=1),
        make_world_event(actor_id="agent-1", action="fallback", tick=2),
    ]
    eng = await _make_engine(events)
    result = await eng.generate_gap_log()
    assert isinstance(result, list)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_reporter_causal_trace():
    """Causal trace returns dict with root_event."""
    eng = await _make_engine()
    result = await eng.generate_causal_trace(EventId("evt-1"))
    assert result["root_event"] == "evt-1"


@pytest.mark.asyncio
async def test_reporter_diff():
    """Diff with two run IDs returns structured comparison."""
    eng = await _make_engine()
    result = await eng.generate_diff(["run-a", "run-b"])
    assert "runs" in result
    assert result["runs"] == ["run-a", "run-b"]


@pytest.mark.asyncio
async def test_reporter_full_report():
    """Full report contains all expected sections."""
    eng = await _make_engine()
    result = await eng.generate_full_report()
    assert "scorecard" in result
    assert "gap_log" in result
    assert "gap_summary" in result
    assert "condition_report" in result
