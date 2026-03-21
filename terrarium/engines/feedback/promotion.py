"""Tier promotion logic -- evaluates candidates for fidelity tier changes."""

from __future__ import annotations

from typing import Any

from terrarium.core import ServiceId


class TierPromoter:
    """Evaluates and proposes fidelity tier promotions for services."""

    async def evaluate_candidate(
        self, service_id: ServiceId, run_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Evaluate whether a service is ready for tier promotion."""
        ...

    async def extract_profile_draft(
        self, service_id: ServiceId, interactions: list[Any]
    ) -> dict[str, Any]:
        """Extract a draft service profile from observed interactions."""
        ...

    async def get_promotion_candidates(self) -> list[dict[str, Any]]:
        """Return all services that are candidates for promotion."""
        ...
