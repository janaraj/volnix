"""Report viewing dashboard routes.

Provides endpoints for viewing evaluation reports including
scorecards, gap logs, and causal traces.
"""

from __future__ import annotations


async def report_view(run_id: str) -> dict:
    """Render the full report page for a completed run.

    Args:
        run_id: The run to view.

    Returns:
        An HTML response with the report view.
    """
    ...


async def scorecard_view(run_id: str) -> dict:
    """Render the scorecard for a completed run.

    Args:
        run_id: The run to view.

    Returns:
        An HTML response with the scorecard.
    """
    ...


async def gap_log_view(run_id: str) -> dict:
    """Render the capability gap log for a completed run.

    Args:
        run_id: The run to view.

    Returns:
        An HTML response with the gap log.
    """
    ...


async def causal_trace_view(run_id: str, event_id: str) -> dict:
    """Render the causal trace rooted at a specific event.

    Args:
        run_id: The run containing the event.
        event_id: The root event for the causal trace.

    Returns:
        An HTML response with the causal trace visualisation.
    """
    ...
