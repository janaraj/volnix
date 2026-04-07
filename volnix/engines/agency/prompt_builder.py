"""ActorPromptBuilder -- assembles per-actor LLM prompts.

Domain-agnostic. Combines actor-specific context (persona, state, trigger)
with the shared WorldContextBundle system prompt. Supports both individual
and batch prompt formats.
"""

from __future__ import annotations

import json
from typing import Any

from volnix.actors.state import ActorState, InteractionRecord
from volnix.core.events import WorldEvent
from volnix.simulation.world_context import WorldContextBundle

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
        """Return the shared world system prompt without tools.

        Tools are rendered per-actor in the user prompt, filtered by
        the actor's service permissions.
        """
        return self._world_context.to_system_prompt(include_tools=False)

    def build_individual_prompt(
        self,
        actor: ActorState,
        trigger_event: WorldEvent | None,
        activation_reason: str,
        available_actions: list[dict[str, Any]],
        team_roster: list[dict[str, str]] | None = None,
        allowed_services: set[str] | None = None,
        simulation_progress: tuple[int, int] | None = None,
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
                team_lines.append(f"\nTeam channel: `{actor.team_channel}`")
            sections.append("\n".join(team_lines))

        # --- 3. Instructions (before tools/state — shapes LLM intent early) ---
        if actor.actor_type == "observer":
            sections.append(
                "## Instructions\n"
                "You are an OBSERVER. You can READ and ANALYZE data but CANNOT "
                "create, update, or delete anything. Only use read actions."
            )
        elif actor.autonomous:
            sections.append(
                self.build_autonomous_instructions(
                    actor,
                    team_roster,
                    activation_reason,
                    simulation_progress,
                )
            )
        else:
            sections.append(
                "## Instructions\n"
                "Choose ONE action or 'do_nothing'. Respond with JSON.\n"
                "For messages: only provide `text` in payload — the system "
                "auto-fills `channel_id`.\n"
                "Use `intended_for` to address teammates by role."
            )

        # --- 3b. Per-actor filtered tools (text prompt) ---
        # Only rendered when explicitly requested via allowed_services.
        # When native tool calling is used, tools are passed via ToolDefinition
        # objects on the LLM request — not duplicated in the text prompt.
        if allowed_services is not None:
            tools_text = self._world_context.render_tools_for_services(allowed_services)
            if tools_text:
                sections.append(tools_text)

        # --- 4. Context ---
        context_parts = []

        # Team mission (shared across all agents)
        if actor.current_goal:
            context_parts.append(f"### Team Mission\n{actor.current_goal}")

        # Goal context (role-specific focus)
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
            context_parts.append(self._build_action_history(actor, available_actions))

        # Recent activity (what the team has been doing)
        if actor.recent_interactions:
            context_parts.append(self._build_recent_activity(actor))

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
    def build_autonomous_instructions(
        actor: ActorState,
        team_roster: list[dict[str, str]] | None,
        activation_reason: str = "",
        simulation_progress: tuple[int, int] | None = None,
    ) -> str:
        """Build instructions for autonomous agents.

        For lead agents, instructions are phase-aware:
        - Phase 1 (Kickoff): first activation → delegate tasks
        - Phase 2 (Monitor): re-activation → validate, direct, assist
        - Phase 3 (Buffer): request_findings → wrap up, gather final findings
        Non-lead agents get standard INVESTIGATE/SHARE/ACT instructions.
        """
        is_reactivation = bool(actor.activation_messages)
        team_size = len(team_roster) if team_roster else 1
        team_note = ""
        if team_size > 1:
            team_note = (
                f"You are part of a team of {team_size} working together.\n"
                "- Leverage teammates' expertise — ask questions, request analysis\n"
                "- Read what teammates shared in Recent Activity and build on it\n"
                "- Use `intended_for` to address specific teammates by role\n\n"
            )

        lead_note = ""
        if actor.is_lead and team_size > 1:
            if activation_reason == "request_findings":
                # Phase 3: Buffer & Wrap-up
                lead_note = (
                    "**CRITICAL: BUFFER PERIOD — The simulation is nearing its end.**\n"
                    "- Instruct ALL sub-agents to STOP starting new investigations.\n"
                    "- Command them to finalize current tasks and share final findings NOW.\n"
                    "- Begin synthesizing the overall situation from what has been shared.\n"
                    "- Address each team member by role with specific wrap-up instructions.\n\n"
                )
            elif not is_reactivation:
                # Phase 1: Kickoff & Delegation
                lead_note = (
                    "**You are the team lead. Your role is orchestration, "
                    "validation, and synthesis — NOT deep investigation.**\n\n"
                    "Start by posting a delegation message in the team channel:\n"
                    "- Assign specific tasks to each team member by role.\n"
                    "- Set expectations: what to investigate, what to report back.\n"
                    "- You may do a brief overview (1-2 reads) but do NOT investigate deeply.\n"
                    "- After delegating, call `do_nothing` to wait for your team's findings.\n\n"
                )
            else:
                # Phase 2: Active Monitoring & Coordination
                lead_note = (
                    "**You have already delegated. Your job is Active Monitoring:**\n"
                    "- Review the new findings shared by your team below.\n"
                    "- VALIDATE: Are their findings complete and accurate?\n"
                    "- DIRECT: If a finding is incomplete, ask that agent to dig deeper.\n"
                    "- ASSIGN: If new events or tickets arrived, delegate them immediately.\n"
                    "- Do NOT investigate on your own — rely on your team to gather data.\n"
                    "- Share a brief status synthesis if you have enough information.\n\n"
                )

        # Simulation state (lead only — provides budget awareness)
        sim_state = ""
        if actor.is_lead and simulation_progress:
            current, total = simulation_progress
            pct = int(current / total * 100) if total > 0 else 0
            sim_state = f"## Simulation State\n{current}/{total} events processed ({pct}%)\n\n"

        # Steps: lead gets DELEGATE/MONITOR/VALIDATE, non-lead gets INVESTIGATE/SHARE/ACT
        if actor.is_lead and team_size > 1:
            steps = [
                "DELEGATE: Assign tasks and set reporting expectations.",
                "MONITOR: Read team updates in the channel.",
                "VALIDATE: Check findings for accuracy and completeness.",
                "ASSIST: Provide guidance if sub-agents are stuck or blocked.",
                "SYNTHESIZE: When findings are sufficient, share your synthesis.",
                "If nothing new to act on: call the `do_nothing` tool.",
            ]
        else:
            steps = [
                "INVESTIGATE. Read relevant data to understand the situation.",
                "SHARE your findings. Post a summary in the team channel so the lead and teammates can see what you learned.",
                "ACT on what you find. Update records, process requests, post updates — whatever the mission requires.",
            ]
            if team_size > 1:
                steps.append("RESPOND to teammates. Messages marked [TO YOU] need your response.")
            steps.append(
                "NO REPETITION. Check Your Action History — don't re-query or re-do completed work."
            )
            steps.append("Track progress via state_updates.pending_tasks and goal_context.")
            steps.append("If nothing new to add: call the `do_nothing` tool.")

        numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))

        return (
            "## Instructions\n"
            f"{team_note}"
            f"{lead_note}"
            f"{sim_state}"
            "The world's services contain real data. Use the available tools to carry out your mission.\n\n"
            f"{numbered}\n\n"
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
            a.get("name", ""): a.get("http_method", "POST").upper() for a in available_actions
        }

        own = [r for r in actor.recent_interactions if r.source == "self"]
        if not own and not actor.pending_actions:
            return "### Your Action History\nNo actions taken yet."

        queries = []
        messages = []
        other = []
        for r in own:
            method = method_lookup.get(r.action, "POST")
            entry = r.summary
            if r.response_summary:
                entry += f" → {r.response_summary[:150]}"
            if method == "GET":
                queries.append(entry)
            elif r.action in (
                "chat.postMessage",
                "chat.replyToThread",
                "chat.update",
                "email_send",
            ):
                messages.append(r.summary)
            else:
                other.append(r.summary)

        lines = ["### Your Action History"]
        if actor.pending_actions:
            lines.append(f"- In progress: {', '.join(actor.pending_actions)}")
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
        """Build recent interaction history split into own work and team messages."""
        records = actor.recent_interactions[-10:]
        if not records:
            return ""

        own = [r for r in records if isinstance(r, InteractionRecord) and r.source == "self"]
        team = [r for r in records if isinstance(r, InteractionRecord) and r.source != "self"]
        other = [r for r in records if not isinstance(r, InteractionRecord)]

        lines: list[str] = []

        # Backward compat: plain strings from older code paths
        for r in other:
            lines.append(f"- {r}")

        if own:
            lines.append("### Your Investigation")
            for r in own:
                result_tag = ""
                if r.response_summary:
                    result_tag = f"\n  → {r.response_summary[:200]}"
                lines.append(f"- [tick {r.tick}] {r.action}: {r.summary}{result_tag}")

        if team:
            lines.append("### Team Messages")
            for r in team:
                addressed_tag = ""
                if r.intended_for:
                    if actor.role in r.intended_for or "all" in r.intended_for:
                        addressed_tag = " [TO YOU]"
                    else:
                        addressed_tag = f" [to: {', '.join(r.intended_for)}]"
                channel_tag = f" in {r.channel}" if r.channel else ""
                reply_tag = f" (reply to {r.reply_to})" if r.reply_to else ""
                lines.append(
                    f"- [tick {r.tick}] {r.actor_role}:{addressed_tag} "
                    f'"{r.summary}"{channel_tag}{reply_tag}'
                )

        return "\n".join(lines) if lines else ""

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
            "## Trigger",
            f"**{trigger_event.actor_id}** performed `{trigger_event.action}`"
            f" on `{trigger_event.service_id}`",
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
                text = trigger_event.input_data.get("text") or trigger_event.action
                preview = (text[:200] + "...") if len(text) > 200 else text
                actor_section.append(
                    f"Trigger: {trigger_event.actor_id} → {trigger_event.action}: {preview}"
                )
            if actor.current_goal:
                actor_section.append(f"Goal: {actor.current_goal}")
            sections.append("\n".join(actor_section))

        sections.append(f"Respond with JSON: {json.dumps(BATCH_OUTPUT_SCHEMA, indent=2)}")
        return "\n\n".join(sections)
