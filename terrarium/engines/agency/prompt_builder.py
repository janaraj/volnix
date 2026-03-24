"""ActorPromptBuilder -- assembles per-actor LLM prompts.

Domain-agnostic. Combines actor-specific context (persona, state, trigger)
with the shared WorldContextBundle system prompt. Supports both individual
and batch prompt formats.
"""

from __future__ import annotations

import json
from typing import Any

from terrarium.actors.state import ActorState
from terrarium.core.events import WorldEvent
from terrarium.simulation.world_context import WorldContextBundle

# Output schema for action generation
ACTION_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action_type": {
            "type": "string",
            "description": "The action to take (or 'do_nothing')",
        },
        "target_service": {
            "type": ["string", "null"],
            "description": "Service to target",
        },
        "payload": {"type": "object", "description": "Action parameters"},
        "reasoning": {
            "type": "string",
            "description": "Brief reasoning for this action",
        },
        "state_updates": {
            "type": "object",
            "properties": {
                "frustration_delta": {"type": "number"},
                "urgency": {"type": "number"},
                "new_goal": {"type": ["string", "null"]},
                "goal_strategy": {"type": ["string", "null"]},
                "schedule_action": {"type": ["object", "null"]},
            },
        },
    },
    "required": ["action_type", "reasoning"],
}

BATCH_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "actor_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "actor_id": {"type": "string"},
                    "action_type": {"type": "string"},
                    "target_service": {"type": ["string", "null"]},
                    "payload": {"type": "object"},
                    "reasoning": {"type": "string"},
                    "state_updates": {"type": "object"},
                },
                "required": ["actor_id", "action_type", "reasoning"],
            },
        },
    },
    "required": ["actor_actions"],
}


class ActorPromptBuilder:
    """Builds LLM prompts for actor action generation."""

    def __init__(self, world_context: WorldContextBundle) -> None:
        self._world_context = world_context

    def build_system_prompt(self) -> str:
        """Return the shared world system prompt (layers 1-2)."""
        return self._world_context.to_system_prompt()

    def build_individual_prompt(
        self,
        actor: ActorState,
        trigger_event: WorldEvent | None,
        activation_reason: str,
        available_actions: list[dict[str, Any]],
    ) -> str:
        """Build per-actor user prompt (layers 3-4).

        Structure:
        - Actor identity (persona, role)
        - Current state (goal, waiting_for, frustration, recent interactions)
        - Trigger (what just happened)
        - Available actions
        - Output schema
        """
        sections: list[str] = []

        # Actor identity
        sections.append(f"## You are: {actor.role} (ID: {actor.actor_id})")
        if actor.persona:
            sections.append(f"### Persona\n{json.dumps(actor.persona, indent=2)}")

        # Current state
        state_lines = [
            f"- Goal: {actor.current_goal or 'None'}",
            f"- Strategy: {actor.goal_strategy or 'None'}",
            f"- Frustration: {actor.frustration:.2f}",
            f"- Urgency: {actor.urgency:.2f}",
        ]
        if actor.waiting_for:
            state_lines.append(
                f"- Waiting for: {actor.waiting_for.description} "
                f"(since t={actor.waiting_for.since:.1f},"
                f" patience={actor.waiting_for.patience:.1f})"
            )
        if actor.pending_notifications:
            state_lines.append(f"- Pending notifications: {len(actor.pending_notifications)}")
            for notif in actor.pending_notifications[-5:]:  # last 5
                state_lines.append(f"  - {notif}")
        if actor.recent_interactions:
            state_lines.append(f"- Recent interactions ({len(actor.recent_interactions)}):")
            for interaction in actor.recent_interactions[-5:]:
                state_lines.append(f"  - {interaction}")
        sections.append("### Current State\n" + "\n".join(state_lines))

        # Trigger
        sections.append(f"### Activation Reason: {activation_reason}")
        if trigger_event:
            trigger_info: dict[str, Any] = {
                "event_type": trigger_event.event_type,
                "actor_id": str(trigger_event.actor_id),
                "action": trigger_event.action,
                "service": str(trigger_event.service_id),
            }
            if trigger_event.post_state:
                trigger_info["result"] = trigger_event.post_state
            sections.append(f"### Trigger Event\n{json.dumps(trigger_info, indent=2)}")

        # Available actions
        if available_actions:
            action_lines = []
            for action in available_actions:
                name = action.get("name", "?")
                desc = action.get("description", "")
                action_lines.append(f"- {name}: {desc}")
            sections.append("### Available Actions\n" + "\n".join(action_lines))

        # Output instruction
        sections.append(
            "### Instructions\n"
            "Choose ONE action or 'do_nothing'. Respond with JSON matching"
            " the output schema.\n"
            f"Output schema: {json.dumps(ACTION_OUTPUT_SCHEMA, indent=2)}"
        )

        return "\n\n".join(sections)

    def build_batch_prompt(
        self,
        actors_with_triggers: list[tuple[ActorState, WorldEvent | None, str]],
        available_actions: list[dict[str, Any]],
    ) -> str:
        """Build batch prompt for multiple actors in one LLM call.

        Each actor gets a summary section. The LLM generates actions for all.
        """
        sections: list[str] = []
        sections.append(
            "## Batch Action Generation\n"
            "Generate actions for each of the following actors. "
            "Each actor may choose 'do_nothing' if they have no reason to act."
        )

        for actor, trigger, reason in actors_with_triggers:
            actor_section = [
                f"### Actor: {actor.role} (ID: {actor.actor_id})",
                f"- Goal: {actor.current_goal or 'None'}",
                f"- Frustration: {actor.frustration:.2f}",
                f"- Activation reason: {reason}",
            ]
            if actor.persona:
                persona_brief = str(actor.persona)[:200]
                actor_section.append(f"- Persona: {persona_brief}")
            if trigger:
                actor_section.append(
                    f"- Trigger: {trigger.event_type} by {trigger.actor_id} -> {trigger.action}"
                )
            sections.append("\n".join(actor_section))

        if available_actions:
            action_lines = [
                f"- {a.get('name', '?')}: {a.get('description', '')}" for a in available_actions
            ]
            sections.append("### Available Actions\n" + "\n".join(action_lines))

        sections.append(f"### Output Schema\n{json.dumps(BATCH_OUTPUT_SCHEMA, indent=2)}")

        return "\n\n".join(sections)
