"""Visibility scope computation for actors."""

from __future__ import annotations

from typing import Any

from terrarium.core import ActorId, EntityId, StateEngineProtocol


class VisibilityScope:
    """Computes and filters entities based on actor visibility rules."""

    def __init__(self, state: StateEngineProtocol) -> None:
        self._state = state

    async def compute_scope(
        self, actor_id: ActorId, entity_type: str
    ) -> list[EntityId]:
        """Compute the set of entity IDs visible to an actor."""
        ...

    async def filter_entities(
        self, actor_id: ActorId, entities: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter a list of entities to only those visible to the actor."""
        ...

    async def is_visible(
        self, actor_id: ActorId, entity_type: str, entity_id: EntityId
    ) -> bool:
        """Check whether a specific entity is visible to the actor."""
        ...
