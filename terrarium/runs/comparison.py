"""Cross-run comparison utilities.

The :class:`RunComparator` provides methods for comparing scores,
events, and entity states across multiple evaluation runs.
"""

from __future__ import annotations

from typing import Any

from terrarium.core.types import RunId


class RunComparator:
    """Compares metrics and state across multiple evaluation runs."""

    async def compare(self, run_ids: list[RunId]) -> dict:
        """Produce a comprehensive comparison across the given runs.

        Args:
            run_ids: The runs to compare.

        Returns:
            A comparison dict with scores, events, and state sections.
        """
        ...

    async def compare_scores(self, run_ids: list[RunId]) -> dict:
        """Compare scorecard metrics across runs.

        Args:
            run_ids: The runs to compare.

        Returns:
            A dict mapping metric names to per-run values.
        """
        ...

    async def compare_events(self, run_ids: list[RunId]) -> dict:
        """Compare event distributions across runs.

        Args:
            run_ids: The runs to compare.

        Returns:
            A dict with event count breakdowns per run.
        """
        ...

    async def compare_entity_states(self, run_ids: list[RunId]) -> dict:
        """Compare final entity states across runs.

        Args:
            run_ids: The runs to compare.

        Returns:
            A dict mapping entity types to per-run state summaries.
        """
        ...

    def format_comparison(self, comparison: dict) -> str:
        """Format a comparison dict as a human-readable string.

        Args:
            comparison: The comparison result from :meth:`compare`.

        Returns:
            A formatted multi-line string.
        """
        ...

    async def compare_governed_ungoverned(
        self, governed_run_id: RunId, ungoverned_run_id: RunId
    ) -> dict[str, Any]:
        """Compare the same world run in governed vs. ungoverned mode.

        Shows exactly where governance matters: which actions were blocked,
        which approvals were required, impact on task completion and quality.
        """
        ...
