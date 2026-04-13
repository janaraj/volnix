"""Unit tests for DecisionTraceBuilder."""
from __future__ import annotations

import json

from volnix.engines.reporter.decision_trace import (
    DecisionTraceBuilder,
    _extract_scalar_fields,
)


def _make_event(
    event_type: str,
    actor_id: str,
    action: str = "",
    service_id: str = "",
    outcome: str = "success",
    input_data: dict | None = None,
    response_body: object = None,
    state_deltas: list | None = None,
    event_id: str | None = None,
    target_entity: str | None = None,
) -> dict:
    return {
        "event_id": event_id or f"evt-{event_type}-{actor_id}",
        "event_type": event_type,
        "actor_id": actor_id,
        "action": action,
        "service_id": service_id,
        "outcome": outcome,
        "input_data": input_data or {},
        "response_body": response_body,
        "state_deltas": state_deltas or [],
        "causes": [],
        "target_entity": target_entity,
        "timestamp": {"wall_time": "2026-01-01T10:00:00", "tick": 1},
    }


async def test_empty_events_returns_empty_trace() -> None:
    builder = DecisionTraceBuilder()
    trace = await builder.build(events=[], actors=[], state_engine=None)
    assert trace["activations"] == []
    assert trace["information_analysis"] == {}
    assert trace["governance_summary"] == {}
    assert "domain_narrative" not in trace


async def test_single_actor_single_activation() -> None:
    actors = [{"id": "agent1", "type": "agent", "role": "buyer"}]
    events = [
        _make_event(
            "world.notion.databases.retrieve",
            "agent1",
            "databases.retrieve",
            "notion",
            response_body={"id": "db1", "status": "active"},
        ),
        _make_event(
            "world.notion.pages.create",
            "agent1",
            "pages.create",
            "notion",
            state_deltas=[{
                "entity_type": "page",
                "entity_id": "p1",
                "operation": "create",
                "fields": {"title": "Test"},
            }],
        ),
    ]
    builder = DecisionTraceBuilder()
    trace = await builder.build(events=events, actors=actors, state_engine=None)
    assert len(trace["activations"]) == 1
    act = trace["activations"][0]
    assert act["actor_id"] == "agent1"
    assert act["activation_id"] == "act-agent1-1"
    assert act["reason"] == "kickstart"
    assert len(act["actions"]) == 2
    # Read action has learned field
    assert "learned" in act["actions"][0]
    assert act["actions"][0]["learned"].get("id") == "db1"
    # Write action has effect field
    assert "effect" in act["actions"][1]
    assert act["actions"][1]["effect"]["operation"] == "create"


async def test_governance_blocked_action() -> None:
    actors = [{"id": "agent1", "type": "agent", "role": "buyer"}]
    events = [
        _make_event(
            "world.stripe.charges.create",
            "agent1",
            "charges.create",
            "stripe",
            outcome="blocked",
        ),
        _make_event("policy.block", "agent1"),
    ]
    builder = DecisionTraceBuilder()
    trace = await builder.build(events=events, actors=actors, state_engine=None)
    act = trace["activations"][0]
    action = act["actions"][0]
    assert action["committed"] is False
    assert action["governance"]["policy"] == "block"


async def test_multi_actor_turn_grouping() -> None:
    actors = [
        {"id": "buyer", "type": "agent", "role": "buyer"},
        {"id": "supplier", "type": "agent", "role": "supplier"},
    ]
    events = [
        _make_event(
            "world.game.negotiate_propose", "buyer", "negotiate_propose", "game"
        ),
        _make_event(
            "world.game.negotiate_counter", "supplier", "negotiate_counter", "game"
        ),
        _make_event(
            "world.game.negotiate_accept", "buyer", "negotiate_accept", "game"
        ),
    ]
    builder = DecisionTraceBuilder()
    trace = await builder.build(events=events, actors=actors, state_engine=None)
    assert len(trace["activations"]) == 3
    assert trace["activations"][0]["actor_id"] == "buyer"
    assert trace["activations"][1]["actor_id"] == "supplier"
    assert trace["activations"][2]["actor_id"] == "buyer"
    assert trace["activations"][2]["activation_id"] == "act-buyer-2"


