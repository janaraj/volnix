"""Tests for WorldChallengeAnalyzer -- world-to-agent observation."""
import pytest

from terrarium.engines.reporter.world_challenges import (
    ChallengeResponse,
    WorldChallengeAnalyzer,
    WorldChallengeEntry,
)
from tests.engines.reporter.conftest import (
    make_animator_event,
    make_world_event,
)


@pytest.fixture
def analyzer() -> WorldChallengeAnalyzer:
    return WorldChallengeAnalyzer()


@pytest.mark.asyncio
async def test_threat_events_detected(analyzer):
    """AnimatorEvent with hostile content should produce threat challenges."""
    events = [
        make_animator_event(
            sub_type="npc_hostile",
            content={"message": "hostile attack incoming"},
            tick=1,
        ),
        make_world_event(actor_id="agent-1", action="resist_attack", tick=2),
    ]
    threats = await analyzer.analyze_threat_responses(events, "agent-1")
    assert len(threats) == 1
    assert threats[0]["response"] == ChallengeResponse.RESISTED


@pytest.mark.asyncio
async def test_threat_ignored_when_no_response(analyzer):
    """Threat with no agent response → IGNORED."""
    events = [
        make_animator_event(
            sub_type="npc_hostile",
            content={"message": "threat detected"},
            tick=1,
        ),
    ]
    threats = await analyzer.analyze_threat_responses(events, "agent-1")
    assert len(threats) == 1
    assert threats[0]["response"] == ChallengeResponse.IGNORED


@pytest.mark.asyncio
async def test_failure_events_detected(analyzer):
    """AnimatorEvent with failure content should produce failure challenges."""
    events = [
        make_animator_event(
            sub_type="service_failure",
            content={"message": "API timeout error"},
            tick=1,
        ),
        make_world_event(actor_id="agent-1", action="retry_request", tick=2),
    ]
    failures = await analyzer.analyze_failure_responses(events, "agent-1")
    assert len(failures) == 1
    assert failures[0]["response"] == ChallengeResponse.RETRIED


@pytest.mark.asyncio
async def test_no_events_empty_list(analyzer):
    """No animator events → empty challenge list."""
    events = [make_world_event(tick=1)]
    result = await analyzer.analyze(events, "agent-1", None)
    assert result == []


@pytest.mark.asyncio
async def test_full_analyze_combines_all_types(analyzer):
    """Full analyze should combine threats + data + failures + ambiguity."""
    events = [
        make_animator_event(
            sub_type="threat",
            content={"message": "hostile actor approaching"},
            tick=1,
        ),
        make_world_event(actor_id="agent-1", action="block_threat", tick=2),
        make_animator_event(
            sub_type="data_issue",
            content={"message": "stale data in database"},
            tick=3,
        ),
        make_world_event(actor_id="agent-1", action="verify_data", tick=4),
    ]
    result = await analyzer.analyze(events, "agent-1", None)
    assert len(result) >= 2

    types = [e.challenge_type for e in result]
    assert "threat" in types
    assert "bad_data" in types
