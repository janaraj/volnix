"""Causal trace renderer -- formats causal chains for reports.

NOTE: Uses StateEngineProtocol (not direct CausalGraph import) to respect
engine isolation. The reporter never imports from engines/state/ directly.
"""

from __future__ import annotations

from typing import Any

from volnix.core.types import EventId
from volnix.core.protocols import StateEngineProtocol


class CausalTraceRenderer:
    """Renders causal traces from the causal graph into report format.

    Depends on StateEngineProtocol for causal chain queries, not on the
    concrete CausalGraph class. This maintains engine isolation.
    """

    async def render(
        self, event_id: EventId, state: StateEngineProtocol
    ) -> dict[str, Any]:
        """Render a causal trace rooted at the given event.

        Returns a dict with:
        - root_event: the event_id that was queried
        - causes: formatted chain of events that caused this event (backward)
        - effects: formatted chain of events caused by this event (forward)
        - chain_length: total number of events in the full chain
        """
        causes = await state.get_causal_chain(event_id, "backward")
        effects = await state.get_causal_chain(event_id, "forward")

        formatted_causes = self._format_chain(causes)
        formatted_effects = self._format_chain(effects)

        return {
            "root_event": str(event_id),
            "causes": formatted_causes,
            "effects": formatted_effects,
            "chain_length": len(formatted_causes) + len(formatted_effects),
        }

    def _format_chain(self, events: list[Any]) -> list[dict[str, Any]]:
        """Format a chain of events for report output.

        Each event is rendered as a dict with id, type, tick, actor, and action.
        """
        formatted: list[dict[str, Any]] = []
        for event in events:
            entry: dict[str, Any] = {
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "tick": getattr(event.timestamp, "tick", 0),
            }
            if hasattr(event, "actor_id"):
                entry["actor_id"] = str(event.actor_id)
            if hasattr(event, "action"):
                entry["action"] = event.action
            if hasattr(event, "target_entity") and event.target_entity:
                entry["target_entity"] = str(event.target_entity)
            formatted.append(entry)
        return formatted
