"""Tests for CounterfactualDiffer -- run comparison."""
import pytest
from unittest.mock import AsyncMock

from volnix.engines.reporter.diff import CounterfactualDiffer
from volnix.engines.reporter.scorecard import ScorecardComputer
from tests.engines.reporter.conftest import make_world_event


def _mock_state(events=None):
    """Create a mock state engine returning given events."""
    state = AsyncMock()
    state.get_timeline = AsyncMock(return_value=events or [])
    return state


@pytest.mark.asyncio
async def test_two_identical_runs_zero_deltas():
    """Two identical runs should produce zero deltas in scores."""
    events = [make_world_event(tick=1)]
    state = _mock_state(events)

    computer = ScorecardComputer()
    differ = CounterfactualDiffer(scorecard_computer=computer)

    result = await differ.compare(["run-1", "run-2"], state)
    assert result["runs"] == ["run-1", "run-2"]

    # Same timeline → same scores → delta = 0
    for metric, data in result["score_diff"].items():
        if isinstance(data.get("delta"), (int, float)):
            assert data["delta"] == 0.0, f"Expected zero delta for {metric}"


@pytest.mark.asyncio
async def test_event_diff_counts():
    """Event diff should report correct counts."""
    events = [make_world_event(tick=1), make_world_event(tick=2)]
    state = _mock_state(events)

    differ = CounterfactualDiffer()
    result = await differ.compare(["run-1", "run-2"], state)

    assert result["event_diff"]["counts"] == [2, 2]


@pytest.mark.asyncio
async def test_needs_at_least_two_runs():
    """Compare with fewer than 2 runs should return error."""
    state = _mock_state()
    differ = CounterfactualDiffer()
    result = await differ.compare(["run-1"], state)
    assert "error" in result


@pytest.mark.asyncio
async def test_entity_state_diff():
    """Entity state differ should detect differences."""
    differ = CounterfactualDiffer()

    states = [
        {"ticket_1": {"status": "open"}},
        {"ticket_1": {"status": "closed"}},
    ]
    diff = differ._diff_entity_states(states)

    assert len(diff["changed_entities"]) == 1
    assert diff["changed_entities"][0]["entity"] == "ticket_1"
