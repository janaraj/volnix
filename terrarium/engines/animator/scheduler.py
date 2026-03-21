"""Event scheduler -- manages time-based event triggers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from terrarium.engines.animator.config import AnimatorConfig


class EventScheduler:
    """Manages scheduled events and advances them based on world time."""

    def __init__(self, config: AnimatorConfig) -> None:
        self._config = config

    async def initialize(self, scheduled_events: list[dict[str, Any]]) -> None:
        """Load initial set of scheduled events."""
        ...

    async def get_due_events(self, world_time: datetime) -> list[dict[str, Any]]:
        """Return events that are due at or before *world_time*."""
        ...

    async def advance_time(self, world_time: datetime) -> None:
        """Advance the scheduler's internal clock to *world_time*."""
        ...
