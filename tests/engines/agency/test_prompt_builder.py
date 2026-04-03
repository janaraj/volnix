"""Tests for ActorPromptBuilder -- prompt assembly for actor action generation."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from terrarium.actors.state import ActorState, InteractionRecord
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
        mission="Evaluate agent support quality.",
        seeds=["VIP customer waiting 3 days for refund"],
        available_services=[
            {"name": "reply_ticket", "service": "helpdesk", "http_method": "POST",
             "description": "Reply to a ticket", "required_params": ["ticket_id", "text"]},
            {"name": "list_tickets", "service": "helpdesk", "http_method": "GET",
             "description": "List tickets", "required_params": []},
            {"name": "email_search", "service": "email", "http_method": "GET",
             "description": "Search emails", "required_params": ["q"]},
        ],
    )


def _make_actor(**kwargs) -> ActorState:
    defaults = {
        "actor_id": ActorId("actor-alice"),
        "role": "support_agent",
        "actor_type": "internal",
        "current_goal": "Resolve ticket quickly",
        "goal_context": "Resolve ticket quickly",
        "persona": {"description": "Patient and thorough support agent"},
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
        input_data={"status": "escalated", "text": "This ticket needs attention"},
    )


def test_system_prompt_from_world_context():
    """System prompt includes world, mission, seeds, services grouped by read/write."""
    ctx = _make_world_context()
    builder = ActorPromptBuilder(ctx)

    prompt = builder.build_system_prompt()

    assert "## World" in prompt
    assert "corporate helpdesk" in prompt
    assert "## Mission" in prompt
    assert "Evaluate agent" in prompt
    assert "## World Scenarios" in prompt
    assert "VIP customer" in prompt
    assert "## Available Tools" in prompt
    assert "### helpdesk" in prompt
    assert "action_type: \"list_tickets\"" in prompt
    assert "action_type: \"reply_ticket\"" in prompt
    assert "### email" in prompt
    assert "action_type: \"email_search\"" in prompt


def test_system_prompt_minimal():
    """System prompt works with minimal context."""
    ctx = WorldContextBundle(
        world_description="Simple world",
        reality_summary="Ideal",
    )
    builder = ActorPromptBuilder(ctx)

    prompt = builder.build_system_prompt()

    assert "## World" in prompt
    assert "Simple world" in prompt
    assert "## Mission" not in prompt
    assert "## Services" not in prompt


def test_individual_prompt_structure():
    """Individual prompt contains identity, instructions, context, trigger, output."""
    ctx = _make_world_context()
    builder = ActorPromptBuilder(ctx)
    actor = _make_actor()
    event = _make_event()

    prompt = builder.build_individual_prompt(
        actor=actor,
        trigger_event=event,
        activation_reason="event_affected",
        available_actions=[],
    )

    # Identity
    assert "support_agent" in prompt
    assert "actor-alice" in prompt
    assert "Patient and thorough" in prompt

    # Instructions
    assert "## Instructions" in prompt

    # Context
    assert "Mission Context" in prompt
    assert "Resolve ticket quickly" in prompt

    # Trigger
    assert "agent-external" in prompt
    assert "update_ticket" in prompt

    # Output
    assert "## Output" in prompt
    assert "do_nothing" in prompt


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
    assert "## Trigger\n**" not in prompt


def test_individual_prompt_with_interactions():
    """Individual prompt shows recent interactions with text."""
    ctx = _make_world_context()
    builder = ActorPromptBuilder(ctx)
    actor = _make_actor()
    actor.recent_interactions = [
        InteractionRecord(
            tick=1.0,
            actor_id="agent-external",
            actor_role="customer",
            action="reply_ticket",
            summary="I need help with my account",
            source="observed",
            event_id="evt-1",
        ),
        InteractionRecord(
            tick=2.0,
            actor_id="actor-alice",
            actor_role="support_agent",
            action="reply_ticket",
            summary="Let me look into that for you",
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

    assert "Recent Activity" in prompt
    assert "I need help with my account" in prompt
    assert "You:" in prompt
    assert "Let me look into that" in prompt


def test_individual_prompt_with_waiting():
    """Waiting_for is no longer rendered (internal engine state)."""
    from terrarium.actors.state import WaitingFor

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

    # Waiting_for is engine-internal, not shown in new prompt
    assert "wait_threshold" in prompt


def test_autonomous_prompt_has_team_and_instructions():
    """Autonomous agent prompt includes team channel and work instructions."""
    from terrarium.actors.state import Subscription

    ctx = _make_world_context()
    builder = ActorPromptBuilder(ctx)
    actor = _make_actor(autonomous=True)
    actor.team_channel = "#research"
    actor.subscriptions = [
        Subscription(service_id="slack", filter={"channel": "#research"})
    ]

    prompt = builder.build_individual_prompt(
        actor=actor,
        trigger_event=None,
        activation_reason="autonomous_continue",
        available_actions=[{"name": "email_search", "http_method": "GET"}],
        team_roster=[
            {"role": "support_agent", "id": "actor-alice"},
            {"role": "manager", "id": "actor-bob"},
        ],
    )

    assert "#research" in prompt
    assert "QUERY before you speak" in prompt
    assert "SHARE facts, not plans" in prompt
    assert "Action History" in prompt


def test_batch_prompt_structure():
    """Batch prompt contains actor sections."""
    ctx = _make_world_context()
    builder = ActorPromptBuilder(ctx)

    actor1 = _make_actor(actor_id=ActorId("actor-alice"), role="support_agent")
    actor2 = _make_actor(actor_id=ActorId("actor-bob"), role="manager")
    event = _make_event()

    prompt = builder.build_batch_prompt(
        actors_with_triggers=[
            (actor1, event, "event_affected"),
            (actor2, None, "frustration_threshold"),
        ],
        available_actions=[],
    )

    assert "Actor: support_agent (ID: actor-alice)" in prompt
    assert "event_affected" in prompt
    assert "Actor: manager (ID: actor-bob)" in prompt
    assert "frustration_threshold" in prompt


def test_batch_prompt_with_no_actions():
    """Batch prompt works without available actions."""
    ctx = _make_world_context()
    builder = ActorPromptBuilder(ctx)
    actor = _make_actor()

    prompt = builder.build_batch_prompt(
        actors_with_triggers=[(actor, None, "event_affected")],
        available_actions=[],
    )

    assert "Actor: support_agent" in prompt


def test_output_schemas_are_valid_json():
    """ACTION_OUTPUT_SCHEMA and BATCH_OUTPUT_SCHEMA are valid JSON-serializable dicts."""
    action_json = json.dumps(ACTION_OUTPUT_SCHEMA)
    assert json.loads(action_json) == ACTION_OUTPUT_SCHEMA

    batch_json = json.dumps(BATCH_OUTPUT_SCHEMA)
    assert json.loads(batch_json) == BATCH_OUTPUT_SCHEMA


def test_addressed_to_you_tag():
    """Messages addressed to the agent show [TO YOU] tag."""
    ctx = _make_world_context()
    builder = ActorPromptBuilder(ctx)
    actor = _make_actor(role="support_agent")
    actor.recent_interactions = [
        InteractionRecord(
            tick=1.0,
            actor_id="manager",
            actor_role="manager",
            action="chat.postMessage",
            summary="Please handle ticket 42",
            source="notified",
            event_id="evt-1",
            intended_for=["support_agent"],
        ),
    ]

    prompt = builder.build_individual_prompt(
        actor=actor,
        trigger_event=None,
        activation_reason="subscription_match",
        available_actions=[],
    )

    assert "[TO YOU]" in prompt
    assert "Please handle ticket 42" in prompt
