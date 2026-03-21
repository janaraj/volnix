"""Live view dashboard routes.

Provides endpoints for server-sent event (SSE) streaming of world
events and the current world state view.
"""

from __future__ import annotations


async def live_view() -> dict:
    """Render the live world state page.

    Returns:
        An HTML response with the live dashboard view.
    """
    ...


async def event_stream() -> None:
    """SSE endpoint streaming real-time world events.

    Yields server-sent events as they occur in the running world.
    """
    ...
