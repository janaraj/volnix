"""Tests for reporter world challenge analysis."""
import pytest

from terrarium.engines.reporter.world_challenges import (
    ChallengeResponse,
    WorldChallengeAnalyzer,
)
from tests.engines.reporter.conftest import (
    make_animator_event,
    make_world_event,
)


@pytest.fixture
def analyzer() -> WorldChallengeAnalyzer:
    return WorldChallengeAnalyzer()


@pytest.mark.asyncio
async def test_analyze_threat_responses(analyzer):
    """Test analyzing agent responses to world-presented threats."""
    events = [
        make_animator_event(
            sub_type="hostile_npc",
            content={"message": "hostile agent approaching"},
            tick=1,
        ),
        make_world_event(actor_id="agent-1", action="block_hostile", tick=2),
    ]
    results = await analyzer.analyze_threat_responses(events, "agent-1")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_analyze_information_quality_responses(analyzer):
    """Test analyzing agent responses to bad or stale data."""
    events = [
        make_animator_event(
            sub_type="data_quality",
            content={"message": "stale cache data"},
            tick=1,
        ),
        make_world_event(actor_id="agent-1", action="verify_data", tick=2),
    ]
    results = await analyzer.analyze_information_quality_responses(events, "agent-1")
    assert len(results) == 1
    assert results[0]["response"] == ChallengeResponse.NOTICED


@pytest.mark.asyncio
async def test_analyze_failure_responses(analyzer):
    """Test analyzing agent responses to service failures."""
    events = [
        make_animator_event(
            sub_type="service_failure",
            content={"message": "database timeout error"},
            tick=1,
        ),
        make_world_event(actor_id="agent-1", action="retry_query", tick=2),
    ]
    results = await analyzer.analyze_failure_responses(events, "agent-1")
    assert len(results) == 1
    assert results[0]["response"] == ChallengeResponse.RETRIED


@pytest.mark.asyncio
async def test_classify_challenge_response(analyzer):
    """Test classifying challenge responses into ChallengeResponse categories."""
    # Threat with resistance
    events = [
        make_animator_event(
            sub_type="threat",
            content={"message": "malicious input detected"},
            tick=1,
        ),
        make_world_event(actor_id="agent-1", action="reject_input", tick=2),
    ]
    results = await analyzer.analyze_threat_responses(events, "agent-1")
    assert len(results) == 1
    # reject_input maps to RESISTED via "reject" keyword
    assert results[0]["response"] == ChallengeResponse.RESISTED
