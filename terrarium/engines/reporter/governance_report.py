"""Governance report generator — packages Mode 1 agent testing results.

Combines scorecard, capability gaps, world challenges, and agent
boundary analysis into one structured artifact. Uses EXISTING
reporter sub-components — no new computation, just packaging.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class GovernanceReportGenerator:
    """Produces the Mode 1 "report card" for external agent testing.

    Aggregates outputs from existing reporter sub-components into
    a single structured artifact suitable for the dashboard and
    API consumers.
    """

    def __init__(
        self,
        scorecard_computer: Any,
        gap_analyzer: Any,
        challenge_analyzer: Any,
        boundary_analyzer: Any,
        conditions: Any = None,
    ) -> None:
        self._scorecard = scorecard_computer
        self._gaps = gap_analyzer
        self._challenges = challenge_analyzer
        self._boundaries = boundary_analyzer
        self._conditions = conditions

    async def generate(
        self,
        events: list[Any],
        actors: list[Any],
    ) -> dict[str, Any]:
        """Generate comprehensive governance report.

        Args:
            events: Full event timeline from the run.
            actors: Actor definitions (list of dicts or ActorDefinition objects).

        Returns:
            Structured artifact with sections: summary, scorecard,
            capability_gaps, world_challenges, agent_boundaries.
        """
        scorecard = await self._scorecard.compute(events, actors)
        gaps = await self._gaps.analyze(events)
        gap_summary = await self._gaps.get_gap_summary(events)

        # Challenges and boundaries are per-actor — iterate and collect
        world_challenges: dict[str, Any] = {}
        agent_boundaries: dict[str, Any] = {}
        for actor in actors:
            actor_id = actor.get("id", "") if isinstance(actor, dict) else getattr(actor, "id", "")
            if not actor_id:
                continue
            try:
                challenges = await self._challenges.analyze(
                    events, actor_id, self._conditions,
                )
                world_challenges[str(actor_id)] = [
                    c.model_dump() if hasattr(c, "model_dump") else c
                    for c in challenges
                ]
            except Exception:
                world_challenges[str(actor_id)] = []

            try:
                boundaries = await self._boundaries.analyze(events, actor_id)
                agent_boundaries[str(actor_id)] = [
                    b.model_dump() if hasattr(b, "model_dump") else b
                    for b in boundaries
                ]
            except Exception:
                agent_boundaries[str(actor_id)] = []

        # Count external agent actions
        world_events = [
            e for e in events
            if (e.get("event_type", "") if isinstance(e, dict)
                else getattr(e, "event_type", "")).startswith("world.")
        ]
        external_actors = [
            a for a in actors
            if (a.get("type") if isinstance(a, dict) else getattr(a, "type", ""))
            in ("agent", "external")
        ]

        return {
            "type": "governance_report",
            "summary": {
                "total_actions": len(world_events),
                "external_actors": len(external_actors),
                "overall_score": scorecard.get("collective", {}).get(
                    "overall_score"
                ),
                "total_gaps": len(gaps),
            },
            "scorecard": scorecard,
            "capability_gaps": {
                "gaps": gaps,
                "summary": gap_summary,
            },
            "world_challenges": world_challenges,
            "agent_boundaries": agent_boundaries,
        }
