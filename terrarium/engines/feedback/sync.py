"""External sync checker -- detects drift between profiles and real APIs."""

from __future__ import annotations

from typing import Any

from terrarium.core import ServiceId


class ExternalSyncChecker:
    """Detects drift between simulated service profiles and real-world APIs."""

    async def check_drift(
        self, service_id: ServiceId, current_profile: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Check for drift and return a report, or ``None`` if in sync."""
        ...

    async def fetch_external_spec(
        self, service_id: ServiceId
    ) -> dict[str, Any] | None:
        """Fetch the external API specification for a service.

        Returns:
            The external spec dict, or ``None`` if unavailable.
        """
        ...

    async def propose_update(
        self, service_id: ServiceId, drift: dict[str, Any]
    ) -> dict[str, Any]:
        """Propose a profile update to address detected drift."""
        ...
