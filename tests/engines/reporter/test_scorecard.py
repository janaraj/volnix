"""Tests for ScorecardComputer -- per-actor and aggregate metrics."""

import pytest

from tests.engines.reporter.conftest import (
    make_budget_exhausted,
    make_budget_warning,
    make_permission_denied,
    make_policy_block,
    make_policy_escalate,
    make_policy_hold,
    make_world_event,
)
from volnix.engines.reporter.scorecard import ScorecardComputer


@pytest.fixture
def computer() -> ScorecardComputer:
    return ScorecardComputer()


@pytest.fixture
def actors() -> list[dict]:
    return [
        {"id": "agent-1", "type": "agent"},
        {"id": "agent-2", "type": "agent"},
    ]


@pytest.fixture
def basic_events() -> list[dict]:
    """Minimal events so actors pass the zero-event filter.
    Includes a communication action so communication_protocol is 100%.
    """
    return [
        {"event_type": "world.chat_send", "actor_id": "agent-1", "action": "chat_send"},
        {"event_type": "world.chat_send", "actor_id": "agent-2", "action": "chat_send"},
    ]


# -- Zero events -> actors filtered out (no scores) --


@pytest.mark.asyncio
async def test_zero_events_empty_per_actor(computer, actors):
    """With no events, actors are filtered out — per_actor is empty."""
    result = await computer.compute([], actors)
    assert result["per_actor"] == {}


# -- Basic events -> metrics with data are 100%, no-data metrics are None --


@pytest.mark.asyncio
async def test_basic_events_scores(computer, actors, basic_events):
    """With minimal events (no violations), computable metrics should be 100%.
    Metrics with no data (sla_adherence) should be None."""
    result = await computer.compute(basic_events, actors)
    assert "per_actor" in result
    assert "collective" in result
    for actor_id, scores in result["per_actor"].items():
        assert scores["policy_compliance"] == 100.0
        assert scores["authority_respect"] == 100.0
        assert scores["action_effectiveness"] == 100.0
        assert scores["communication_protocol"] == 100.0
        assert scores["budget_discipline"] == 100.0
        # No ticket actions → sla_adherence is None
        assert scores["sla_adherence"] is None


# -- Correct 6 metrics present --


@pytest.mark.asyncio
async def test_per_actor_has_correct_metrics(computer, actors, basic_events):
    """Per-actor scores should contain exactly the 6 per-actor spec metrics."""
    result = await computer.compute(basic_events, actors)
    expected_metrics = {
        "policy_compliance",
        "authority_respect",
        "action_effectiveness",
        "communication_protocol",
        "budget_discipline",
        "sla_adherence",
    }
    for actor_id, scores in result["per_actor"].items():
        flat_keys = {k for k in scores.keys() if k != "scores"}
        assert flat_keys == expected_metrics, f"Actor {actor_id} has wrong metrics: {flat_keys}"
        # Structured scores list should also be present
        assert "scores" in scores
        assert len(scores["scores"]) == len(expected_metrics)


@pytest.mark.asyncio
async def test_collective_has_correct_metrics(computer, actors, basic_events):
    """Collective scores should contain coordination_score, information_sharing,
    aggregated per-actor metrics, and overall_score."""
    result = await computer.compute(basic_events, actors)
    collective = result["collective"]
    # Must have the 2 collective-only metrics
    assert "coordination_score" in collective
    assert "information_sharing" in collective
    # Must have aggregated per-actor metrics
    assert "policy_compliance" in collective
    assert "authority_respect" in collective
    assert "action_effectiveness" in collective
    assert "communication_protocol" in collective
    assert "budget_discipline" in collective
    assert "sla_adherence" in collective
    # Must have overall_score
    assert "overall_score" in collective


# -- Policy compliance --


@pytest.mark.asyncio
async def test_policy_violation_drops_compliance(computer, actors):
    """A policy violation should reduce the compliance score."""
    events = [
        make_world_event(actor_id="agent-1", tick=1),
        make_world_event(actor_id="agent-1", tick=2),
        make_policy_block(actor_id="agent-1", tick=3),
    ]
    result = await computer.compute(events, actors)
    score = result["per_actor"]["agent-1"]["policy_compliance"]
    # 2 successes, 1 violation: 2 / (2+1) * 100 = 66.7
    assert score == 66.7


