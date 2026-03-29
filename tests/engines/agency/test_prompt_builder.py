"""Tests for ActorPromptBuilder -- prompt assembly for actor action generation."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from terrarium.actors.state import ActorState, WaitingFor
from terrarium.core.events import WorldEvent
from terrarium.core.types import ActorId, EntityId, ServiceId, Timestamp
from terrarium.engines.agency.prompt_builder import (
    ACTION_OUTPUT_SCHEMA,
    BATCH_OUTPUT_SCHEMA,
    ActorPromptBuilder,
)
from terrarium.simulation.world_context import WorldContextBundle


def _make_world_context() -> WorldContextBundle:
    return WorldContextBundle(
        world_description="A corporate helpdesk simulation.",
        reality_summary="Messy reality with occasional system failures.",
        behavior_mode="reactive",
        behavior_description="World reacts to agent actions.",
        governance_rules_summary="No PII sharing. Manager approval for refunds > $100.",
        mission="Evaluate agent support quality.",
        available_services=[
            {
                "name": "helpdesk",
                "actions": [
                    {"name": "reply_ticket"},
                    {"name": "close_ticket"},
                ],
            },
            {
                "name": "email",
                "actions": [
                    {"name": "send_email"},
                ],
            },
        ],
    )


def _make_actor(**kwargs) -> ActorState:
    defaults = {
        "actor_id": ActorId("actor-alice"),
        "role": "support_agent",
        "actor_type": "internal",
        "current_goal": "Resolve ticket quickly",
        "goal_strategy": "Check knowledge base first",
        "frustration": 0.3,
        "urgency": 0.5,
        "persona": {"name": "Alice", "temperament": "patient"},
    }
    defaults.update(kwargs)
    return ActorState(**defaults)


def _make_event() -> WorldEvent:
    now = datetime.now(UTC)
    return WorldEvent(
        event_type="world.ticket_update",
        timestamp=Timestamp(world_time=now, wall_time=now, tick=5),
        actor_id=ActorId("agent-external"),
        service_id=ServiceId("helpdesk"),
        action="update_ticket",
        target_entity=EntityId("ticket-42"),
        input_data={"status": "escalated"},
        post_state={"status": "escalated", "priority": "high"},
    )


def _sample_actions() -> list[dict]:
    return [
        {"name": "reply_ticket", "description": "Reply to a support ticket"},
        {"name": "close_ticket", "description": "Close a resolved ticket"},
        {"name": "send_email", "description": "Send an email notification"},
    ]


def test_system_prompt_from_world_context():
    """System prompt includes all world context sections."""
    ctx = _make_world_context()
    builder = ActorPromptBuilder(ctx)

    prompt = builder.build_system_prompt()

    assert "## World" in prompt
    assert "corporate helpdesk" in prompt
    assert "## Reality" in prompt
    assert "Messy reality" in prompt
    assert "## Behavior Mode" in prompt
    assert "reactive" in prompt
    assert "## Governance Rules" in prompt
    assert "Manager approval" in prompt
    assert "## Mission" in prompt
    assert "Evaluate agent" in prompt
    assert "## Available Services" in prompt
    assert "helpdesk" in prompt
    assert "email" in prompt


def test_system_prompt_minimal():
    """System prompt works with minimal context."""
    ctx = WorldContextBundle(
        world_description="Simple world",
        reality_summary="Ideal",
        behavior_mode="static",
    )
    builder = ActorPromptBuilder(ctx)

    prompt = builder.build_system_prompt()

    assert "## World" in prompt
    assert "Simple world" in prompt
    # No governance or mission sections
    assert "## Governance Rules" not in prompt
    assert "## Mission" not in prompt


def test_individual_prompt_structure():
    """Individual prompt contains all required sections."""
    ctx = _make_world_context()
    builder = ActorPromptBuilder(ctx)
    actor = _make_actor()
    event = _make_event()
    actions = _sample_actions()

    prompt = builder.build_individual_prompt(
        actor=actor,
        trigger_event=event,
        activation_reason="event_affected",
        available_actions=actions,
    )

    # Actor identity
    assert "support_agent" in prompt
    assert "actor-alice" in prompt

    # Persona
    assert "Alice" in prompt
    assert "patient" in prompt

    # Current state
    assert "Resolve ticket quickly" in prompt
    assert "Frustration: 0.30" in prompt
    assert "Urgency: 0.50" in prompt

    # Trigger (human-readable summary, not raw JSON)
    assert "event_affected" in prompt
    assert "agent-external" in prompt
    assert "update_ticket" in prompt
    assert "helpdesk" in prompt

    # Available actions
    assert "reply_ticket" in prompt
    assert "close_ticket" in prompt
    assert "send_email" in prompt

    # Output schema
    assert "Instructions" in prompt
    assert "do_nothing" in prompt


def test_individual_prompt_with_waiting():
    """Individual prompt includes waiting_for information."""
    ctx = _make_world_context()
    builder = ActorPromptBuilder(ctx)
    actor = _make_actor(
        waiting_for=WaitingFor(
            description="Manager approval for refund",
            since=2.0,
            patience=10.0,
        )
    )

    prompt = builder.build_individual_prompt(
        actor=actor,
        trigger_event=None,
        activation_reason="wait_threshold",
        available_actions=[],
    )

    assert "Waiting for: Manager approval for refund" in prompt
    assert "patience=10.0" in prompt


def test_individual_prompt_no_trigger():
    """Individual prompt works without a trigger event."""
    ctx = _make_world_context()
    builder = ActorPromptBuilder(ctx)
    actor = _make_actor()

    prompt = builder.build_individual_prompt(
        actor=actor,
        trigger_event=None,
        activation_reason="frustration_threshold",
        available_actions=[],
    )

    assert "frustration_threshold" in prompt
    assert "Trigger Event" not in prompt


def test_individual_prompt_with_interactions():
    """Individual prompt shows recent interactions."""
    from terrarium.actors.state import InteractionRecord

    ctx = _make_world_context()
    builder = ActorPromptBuilder(ctx)
    actor = _make_actor()
    actor.recent_interactions = [
        InteractionRecord(
            tick=1.0,
            actor_id="agent-external",
            actor_role="customer",
            action="reply_ticket",
            summary="reply_ticket by agent-external",
            source="observed",
            event_id="evt-1",
        ),
        InteractionRecord(
            tick=2.0,
            actor_id="actor-alice",
            actor_role="support_agent",
            action="close_ticket",
            summary="close_ticket by actor-alice",
            source="self",
            event_id="evt-2",
        ),
    ]

    prompt = builder.build_individual_prompt(
        actor=actor,
        trigger_event=None,
        activation_reason="event_affected",
        available_actions=[],
    )

    assert "Recent activity you're aware of" in prompt
    assert "reply_ticket by agent-external" in prompt


def test_batch_prompt_structure():
    """Batch prompt contains sections for each actor."""
    ctx = _make_world_context()
    builder = ActorPromptBuilder(ctx)

    actor1 = _make_actor(actor_id=ActorId("actor-alice"), role="support_agent")
    actor2 = _make_actor(actor_id=ActorId("actor-bob"), role="manager")
    event = _make_event()
    actions = _sample_actions()

    actors_with_triggers = [
        (actor1, event, "event_affected"),
        (actor2, None, "frustration_threshold"),
    ]

    prompt = builder.build_batch_prompt(
        actors_with_triggers=actors_with_triggers,
        available_actions=actions,
    )

    # Header
    assert "Batch Action Generation" in prompt

    # Actor 1
    assert "Actor: support_agent (ID: actor-alice)" in prompt
    assert "event_affected" in prompt

    # Actor 2
    assert "Actor: manager (ID: actor-bob)" in prompt
    assert "frustration_threshold" in prompt

    # Actions and schema
    assert "reply_ticket" in prompt
    assert "Output Schema" in prompt


def test_available_actions_formatted():
    """Available actions are properly formatted in prompts."""
    ctx = _make_world_context()
    builder = ActorPromptBuilder(ctx)
    actor = _make_actor()

    actions = [
        {"name": "create_ticket", "description": "Create a new support ticket"},
        {"name": "assign_ticket", "description": "Assign ticket to an agent"},
    ]

    prompt = builder.build_individual_prompt(
        actor=actor,
        trigger_event=None,
        activation_reason="event_affected",
        available_actions=actions,
    )

    # Actions now include service context
    assert "create_ticket" in prompt
    assert "Create a new support ticket" in prompt
    assert "assign_ticket" in prompt
    assert "Assign ticket to an agent" in prompt


def test_output_schemas_are_valid_json():
    """ACTION_OUTPUT_SCHEMA and BATCH_OUTPUT_SCHEMA are valid JSON-serializable dicts."""
    # Round-trip through JSON
    action_json = json.dumps(ACTION_OUTPUT_SCHEMA)
    assert json.loads(action_json) == ACTION_OUTPUT_SCHEMA

    batch_json = json.dumps(BATCH_OUTPUT_SCHEMA)
    assert json.loads(batch_json) == BATCH_OUTPUT_SCHEMA


def test_batch_prompt_with_no_actions():
    """Batch prompt works without available actions."""
    ctx = _make_world_context()
    builder = ActorPromptBuilder(ctx)
    actor = _make_actor()

    prompt = builder.build_batch_prompt(
        actors_with_triggers=[(actor, None, "event_affected")],
        available_actions=[],
    )

    assert "Batch Action Generation" in prompt
    assert "Available Actions" not in prompt
