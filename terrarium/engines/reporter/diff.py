"""Counterfactual differ -- compares multiple simulation runs."""

from __future__ import annotations

from typing import Any

from terrarium.core import StateEngineProtocol


class CounterfactualDiffer:
    """Compares multiple simulation runs to highlight differences."""

    async def compare(
        self, run_ids: list[str], state: StateEngineProtocol
    ) -> dict[str, Any]:
        """Compare multiple runs and return a structured diff."""
        ...

    def _diff_scores(self, scorecards: list[dict[str, Any]]) -> dict[str, Any]:
        """Diff scorecard metrics across runs."""
        ...

    def _diff_events(
        self, event_logs: list[list[Any]]
    ) -> dict[str, Any]:
        """Diff event logs across runs."""
        ...

    def _diff_entity_states(
        self, states: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Diff final entity states across runs."""
        ...