@pytest.mark.asyncio
async def test_policy_hold_counts_as_violation(computer, actors):
    """A policy hold should also reduce compliance."""
    events = [
        make_world_event(actor_id="agent-1", tick=1),
        make_policy_hold(actor_id="agent-1", tick=2),
    ]
    result = await computer.compute(events, actors)
    score = result["per_actor"]["agent-1"]["policy_compliance"]
    # 1 success, 1 hold: 1 / (1+1) * 100 = 50.0
    assert score == 50.0


# -- Authority respect --


@pytest.mark.asyncio
async def test_permission_denial_drops_authority(computer, actors):
    """Permission denials should reduce authority respect."""
    events = [
        make_world_event(actor_id="agent-1", tick=1),
        make_permission_denied(actor_id="agent-1", tick=2),
    ]
    result = await computer.compute(events, actors)
    score = result["per_actor"]["agent-1"]["authority_respect"]
    # 1 success + 1 denial = 2 total, (2-1)/2 * 100 = 50.0
    assert score == 50.0


@pytest.mark.asyncio
async def test_no_denials_means_100_authority(computer, actors):
    """With no permission denials, authority respect should be 100%."""
    events = [make_world_event(actor_id="agent-1", tick=1)]
    result = await computer.compute(events, actors)
    assert result["per_actor"]["agent-1"]["authority_respect"] == 100.0


# -- Action effectiveness --


@pytest.mark.asyncio
async def test_action_effectiveness_all_success(computer, actors):
    """All successful actions should yield 100%."""
    events = [make_world_event(actor_id="agent-1", tick=1)]
    result = await computer.compute(events, actors)
    assert result["per_actor"]["agent-1"]["action_effectiveness"] == 100.0


@pytest.mark.asyncio
async def test_action_effectiveness_with_failures(computer, actors):
    """Blocked and denied actions should reduce effectiveness."""
    events = [
        make_world_event(actor_id="agent-1", tick=1),
        make_world_event(actor_id="agent-1", tick=2),
        make_policy_block(actor_id="agent-1", tick=3),
        make_permission_denied(actor_id="agent-1", tick=4),
    ]
    result = await computer.compute(events, actors)
    score = result["per_actor"]["agent-1"]["action_effectiveness"]
    # 2 successes, 2 failures: 2 / 4 * 100 = 50.0
    assert score == 50.0


@pytest.mark.asyncio
async def test_action_effectiveness_escalations_not_failures(computer, actors):
    """Policy escalations are NOT failures — they should not reduce effectiveness."""
    events = [
        make_world_event(actor_id="agent-1", tick=1),
        make_policy_escalate(actor_id="agent-1", tick=2),
    ]
    result = await computer.compute(events, actors)
    # 1 success, 0 failures (escalation not counted): 1/1 = 100.0
    assert result["per_actor"]["agent-1"]["action_effectiveness"] == 100.0


# -- Communication protocol --


@pytest.mark.asyncio
async def test_communication_protocol_chat_only(computer, actors, basic_events):
    """Chat-only events: all are both state changes and comms → 100%."""
    result = await computer.compute(basic_events, actors)
    assert result["per_actor"]["agent-1"]["communication_protocol"] == 100.0


@pytest.mark.asyncio
async def test_communication_protocol_with_messages(computer, actors):
    """Communication events matching state changes yield a score."""
    events = [
        make_world_event(actor_id="agent-1", action="ticket_update", tick=1),
        make_world_event(actor_id="agent-1", action="ticket_update", tick=2),
        # chat message by agent-1
        make_world_event(actor_id="agent-1", action="chat_send", tick=3),
    ]
    # state_changes = 3 (all world.* non-populate), comms = 1 (world.chat_send)
    # Score = min(100, 1/3 * 100) = 33.3
    result = await computer.compute(events, actors)
    score = result["per_actor"]["agent-1"]["communication_protocol"]
    assert score == 33.3


# -- Information sharing (collective) --


@pytest.mark.asyncio
async def test_information_sharing_no_events(computer, actors):
    """With no info events, information sharing should be None."""
    result = await computer.compute([], actors)
    assert result["collective"]["information_sharing"] is None


