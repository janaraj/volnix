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

# Compact output example shown to LLM (replaces verbose JSON Schema)
OUTPUT_EXAMPLE = """{
  "action_type": "tool_name or do_nothing",
  "target_service": "service_name",
  "payload": { "param": "value" },
  "reasoning": "why this action",
  "intended_for": ["role_name"],
  "state_updates": {
    "goal_context": "updated progress notes",
    "pending_tasks": ["remaining task 1", "remaining task 2"]
  }
}"""

# Full schema kept for batch prompts and backward compat
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

# Keep ACTION_OUTPUT_SCHEMA for _parse_llm_action compatibility
ACTION_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action_type": {"type": "string"},
        "target_service": {"type": ["string", "null"]},
        "payload": {"type": "object"},
        "reasoning": {"type": "string"},
        "state_updates": {
            "type": "object",
            "properties": {
                "pending_tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "goal_context": {"type": ["string", "null"]},
            },
        },
        "intended_for": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["action_type", "reasoning"],
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
        team_roster: list[dict[str, str]] | None = None,
    ) -> str:
        """Build per-actor user prompt.

        Section order designed for LLM comprehension:
        1. Identity (who am I)
        2. Team + channel (who else, where we talk)
        3. Instructions (what to do — BEFORE tools/state)
        4. Context (goal, tasks, action history, recent activity)
        5. Trigger (what activated me, if any)
        6. Output format (compact example)
        """
        sections: list[str] = []

        # --- 1. Identity ---
        persona_desc = ""
        if actor.persona:
            persona_desc = actor.persona.get("description", "")
            if not persona_desc:
                persona_desc = json.dumps(actor.persona)
        identity = f"## You are: {actor.role} (ID: {actor.actor_id})"
        if persona_desc:
            identity += f"\n{persona_desc}"
        sections.append(identity)

        # --- 2. Team + channel ---
        if team_roster:
            team_lines = ["## Your Team"]
            for member in team_roster:
                if member["role"] != actor.role:
                    team_lines.append(f"- **{member['role']}** (ID: {member['id']})")
            # Show team channel for autonomous agents
            if actor.autonomous and actor.team_channel:
                team_lines.append(
                    f"\nTeam channel: `{actor.team_channel}`"
                )
            sections.append("\n".join(team_lines))

        # --- 3. Instructions (before tools/state — shapes LLM intent early) ---
        if actor.actor_type == "observer":
            sections.append(
                "## Instructions\n"
                "You are an OBSERVER. You can READ and ANALYZE data but CANNOT "
                "create, update, or delete anything. Only use read actions."
            )
        elif actor.autonomous:
            sections.append(self._build_autonomous_instructions(actor, team_roster))
        else:
            sections.append(
                "## Instructions\n"
                "Choose ONE action or 'do_nothing'. Respond with JSON.\n"
                "For messages: only provide `text` in payload — the system "
                "auto-fills `channel_id`.\n"
                "Use `intended_for` to address teammates by role."
            )

        # --- 4. Context ---
        context_parts = []

        # Goal context
        context_parts.append(
            f"### Mission Context\n"
            f"{actor.goal_context or 'Not set — update via state_updates.goal_context'}"
        )

        # Pending tasks
        if actor.pending_tasks:
            task_lines = ["### Pending Tasks"]
            for i, task in enumerate(actor.pending_tasks, 1):
                task_lines.append(f"{i}. {task}")
            context_parts.append("\n".join(task_lines))

        # Action history (anti-repetition: shows what agent already did)
        if actor.autonomous:
            context_parts.append(
                self._build_action_history(actor, available_actions)
            )

        # Recent activity (what the team has been doing)
        if actor.recent_interactions:
            context_parts.append(
                self._build_recent_activity(actor)
            )

        if context_parts:
            sections.append("## What You Know\n\n" + "\n\n".join(context_parts))

        # --- 5. Trigger ---
        if trigger_event:
            sections.append(self._build_trigger(trigger_event))
        elif activation_reason:
            sections.append(f"## Trigger: {activation_reason}")

        # --- 6. Output format ---
        sections.append(
            "## Output\n"
            "Call one of the available tools to take action, or call `do_nothing` to skip.\n"
            "Include `reasoning` to explain your choice.\n"
            "Use `intended_for` to address teammates by role (e.g. ['analyst'] or ['all']).\n"
            "Use `state_updates` to track your progress:\n"
            "  - `goal_context`: updated notes on what you've learned\n"
            "  - `pending_tasks`: remaining work items"
        )

        return "\n\n".join(sections)

    # -- Helper methods --

    @staticmethod
    def _build_autonomous_instructions(
        actor: ActorState,
        team_roster: list[dict[str, str]] | None,
    ) -> str:
        """Build instructions for autonomous agents."""
        team_size = len(team_roster) if team_roster else 1
        team_note = ""
        if team_size > 1:
            team_note = (
                f"You are part of a team of {team_size} working together.\n"
                "- Leverage teammates' expertise — ask questions, request analysis\n"
                "- Read what teammates shared in Recent Activity and build on it\n"
                "- Use `intended_for` to address teammates by role or 'all'\n\n"
            )

        return (
            "## Instructions\n"
            f"{team_note}"
            "The world's services contain real data generated during world creation.\n"
            "Your job is to QUERY these services and share findings with the team.\n\n"
            "1. QUERY before you speak. Use READ tools to find actual data from services.\n"
            "2. SHARE facts, not plans. Post specific data you found (numbers, quotes, dates).\n"
            "3. RESPOND to teammates. Messages marked [TO YOU] need your response.\n"
            "4. NO REPETITION. Check Your Action History. Don't re-query or re-state.\n"
            "5. Track progress via state_updates.pending_tasks and goal_context.\n"
            "6. If nothing new to add: call the `do_nothing` tool.\n\n"
            "For messages: only provide `text` in payload — the system auto-fills `channel_id`."
        )

    @staticmethod
    def _build_action_history(
        actor: ActorState,
        available_actions: list[dict[str, Any]],
    ) -> str:
        """Build summary of agent's own actions (anti-repetition)."""
        # Build lookup: tool name → http_method
        method_lookup = {
            a.get("name", ""): a.get("http_method", "POST").upper()
            for a in available_actions
        }

        own = [r for r in actor.recent_interactions if r.source == "self"]
        if not own:
            return "### Your Action History\nNo actions taken yet."

        queries = []
        messages = []
        other = []
        for r in own:
            method = method_lookup.get(r.action, "POST")
            if method == "GET":
                queries.append(r.action)
            elif r.action in ("chat.postMessage", "chat.replyToThread",
                              "chat.update", "email_send"):
                messages.append(r.action)
            else:
                other.append(r.action)

        lines = ["### Your Action History"]
        if queries:
            lines.append(f"- Queries: {len(queries)} ({', '.join(queries)})")
        if messages:
            lines.append(f"- Messages: {len(messages)} ({', '.join(messages)})")
        if other:
            lines.append(f"- Other: {len(other)} ({', '.join(other)})")
        lines.append(f"- Total: {len(own)}")
        return "\n".join(lines)

    @staticmethod
    def _build_recent_activity(actor: ActorState) -> str:
        """Build recent interaction history with full text and addressing."""
        lines = ["### Recent Activity"]
        for record in actor.recent_interactions[-10:]:
            if not isinstance(record, InteractionRecord):
                lines.append(f"- {record}")
                continue

            channel_tag = f" in {record.channel}" if record.channel else ""
            reply_tag = f" (reply to {record.reply_to})" if record.reply_to else ""

            # Show if addressed to this agent
            addressed_tag = ""
            if record.intended_for:
                if actor.role in record.intended_for or "all" in record.intended_for:
                    addressed_tag = " [TO YOU]"
                else:
                    addressed_tag = f" [to: {', '.join(record.intended_for)}]"

            if record.source == "self":
                lines.append(
                    f"- [tick {record.tick}] You: "
                    f'"{record.summary}"{channel_tag}{reply_tag}'
                )
            else:
                lines.append(
                    f"- [tick {record.tick}] {record.actor_role}: "
                    f'"{record.summary}"{channel_tag}'
                    f"{addressed_tag}{reply_tag}"
                )
        return "\n".join(lines)

    @staticmethod
    def _build_trigger(trigger_event: WorldEvent) -> str:
        """Build trigger section from a WorldEvent."""
        text = (
            trigger_event.input_data.get("text")
            or trigger_event.input_data.get("body")
            or trigger_event.input_data.get("content")
            or trigger_event.action
        )
        channel = (
            trigger_event.input_data.get("channel_id")
            or trigger_event.input_data.get("channel")
            or ""
        )

        trigger_lines = [
            f"## Trigger",
            f"**{trigger_event.actor_id}** performed `{trigger_event.action}`"
            f" on `{trigger_event.service_id}`"
        ]
        if channel:
            trigger_lines[-1] += f" in `{channel}`"
        if text and len(text) > 10:
            preview = text[:500] + ("..." if len(text) > 500 else "")
            trigger_lines.append(f"> {preview}")
        intended = trigger_event.input_data.get("intended_for", [])
        if intended:
            trigger_lines.append(f"Addressed to: **{', '.join(intended)}**")

        return "\n".join(trigger_lines)

    def build_batch_prompt(
        self,
        actors_with_triggers: list[tuple[ActorState, WorldEvent | None, str]],
        available_actions: list[dict[str, Any]],
    ) -> str:
        """Build batch prompt for multiple actors in one LLM call.

        Each actor gets a summary section. The LLM generates actions for all.
        """
        sections: list[str] = []

        for actor, trigger_event, reason in actors_with_triggers:
            actor_section = [
                f"### Actor: {actor.role} (ID: {actor.actor_id})",
                f"Activation: {reason}",
            ]
            if trigger_event:
                text = (
                    trigger_event.input_data.get("text")
                    or trigger_event.action
                )
                preview = (text[:200] + "...") if len(text) > 200 else text
                actor_section.append(
                    f"Trigger: {trigger_event.actor_id} → "
                    f"{trigger_event.action}: {preview}"
                )
            if actor.current_goal:
                actor_section.append(f"Goal: {actor.current_goal}")
            sections.append("\n".join(actor_section))

        sections.append(
            f"Respond with JSON: {json.dumps(BATCH_OUTPUT_SCHEMA, indent=2)}"
        )
        return "\n\n".join(sections)
