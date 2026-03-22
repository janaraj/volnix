"""Append-only event log for the state engine."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from terrarium.core.types import ActorId, EntityId, EventId
from terrarium.core.events import Event, WorldEvent
from terrarium.persistence.database import Database

logger = logging.getLogger(__name__)


class EventLog:
    """Append-only, queryable event log backed by a :class:`Database`.

    Tables are created by :mod:`terrarium.engines.state.migrations` via
    ``MigrationRunner`` -- this class contains business logic only.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def append(self, event: Event) -> EventId:
        """Append an event and return its id.

        Extracts indexed fields for fast SQL queries and stores the full
        serialised payload for lossless reconstruction.
        """
        # Extract fields for indexed columns (WorldEvent-specific fields may
        # not exist on the base Event).
        actor_id = getattr(event, "actor_id", None)
        service_id = getattr(event, "service_id", None)
        action = getattr(event, "action", None)
        target = getattr(event, "target_entity", None)

        await self._db.execute(
            """INSERT INTO events
               (event_id, event_type, timestamp_world, timestamp_wall, tick,
                actor_id, service_id, action, target_entity, payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(event.event_id),
                event.event_type,
                event.timestamp.world_time.isoformat() if event.timestamp.world_time else None,
                event.timestamp.wall_time.isoformat() if event.timestamp.wall_time else None,
                event.timestamp.tick,
                str(actor_id) if actor_id else None,
                str(service_id) if service_id else None,
                action,
                str(target) if target else None,
                event.model_dump_json(),
            ),
        )
        return event.event_id

    async def get(self, event_id: EventId) -> Event | None:
        """Retrieve a single event by id."""
        row = await self._db.fetchone(
            "SELECT payload FROM events WHERE event_id = ?", (str(event_id),)
        )
        if row is None:
            return None
        return self._deserialize(row["payload"])

    async def query(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        actor_id: ActorId | None = None,
        entity_id: EntityId | None = None,
        event_type: str | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        """Query events with optional filters. All filters are AND'd."""
        sql = "SELECT payload FROM events WHERE 1=1"
        params: list[Any] = []
        if start is not None:
            sql += " AND timestamp_world >= ?"
            params.append(start.isoformat())
        if end is not None:
            sql += " AND timestamp_world <= ?"
            params.append(end.isoformat())
        if actor_id is not None:
            sql += " AND actor_id = ?"
            params.append(str(actor_id))
        if entity_id is not None:
            sql += " AND target_entity = ?"
            params.append(str(entity_id))
        if event_type is not None:
            sql += " AND event_type = ?"
            params.append(event_type)
        sql += " ORDER BY timestamp_world IS NULL, timestamp_world ASC, tick ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = await self._db.fetchall(sql, tuple(params))
        return [self._deserialize(row["payload"]) for row in rows]

    async def get_by_entity(
        self, entity_type: str, entity_id: EntityId
    ) -> list[Event]:
        """Return all events that affected a specific entity.

        Note: entity_type is accepted for API consistency but filtering
        is by entity_id only (entity IDs are globally unique by design).
        """
        return await self.query(entity_id=entity_id)

    def _deserialize(self, payload: str) -> Event:
        """Deserialize event payload. Try WorldEvent first, fall back to Event."""
        try:
            return WorldEvent.model_validate_json(payload)
        except Exception as exc:
            logger.warning("Failed to deserialize as WorldEvent, falling back to Event: %s", exc)
            return Event.model_validate_json(payload)
