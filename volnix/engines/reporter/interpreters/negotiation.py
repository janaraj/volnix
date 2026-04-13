"""Negotiation domain interpreter — formats game events into post-mortem narrative."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


class NegotiationInterpreter:
    """Formats negotiation game activations into a structured post-mortem.

    Produces four narrative sections:

    1. **Deal Evolution** — term-by-term progression across game moves
    2. **Agent Behavior** — per-actor research effort and decision pattern
    3. **World Context** — animator/world events between agent turns
    4. **Outcome** — game result summary

    Only committed game-service actions are included in the deal evolution.
    Research/read actions contribute to the behavior summary.
    """

    def interpret(
        self,
        activations: list[dict[str, Any]],
        game_result: dict[str, Any] | None,
    ) -> list[str]:
        narrative: list[str] = []
        narrative.extend(self._deal_evolution(activations))
        narrative.extend(self._agent_summaries(activations))
        narrative.extend(self._world_context(activations))
        narrative.extend(self._outcome_analysis(game_result))
        return narrative

    def _deal_evolution(self, activations: list[dict[str, Any]]) -> list[str]:
        """Extract term progression across game moves."""
        lines: list[str] = []
        move_num = 0
        for act in activations:
            actor = act.get("actor_id", "?")
            for action in act.get("actions", []):
                if action.get("service") != "game" or not action.get("committed"):
                    continue
                move_num += 1
                tool = action.get("tool_name", "?")
                # Strip "game." prefix for readability
                move_name = tool.split(".")[-1] if "." in tool else tool
                # Strip "negotiate_" prefix
                if move_name.startswith("negotiate_"):
                    move_name = move_name[len("negotiate_"):]

                # Get terms from arguments (input_data scalars) or
                # effect.key_changes
                terms = action.get("arguments") or {}
                effect = action.get("effect") or {}
                changes = effect.get("key_changes", {})
                # Merge: arguments has the raw input, key_changes has
                # committed state delta — prefer arguments for full picture
                all_terms = {**changes, **terms}
                # Filter out non-term fields
                skip = {
                    "deal_id", "message", "reasoning",
                    "intended_for", "state_updates",
                }
                term_parts = []
                for k, v in all_terms.items():
                    if k in skip:
                        continue
                    if isinstance(v, float):
                        term_parts.append(f"{k}=${v:g}")
                    else:
                        term_parts.append(f"{k}={v}")

                line = f"Move {move_num} ({actor}): {move_name}"
                if term_parts:
                    line += " — " + ", ".join(term_parts)
                lines.append(line)

        if lines:
            lines.insert(0, "--- Deal Evolution ---")
        return lines

    def _agent_summaries(self, activations: list[dict[str, Any]]) -> list[str]:
        """Per-actor research effort and decision pattern."""
        stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "activations": 0,
                "reads": 0,
                "game_moves": 0,
                "services": set(),
            }
        )
        for act in activations:
            actor = act.get("actor_id", "?")
            stats[actor]["activations"] += 1
            for action in act.get("actions", []):
                svc = action.get("service", "")
                if svc:
                    stats[actor]["services"].add(svc)
                if action.get("learned") is not None:
                    stats[actor]["reads"] += 1
                if svc == "game" and action.get("committed"):
                    stats[actor]["game_moves"] += 1

        lines: list[str] = []
        for actor, s in stats.items():
            svcs = ", ".join(sorted(s["services"] - {"game"})) or "none"
            lines.append(
                f"{actor}: {s['activations']} activations, "
                f"{s['reads']} reads ({svcs}), "
                f"{s['game_moves']} game moves"
            )
        if lines:
            lines.insert(0, "--- Agent Behavior ---")
        return lines

    def _world_context(self, activations: list[dict[str, Any]]) -> list[str]:
        """Summarize world/animator events between agent turns."""
        total_world_events = 0
        event_types: set[str] = set()
        for act in activations:
            wr = act.get("world_response") or {}
            events = wr.get("other_agent_actions", [])
            events += wr.get("environment_changes", [])
            total_world_events += len(events)
            for ev in events:
                if isinstance(ev, dict):
                    t = ev.get("tool_name") or ev.get("action", "")
                    if t:
                        event_types.add(t)

        if total_world_events == 0:
            return []
        types_str = ", ".join(sorted(event_types)[:5]) or "various"
        return [
            "--- World Context ---",
            f"{total_world_events} world events between agent turns ({types_str})",
        ]

    def _outcome_analysis(
        self, game_result: dict[str, Any] | None
    ) -> list[str]:
        """Game result summary."""
        if not game_result:
            return []
        reason = game_result.get("reason", "?")
        winner = game_result.get("winner") or "none"
        total = game_result.get("total_events", "?")
        wall = game_result.get("wall_clock_seconds", 0)
        mode = game_result.get("scoring_mode", "?")
        wall_str = f"{wall:.0f}s" if isinstance(wall, (int, float)) else "?"
        return [
            "--- Outcome ---",
            f"{reason} in {total} moves ({wall_str}). "
            f"Winner: {winner}. Mode: {mode}.",
        ]