async def test_animator_events_in_world_response_not_actions() -> None:
    actors = [{"id": "agent1", "type": "agent", "role": "buyer"}]
    events = [
        _make_event("world.slack.chat.post", "agent1", "chat.post", "slack"),
        _make_event(
            "world.slack.chat.post",
            "animator",
            "chat.post",
            "slack",
            response_body={"text": "Slack message from system"},
        ),
    ]
    builder = DecisionTraceBuilder()
    trace = await builder.build(events=events, actors=actors, state_engine=None)
    # Only agent's action in actions list
    assert len(trace["activations"][0]["actions"]) == 1
    # Animator event in world_response
    reactions = trace["activations"][0]["world_response"]["animator_reactions"]
    assert len(reactions) == 1
    assert "Slack message" in reactions[0]["summary"]


async def test_information_coverage_ratio() -> None:
    class MockStateEngine:
        async def count_entities(self) -> int:
            return 10

    actors = [{"id": "agent1", "type": "agent", "role": "buyer"}]
    events = [
        {
            **_make_event(
                "world.notion.databases.retrieve",
                "agent1",
                "databases.retrieve",
                "notion",
            ),
            "target_entity": "db1",
        },
        {
            **_make_event(
                "world.notion.databases.retrieve",
                "agent1",
                "databases.retrieve",
                "notion",
            ),
            "target_entity": "db2",
        },
        {
            **_make_event(
                "world.notion.databases.retrieve",
                "agent1",
                "databases.retrieve",
                "notion",
            ),
            "target_entity": "db3",
        },
    ]
    builder = DecisionTraceBuilder()
    trace = await builder.build(
        events=events, actors=actors, state_engine=MockStateEngine()
    )
    info = trace["information_analysis"]["agent1"]
    assert info["entities_available"] == 10
    assert info["entities_queried"] == 3
    assert info["coverage_ratio"] == 0.3


def test_key_field_extraction_prefers_preferred_fields() -> None:
    body = {
        "id": "abc",
        "status": "active",
        "nested": {"key": "val"},
        "some_list": [1, 2, 3],
        "price": 99.5,
        "_internal": "skip",
        "irrelevant": "kept_if_cap_allows",
    }
    result = _extract_scalar_fields(body, cap=3)
    assert "id" in result
    assert "status" in result
    assert "price" in result
    assert "nested" not in result
    assert "_internal" not in result
    assert len(result) == 3


async def test_domain_narrative_absent_without_interpreter() -> None:
    builder = DecisionTraceBuilder()
    trace = await builder.build(events=[], actors=[], state_engine=None)
    assert "domain_narrative" not in trace


async def test_game_result_extracted_from_terminated_event() -> None:
    events = [
        {
            "event_id": "evt-term",
            "event_type": "game.terminated",
            "actor_id": "system",
            "reason": "deal_closed",
            "winner": "buyer",
            "total_events": 5,
            "wall_clock_seconds": 12.3,
            "scoring_mode": "behavioral",
            "final_standings": [],
            "timestamp": {"wall_time": "2026-01-01T10:00:00", "tick": 10},
        }
    ]
    builder = DecisionTraceBuilder()
    trace = await builder.build(events=events, actors=[], state_engine=None)
    assert trace["game_outcome"]["reason"] == "deal_closed"
    assert trace["game_outcome"]["winner"] == "buyer"
    assert trace["game_outcome"]["total_events"] == 5


async def test_trace_is_json_serializable() -> None:
    actors = [{"id": "agent1", "type": "agent", "role": "buyer"}]
    events = [
        _make_event(
            "world.notion.pages.create",
            "agent1",
            "pages.create",
            "notion",
            state_deltas=[{
                "entity_type": "page",
                "entity_id": "p1",
                "operation": "create",
                "fields": {"title": "X"},
            }],
        ),
    ]
    builder = DecisionTraceBuilder()
    trace = await builder.build(events=events, actors=actors, state_engine=None)
    serialized = json.dumps(trace)  # must not raise TypeError
    assert "activations" in json.loads(serialized)