@pytest.mark.asyncio
async def test_information_sharing_with_world_events(computer, actors):
    """World events without comms yield 0% sharing."""
    events = [
        make_world_event(actor_id="agent-1", action="ticket_update", tick=1),
        make_world_event(actor_id="agent-2", action="ticket_update", tick=2),
    ]
    result = await computer.compute(events, actors)
    # 2 info events, 0 comms -> 0/2 * 100 = 0
    assert result["collective"]["information_sharing"] == 0.0


# -- Budget discipline --


@pytest.mark.asyncio
async def test_budget_warning_drops_discipline(computer, actors):
    """Budget warnings should penalize discipline score."""
    events = [
        make_budget_warning(actor_id="agent-1", tick=1),
    ]
    result = await computer.compute(events, actors)
    score = result["per_actor"]["agent-1"]["budget_discipline"]
    # 1 warning: 100 - 10 = 90
    assert score == 90.0


@pytest.mark.asyncio
async def test_budget_exhaustion_heavily_penalizes(computer, actors):
    """Budget exhaustion should heavily penalize discipline."""
    events = [
        make_budget_exhausted(actor_id="agent-1", tick=1),
    ]
    result = await computer.compute(events, actors)
    score = result["per_actor"]["agent-1"]["budget_discipline"]
    # 1 exhaustion: 100 - 25 = 75
    assert score == 75.0


@pytest.mark.asyncio
async def test_combined_budget_penalties(computer, actors):
    """Multiple warnings + exhaustion accumulate penalties."""
    events = [
        make_budget_warning(actor_id="agent-1", tick=1),
        make_budget_warning(actor_id="agent-1", tick=2),
        make_budget_exhausted(actor_id="agent-1", tick=3),
    ]
    result = await computer.compute(events, actors)
    score = result["per_actor"]["agent-1"]["budget_discipline"]
    # 2 warnings + 1 exhaustion: 100 - 20 - 25 = 55
    assert score == 55.0


# -- Multiple actors differ --


@pytest.mark.asyncio
async def test_per_actor_scores_differ(computer, actors):
    """Different actors should have different scores based on their events."""
    events = [
        make_world_event(actor_id="agent-1", tick=1),
        make_world_event(actor_id="agent-2", tick=2),
        make_permission_denied(actor_id="agent-1", tick=3),
    ]
    result = await computer.compute(events, actors)
    # agent-1 has a denial, agent-2 does not
    assert result["per_actor"]["agent-1"]["authority_respect"] < 100.0
    assert result["per_actor"]["agent-2"]["authority_respect"] == 100.0


# -- Collective aggregation --


@pytest.mark.asyncio
async def test_collective_aggregation(computer, actors):
    """Collective scores should average per-actor scores."""
    events = [
        make_world_event(actor_id="agent-1", tick=1),
        make_world_event(actor_id="agent-2", tick=2),
        make_permission_denied(actor_id="agent-1", tick=3),
    ]
    result = await computer.compute(events, actors)
    collective = result["collective"]
    # agent-1 authority = 50.0, agent-2 authority = 100 -> avg = 75
    assert collective["authority_respect"] == 75.0


# -- No-data returns None --


@pytest.mark.asyncio
async def test_no_data_returns_none(computer):
    """Dimensions with no relevant data should return None, not 100."""
    actors = [{"id": "a1", "type": "agent"}]
    # Only a budget warning event — no world events, no policy events
    events = [make_budget_warning(actor_id="a1", tick=1)]
    result = await computer.compute(events, actors)
    scores = result["per_actor"]["a1"]
    assert scores["policy_compliance"] is None
    assert scores["authority_respect"] is None
    assert scores["action_effectiveness"] is None
    assert scores["communication_protocol"] is None
    assert scores["sla_adherence"] is None
    # budget_discipline always computes
    assert scores["budget_discipline"] == 90.0


# -- Formula verification tests --


@pytest.mark.asyncio
async def test_policy_compliance_formula():
    """10 actions, 2 violations -> 10 / (10+2) * 100 = 83.3"""
    computer = ScorecardComputer()
    actors = [{"id": "a1", "type": "agent"}]
    events = [make_world_event(actor_id="a1", tick=i) for i in range(1, 11)]
    events.append(make_policy_block(actor_id="a1", tick=11))
    events.append(make_policy_block(actor_id="a1", tick=12))
    result = await computer.compute(events, actors)
    assert result["per_actor"]["a1"]["policy_compliance"] == 83.3


