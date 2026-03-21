"""Capability gap analysis -- classifies and summarises gap events."""

from __future__ import annotations

from typing import Any

from terrarium.core import GapResponse


class GapAnalyzer:
    """Analyses capability gap events and classifies responses."""

    async def analyze(self, events: list[Any]) -> list[dict[str, Any]]:
        """Analyze events and return a list of capability gap records."""
        ...

    def _classify_response(
        self, gap_event: Any, following_events: list[Any]
    ) -> GapResponse:
        """Classify how the system responded to a capability gap."""
        ...

    async def get_gap_summary(self, events: list[Any]) -> dict[str, Any]:
        """Return an aggregate summary of all capability gaps."""
        ...
