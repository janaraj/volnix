"""Append-only event log for the state engine."""

from __future__ import annotations

from datetime import datetime

from terrarium.core import ActorId, EntityId, EventId, WorldEvent
from terrarium.persistence.database import Database


class EventLog:
    """Append-only, queryable event log backed by a :class:`Database`."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def initialize(self) -> None:
        """Create tables / indexes if they do not exist."""
        ...

    async def append(self, event: WorldEvent) -> EventId:
        """Append an event and return its id."""
        ...

    async def get(self, event_id: EventId) -> WorldEvent | None:
        """Retrieve a single event by id."""
        ...

    async def query(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        actor_id: ActorId | None = None,
        limit: int | None = None,
    ) -> list[WorldEvent]:
        """Query events with optional time-range, actor, and limit filters."""
        ...

    async def get_by_entity(
        self, entity_type: str, entity_id: EntityId
    ) -> list[WorldEvent]:
        """Return all events that affected a specific entity."""
        ...
