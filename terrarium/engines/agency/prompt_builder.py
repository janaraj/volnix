"""ActorPromptBuilder -- assembles per-actor LLM prompts.

Domain-agnostic. Combines actor-specific context (persona, state, trigger)
with the shared WorldContextBundle system prompt. Supports both individual
and batch prompt formats.
"""

from __future__ import annotations

import json
from typing import Any

from terrarium.actors.state import ActorState, InteractionRecord
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
                "pending_tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Your current task list",
                },
                "goal_context": {
                    "type": ["string", "null"],
                    "description": "Updated context about your goal progress",
                },
            },
        },
        "intended_for": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "When posting a message, list the actor roles you are addressing"
                " (e.g. ['oceanographer'] or ['all'])"
            ),
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
        sections.append("### Current State\n" + "\n".join(state_lines))

        # Structured interaction history (conversational context)
        if actor.recent_interactions:
            interaction_lines = ["### Recent activity you're aware of"]
            for record in actor.recent_interactions[-10:]:  # last 10
                if isinstance(record, InteractionRecord):
                    source_tag = ""
                    if record.source == "notified":
                        source_tag = " [notified via subscription]"
                    reply_tag = ""
                    if record.reply_to:
                        reply_tag = f" (reply to {record.reply_to})"
                    channel_tag = ""
                    if record.channel:
                        channel_tag = f" in {record.channel}"

                    if record.source == "self":
                        interaction_lines.append(
                            f"- [tick {record.tick}] You:"
                            f' "{record.summary}"{channel_tag}{reply_tag}'
                        )
                    else:
                        interaction_lines.append(
                            f"- [tick {record.tick}] {record.actor_role}"
                            f" ({record.actor_id}):"
                            f' "{record.summary}"{channel_tag}'
                            f"{reply_tag}{source_tag}"
                        )
                else:
                    # Backward compat: plain string
                    interaction_lines.append(f"- {record}")
            sections.append("\n".join(interaction_lines))

        # Pending tasks
        if actor.pending_tasks:
            task_lines = ["### Your pending tasks"]
            for i, task in enumerate(actor.pending_tasks, 1):
                task_lines.append(f"{i}. {task}")
            sections.append("\n".join(task_lines))

        # Goal context
        if actor.goal_context:
            sections.append(f"### Goal context\n{actor.goal_context}")

        # Trigger
        sections.append(f"### Activation Reason: {activation_reason}")
        if trigger_event:
            trigger_info: dict[str, Any] = {
                "event_type": trigger_event.event_type,
                "actor_id": str(trigger_event.actor_id),
                "action": trigger_event.action,
                "service": str(trigger_event.service_id),
            }
            # Include key payload fields so the LLM can construct valid responses
            # (e.g. channel_id for posting, thread_ts for replying)
            if trigger_event.input_data:
                payload_summary = {
                    k: v for k, v in trigger_event.input_data.items()
                    if k in ("channel_id", "channel", "text", "thread_ts", "ts",
                             "subject", "body", "id", "status", "intended_for")
                }
                if payload_summary:
                    trigger_info["payload"] = payload_summary
            # Include response data (contains ts for replies, entity IDs, etc.)
            if trigger_event.response_body:
                resp_summary = {
                    k: v for k, v in trigger_event.response_body.items()
                    if k in ("ts", "channel", "ok", "id", "status", "message")
                    and k != "_event"
                }
                if resp_summary:
                    trigger_info["response"] = resp_summary
            if trigger_event.post_state:
                trigger_info["result"] = trigger_event.post_state
            sections.append(f"### Trigger Event\n{json.dumps(trigger_info, indent=2)}")

        # Available actions
        if available_actions:
            action_lines = []
            for action in available_actions:
                name = action.get("name", "?")
                service = action.get("service", "")
                desc = action.get("description", "")
                required = action.get("required_params", [])
                params_str = f" — required: {', '.join(required)}" if required else ""
                action_lines.append(f"- {name} (service: {service}): {desc}{params_str}")
            sections.append(
                "### Available Actions\n"
                "Use `action_type` = the action name, `target_service` = the service name.\n"
                "Include ALL required parameters in `payload`.\n"
                + "\n".join(action_lines)
            )

        # Output instruction
        sections.append(
            "### Instructions\n"
            "Choose ONE action or 'do_nothing'. Respond with JSON matching"
            " the output schema.\n"
            "When posting a message, include 'intended_for' in your payload with"
            " a list of actor roles you're addressing"
            " (e.g. ['oceanographer'] or ['all']).\n"
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
            action_lines = []
            for a in available_actions:
                required = a.get("required_params", [])
                params_str = f" — required: {', '.join(required)}" if required else ""
                action_lines.append(
                    f"- {a.get('name', '?')} (service: {a.get('service', '')}): "
                    f"{a.get('description', '')}{params_str}"
                )
            sections.append(
                "### Available Actions\n"
                "Use `action_type` = the action name, `target_service` = the service name.\n"
                "Include ALL required parameters in `payload`.\n"
                + "\n".join(action_lines)
            )

        sections.append(f"### Output Schema\n{json.dumps(BATCH_OUTPUT_SCHEMA, indent=2)}")

        return "\n\n".join(sections)
