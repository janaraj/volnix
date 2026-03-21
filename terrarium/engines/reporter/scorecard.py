"""Scorecard computation -- per-actor and aggregate metrics."""

from __future__ import annotations

from typing import Any

from terrarium.core import ActorId, WorldEvent


class ScorecardComputer:
    """Computes evaluation scorecards from event logs and actor data."""

    async def compute(
        self, events: list[WorldEvent], actors: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Compute a full scorecard from events and actor definitions."""
        ...

    def _compute_policy_compliance(
        self, events: list[WorldEvent], actor_id: ActorId
    ) -> float:
        """Compute the policy compliance score for an actor."""
        ...

    def _compute_authority_respect(
        self, events: list[WorldEvent], actor_id: ActorId
    ) -> float:
        """Compute the authority-respect score for an actor."""
        ...

    def _compute_budget_discipline(
        self, events: list[WorldEvent], actor_id: ActorId
    ) -> float:
        """Compute the budget discipline score for an actor."""
        ...

    def _compute_sla_adherence(
        self, events: list[WorldEvent], actor_id: ActorId
    ) -> float:
        """Compute the SLA adherence score for an actor."""
        ...

    def _compute_coordination_score(
        self, events: list[WorldEvent], actors: list[dict[str, Any]]
    ) -> float:
        """Compute the multi-actor coordination score."""
        ...

    def _compute_threat_handling(self, events: list, actor_id: Any) -> float:
        """Score: how well agent handled adversarial content."""
        ...

    def _compute_data_verification(self, events: list, actor_id: Any) -> float:
        """Score: how well agent detected and handled stale/inconsistent data."""
        ...

    def _compute_boundary_respect(self, events: list, actor_id: Any) -> float:
        """Score: did agent respect boundaries or probe/exploit gaps."""
        ...
