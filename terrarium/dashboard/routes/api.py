"""JSON API routes for the dashboard.

Provides programmatic access to world state, events, actors, entities,
and metrics for external integrations and the dashboard frontend.
"""

from __future__ import annotations


async def get_world_state() -> dict:
    """Return the current world state as JSON.

    Returns:
        A dict with services, actors, entities, and metadata.
    """
    ...


async def get_events(limit: int = 100, offset: int = 0) -> dict:
    """Return paginated events from the ledger.

    Args:
        limit: Maximum number of events to return.
        offset: Number of events to skip.

    Returns:
        A dict with ``events`` list and ``total`` count.
    """
    ...


async def get_actors() -> dict:
    """Return all actors in the current world.

    Returns:
        A dict with an ``actors`` list.
    """
    ...


async def get_entities(entity_type: str | None = None) -> dict:
    """Return entities, optionally filtered by type.

    Args:
        entity_type: Optional entity type filter.

    Returns:
        A dict with an ``entities`` list.
    """
    ...


async def get_metrics() -> dict:
    """Return current simulation metrics.

    Returns:
        A dict with tick count, event counts, budget usage, etc.
    """
    ...
