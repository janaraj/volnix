"""External sync checker -- detects drift between profiles and real APIs.

**G4b scope** — not yet implemented.  This module will be filled in
during the G4b phase (External Source Sync + Ecosystem Signals).

Planned functionality:
- Context Hub docs updated → detect drift → propose profile update
- OpenAPI spec version changed → flag for review
- MCP server manifest updated → check for new tools
"""
from __future__ import annotations

from typing import Any

from terrarium.core import ServiceId


class ExternalSyncChecker:
    """Detects drift between simulated profiles and real-world APIs.

    Not yet implemented — placeholder for G4b.
    All methods return empty/None results.
    """

    async def check_drift(
        self,
        service_id: ServiceId | str,
        current_profile: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Check for drift and return a report, or ``None`` if in sync."""
        return None

    async def fetch_external_spec(
        self, service_id: ServiceId | str
    ) -> dict[str, Any] | None:
        """Fetch the external API specification for a service."""
        return None

    async def propose_update(
        self,
        service_id: ServiceId | str,
        drift: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Propose a profile update to address detected drift."""
        return None
