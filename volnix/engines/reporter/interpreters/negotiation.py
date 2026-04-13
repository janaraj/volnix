"""Negotiation domain interpreter — formats game events into narrative lines."""
from __future__ import annotations

from typing import Any


class NegotiationInterpreter:
    """Formats negotiation game activations into one-line narrative strings.

    Only committed game-service actions are included (service == "game"
    and committed == True). Research/read actions are excluded — they
    appear in the activation detail, not the narrative.
    """

    def interpret(
        self,
        activations: list[dict[str, Any]],
        game_result: dict[str, Any] | None,
    ) -> list[str]:
        narrative: list[str] = []
        for act in activations:
            actor = act.get("actor_id", "?")
            for action in act.get("actions", []):
                if action.get("service") != "game":
                    continue
                if not action.get("committed"):
                    continue
                tool = action.get("tool_name", "?")
                effect = action.get("effect") or {}
                changes: dict[str, Any] = effect.get("key_changes", {})
                price = changes.get("unit_price") or changes.get("price") or "?"
                extras = ", ".join(
                    f"{k}={v}"
                    for k, v in changes.items()
                    if k not in ("unit_price", "price")
                )
                line = f"{actor}: {tool} at ${price}"
                if extras:
                    line += f" — {extras}"
                narrative.append(line)

        if game_result:
            reason = game_result.get("reason", "?")
            winner = game_result.get("winner") or "none"
            narrative.append(f"Outcome: {reason} (winner: {winner})")

        return narrative
