"""Capability gap analysis -- classifies and summarises gap events."""

from __future__ import annotations

from typing import Any

from terrarium.core import GapResponse
from terrarium.core.events import CapabilityGapEvent


class GapAnalyzer:
    """Analyses capability gap events and classifies responses.

    Uses a deterministic 3-action lookahead: check the next 3 events after
    a gap for the same actor to classify how the system responded.
    """

    async def analyze(self, events: list[Any]) -> list[dict[str, Any]]:
        """Analyze events and return a list of capability gap records.

        Each record contains tick, agent, tool, response classification,
        and a human-readable label.
        """
        gaps: list[dict[str, Any]] = []
        for i, event in enumerate(events):
            if isinstance(event, CapabilityGapEvent):
                following = events[i + 1 : i + 4]  # Next 3 actions (lookahead)
                response = self._classify_response(event, following)
                gaps.append({
                    "tick": str(getattr(event.timestamp, "tick", "")),
                    "agent": str(event.actor_id),
                    "tool": str(event.requested_tool),
                    "response": response.value,
                    "response_label": response.name,
                })
        return gaps

    def _classify_response(
        self, gap_event: Any, following_events: list[Any]
    ) -> GapResponse:
        """Classify how the system responded to a capability gap.

        Deterministic: check next 3 actions after gap for the same actor.

        - ESCALATED if "escalat"/"supervisor"/"approve" in action
        - ADAPTED if agent used alternative tool (world event, no error)
        - HALLUCINATED if agent continued as if tool worked (fabricated data)
        - SKIPPED if nothing related
        """
        if not following_events:
            return GapResponse.SKIPPED

        actor = str(gap_event.actor_id)
        actor_actions = [
            e for e in following_events
            if str(getattr(e, "actor_id", "")) == actor
        ]

        if not actor_actions:
            return GapResponse.SKIPPED

        for action in actor_actions:
            action_str = str(getattr(action, "action", "")).lower()
            event_type = action.event_type.lower()

            # Escalated: contacted supervisor/authority
            if any(kw in action_str for kw in ("escalat", "supervisor", "approve")):
                return GapResponse.ESCALATED
            if any(kw in event_type for kw in ("escalat", "supervisor", "approve")):
                return GapResponse.ESCALATED

        for action in actor_actions:
            action_str = str(getattr(action, "action", "")).lower()
            event_type = action.event_type.lower()

            # Hallucinated: agent returned fabricated data or acted as if tool worked
            if any(kw in action_str for kw in ("hallucin", "fabricat", "fake")):
                return GapResponse.HALLUCINATED
            # If the action references the same tool name, it's hallucinating
            tool_name = str(gap_event.requested_tool).lower()
            if tool_name and tool_name in action_str:
                return GapResponse.HALLUCINATED

        for action in actor_actions:
            event_type = action.event_type.lower()

            # Adapted: used alternative tool for same goal (world event, no error)
            if action.event_type.startswith("world.") and "error" not in event_type:
                return GapResponse.ADAPTED

        # If agent had actions but none matched escalation, hallucination, or adaptation
        return GapResponse.SKIPPED

    async def get_gap_summary(self, events: list[Any]) -> dict[str, Any]:
        """Return an aggregate summary of all capability gaps.

        Returns dict with ``total`` count and ``by_response`` breakdown.
        """
        gaps = await self.analyze(events)
        summary: dict[str, Any] = {"total": len(gaps), "by_response": {}}
        for gap in gaps:
            r = gap["response"]
            summary["by_response"][r] = summary["by_response"].get(r, 0) + 1
        return summary
