"""Causal trace renderer -- formats causal chains for reports.

NOTE: Uses StateEngineProtocol (not direct CausalGraph import) to respect
engine isolation. The reporter never imports from engines/state/ directly.
"""

from __future__ import annotations

from typing import Any

from terrarium.core.types import EventId
from terrarium.core.protocols import StateEngineProtocol


class CausalTraceRenderer:
    """Renders causal traces from the causal graph into report format.

    Depends on StateEngineProtocol for causal chain queries, not on the
    concrete CausalGraph class. This maintains engine isolation.
    """

    async def render(
        self, event_id: EventId, state: StateEngineProtocol
    ) -> dict[str, Any]:
        """Render a causal trace rooted at the given event."""
        ...

    def _format_chain(self, events: list[Any]) -> list[dict[str, Any]]:
        """Format a chain of events for report output."""
        ...
