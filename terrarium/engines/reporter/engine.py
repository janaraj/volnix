"""Report generator engine implementation.

Produces scorecards, capability gap logs, causal traces, counterfactual
diffs, and comprehensive reports for evaluation runs.
"""

from __future__ import annotations

from typing import Any, ClassVar

from terrarium.core import BaseEngine, Event, EventId, WorldId


class ReportGeneratorEngine(BaseEngine):
    """Report generation engine for evaluation diagnostics."""

    engine_name: ClassVar[str] = "reporter"
    subscriptions: ClassVar[list[str]] = ["simulation"]
    dependencies: ClassVar[list[str]] = ["state"]

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Handle an inbound event from the bus."""
        ...

    # -- Reporter operations ---------------------------------------------------

    async def generate_scorecard(self, world_id: WorldId) -> dict[str, Any]:
        """Generate a summary scorecard for a world."""
        ...

    async def generate_gap_log(self, world_id: WorldId) -> list[dict[str, Any]]:
        """Generate a log of all capability gaps encountered."""
        ...

    async def generate_causal_trace(self, event_id: EventId) -> dict[str, Any]:
        """Generate a causal trace rooted at the given event."""
        ...

    async def generate_diff(self, run_ids: list[str]) -> dict[str, Any]:
        """Generate a counterfactual diff between multiple runs."""
        ...

    async def generate_full_report(self, world_id: WorldId) -> dict[str, Any]:
        """Generate a comprehensive report combining all diagnostics."""
        ...

    async def generate_condition_report(self, world_id: WorldId) -> dict[str, Any]:
        """Generate two-direction observation report.

        Direction 1 (world -> agent): How the agent handled world challenges
        (threats, bad data, failures, ambiguity).

        Direction 2 (agent -> world): How the agent's own behavior tested
        world boundaries (data access, information handling, authority, probing).
        """
        ...
