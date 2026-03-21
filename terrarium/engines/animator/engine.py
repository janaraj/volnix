"""World animator engine implementation.

Generates autonomous world events (NPC behaviour, scheduled triggers,
organic activity) on each simulation tick.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from terrarium.core import ActionContext, BaseEngine, Event


class WorldAnimatorEngine(BaseEngine):
    """Autonomous world event generation engine.

    Uses WorldConditions to apply runtime probabilities (service failures,
    injection content in organic events).
    """

    engine_name: ClassVar[str] = "animator"
    subscriptions: ClassVar[list[str]] = ["simulation", "world"]
    dependencies: ClassVar[list[str]] = ["state"]

    # WorldConditions reference, set during initialization.
    _conditions: Any = None

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """Handle an inbound event from the bus."""
        ...

    # -- Animator operations ---------------------------------------------------

    async def tick(self, world_time: datetime) -> list[ActionContext]:
        """Advance the animator by one logical tick and return generated actions."""
        ...

    async def generate_events(self, world_time: datetime) -> list[ActionContext]:
        """Generate autonomous events for the current world time."""
        ...

    async def get_pending_scheduled(self, until: datetime) -> list[dict[str, Any]]:
        """Return scheduled events that are due before *until*."""
        ...
