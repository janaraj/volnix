"""Observation delivery -- pushes events to connected agents."""

from __future__ import annotations

from typing import Any

from terrarium.core import ActorId, PermissionEngineProtocol, WorldEvent
from terrarium.engines.adapter.protocols.base import ProtocolAdapter


class ObservationDelivery:
    """Delivers world events to agents as observations, respecting visibility."""

    def __init__(
        self,
        adapters: dict[str, ProtocolAdapter],
        permissions: PermissionEngineProtocol,
    ) -> None:
        self._adapters = adapters
        self._permissions = permissions

    async def deliver(
        self, event: WorldEvent, actor_ids: list[ActorId]
    ) -> None:
        """Deliver an event as an observation to the specified actors."""
        ...

    async def filter_for_actor(
        self, event: WorldEvent, actor_id: ActorId
    ) -> dict[str, Any] | None:
        """Filter event data for a specific actor's visibility scope.

        Returns:
            The filtered event dict, or ``None`` if the actor cannot see it.
        """
        ...