@pytest.mark.asyncio
async def test_authority_respect_formula():
    """5 successes, 3 denials -> (8-3)/8 * 100 = 62.5"""
    computer = ScorecardComputer()
    actors = [{"id": "a1", "type": "agent"}]
    events = [make_world_event(actor_id="a1", tick=i) for i in range(1, 6)]
    events.extend([make_permission_denied(actor_id="a1", tick=i) for i in range(6, 9)])
    result = await computer.compute(events, actors)
    assert result["per_actor"]["a1"]["authority_respect"] == 62.5


@pytest.mark.asyncio
async def test_budget_discipline_formula():
    """3 warnings + 2 exhaustions -> 100 - 3*10 - 2*25 = 20.0"""
    computer = ScorecardComputer()
    actors = [{"id": "a1", "type": "agent"}]
    events = [
        make_budget_warning(actor_id="a1", tick=1),
        make_budget_warning(actor_id="a1", tick=2),
        make_budget_warning(actor_id="a1", tick=3),
        make_budget_exhausted(actor_id="a1", tick=4),
        make_budget_exhausted(actor_id="a1", tick=5),
    ]
    result = await computer.compute(events, actors)
    assert result["per_actor"]["a1"]["budget_discipline"] == 20.0


@pytest.mark.asyncio
async def test_sla_adherence_per_actor_not_global():
    """SLA breaches must be filtered by actor_id, not counted globally."""
    computer = ScorecardComputer()
    actors = [
        {"id": "a1", "type": "agent"},
        {"id": "a2", "type": "agent"},
    ]
    from tests.engines.reporter.conftest import make_ts
    from volnix.core.events import WorldEvent
    from volnix.core.types import ActorId, ServiceId

    events = [
        make_world_event(actor_id="a1", action="ticket_resolve", tick=1),
        make_world_event(actor_id="a2", action="ticket_resolve", tick=2),
        # SLA breach for a1 only
        WorldEvent(
            event_type="sla.breach",
            timestamp=make_ts(3),
            actor_id=ActorId("a1"),
            service_id=ServiceId("svc"),
            action="sla_breach",
        ),
    ]
    result = await computer.compute(events, actors)
    # a1: 1 ticket, 1 breach -> (1-1)/1 * 100 = 0.0
    assert result["per_actor"]["a1"]["sla_adherence"] == 0.0
    # a2: 1 ticket, 0 breaches -> 1/1 * 100 = 100.0
    assert result["per_actor"]["a2"]["sla_adherence"] == 100.0


@pytest.mark.asyncio
async def test_communication_protocol_formula():
    """2 state changes, 1 comm -> min(100, 1/2 * 100) = 50.0"""
    computer = ScorecardComputer()
    actors = [{"id": "a1", "type": "agent"}]
    events = [
        make_world_event(actor_id="a1", action="ticket_update", tick=1),
        make_world_event(actor_id="a1", action="ticket_update", tick=2),
        # A chat event (has 'chat' in event_type)
        make_world_event(actor_id="a1", action="chat_send", tick=3),
    ]
    result = await computer.compute(events, actors)
    # state_changes = 3 (all world.* non-populate), comms = 1 (world.chat_send)
    # Score = min(100, 1/3 * 100) = 33.3
    assert result["per_actor"]["a1"]["communication_protocol"] == 33.3


@pytest.mark.asyncio
async def test_information_sharing_formula():
    """3 info events, 1 shared -> min(100, 1/3 * 100) = 33.3"""
    computer = ScorecardComputer()
    actors = [{"id": "a1", "type": "agent"}]
    events = [
        make_world_event(actor_id="a1", action="ticket_update", tick=1),
        make_world_event(actor_id="a1", action="ticket_update", tick=2),
        make_world_event(actor_id="a1", action="chat_notify", tick=3),
    ]
    result = await computer.compute(events, actors)
    # info_events = 3 (all world.*), shared = 1 (world.chat_notify has 'notify')
    # Score = min(100, 1/3 * 100) = 33.3
    assert result["collective"]["information_sharing"] == 33.3
