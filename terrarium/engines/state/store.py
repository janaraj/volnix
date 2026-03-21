"""Entity store -- CRUD operations for world entities."""

from __future__ import annotations

from typing import Any

from terrarium.core import EntityId
from terrarium.persistence.database import Database


class EntityStore:
    """Low-level CRUD store for entities backed by a :class:`Database`."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def initialize(self) -> None:
        """Create tables / indexes if they do not exist."""
        ...

    async def create(
        self, entity_type: str, entity_id: EntityId, fields: dict[str, Any]
    ) -> None:
        """Insert a new entity."""
        ...

    async def read(
        self, entity_type: str, entity_id: EntityId
    ) -> dict[str, Any] | None:
        """Read an entity by type and id, returning ``None`` if missing."""
        ...

    async def update(
        self, entity_type: str, entity_id: EntityId, fields: dict[str, Any]
    ) -> None:
        """Update fields on an existing entity."""
        ...

    async def delete(self, entity_type: str, entity_id: EntityId) -> None:
        """Delete an entity."""
        ...

    async def query(
        self, entity_type: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Query entities of a given type with optional filters."""
        ...

    async def count(self, entity_type: str) -> int:
        """Return the count of entities of the given type."""
        ...
