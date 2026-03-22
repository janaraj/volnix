"""Entity store -- CRUD operations for world entities."""

from __future__ import annotations

import json
import logging
from typing import Any

from terrarium.core.types import EntityId
from terrarium.core.errors import EntityNotFoundError, StateError
from terrarium.persistence.database import Database

logger = logging.getLogger(__name__)


class EntityStore:
    """Low-level CRUD store for entities backed by a :class:`Database`.

    Tables are created by :mod:`terrarium.engines.state.migrations` via
    ``MigrationRunner`` -- this class contains business logic only.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self, entity_type: str, entity_id: EntityId, fields: dict[str, Any]
    ) -> None:
        """Insert a new entity."""
        try:
            await self._db.execute(
                "INSERT INTO entities (entity_type, entity_id, data) VALUES (?, ?, ?)",
                (entity_type, str(entity_id), json.dumps(fields)),
            )
        except Exception as exc:
            if "UNIQUE constraint" in str(exc):
                raise StateError(f"Entity already exists: {entity_type}/{entity_id}") from exc
            raise

    async def read(
        self, entity_type: str, entity_id: EntityId
    ) -> dict[str, Any] | None:
        """Read an entity by type and id, returning ``None`` if missing."""
        row = await self._db.fetchone(
            "SELECT data FROM entities WHERE entity_type = ? AND entity_id = ?",
            (entity_type, str(entity_id)),
        )
        if row is None:
            return None
        result = json.loads(row["data"])
        result["_entity_type"] = entity_type
        result["_entity_id"] = str(entity_id)
        return result

    async def update(
        self, entity_type: str, entity_id: EntityId, fields: dict[str, Any]
    ) -> dict[str, Any]:
        """Update fields on an existing entity (merge semantics).

        Note: This is a read-modify-write. Callers should wrap in
        ``db.transaction()`` to prevent lost updates under concurrency.
        SQLite's single-writer with WAL provides baseline protection.

        Returns the pre-update state for retractability.
        """
        existing = await self.read(entity_type, entity_id)
        if existing is None:
            raise EntityNotFoundError(f"Entity not found: {entity_type}/{entity_id}")
        # Capture pre-update state (for StateDelta.previous_fields / retract)
        previous = {k: v for k, v in existing.items() if not k.startswith("_")}
        existing.update(fields)
        # Remove metadata keys before persisting
        data = {k: v for k, v in existing.items() if not k.startswith("_")}
        await self._db.execute(
            "UPDATE entities SET data = ?, updated_at = datetime('now') WHERE entity_type = ? AND entity_id = ?",
            (json.dumps(data), entity_type, str(entity_id)),
        )
        return previous

    async def delete(self, entity_type: str, entity_id: EntityId) -> dict[str, Any] | None:
        """Delete an entity.

        Returns the pre-delete state for retractability, or ``None`` if
        the entity did not exist.
        """
        existing = await self.read(entity_type, entity_id)
        if existing is None:
            return None
        await self._db.execute(
            "DELETE FROM entities WHERE entity_type = ? AND entity_id = ?",
            (entity_type, str(entity_id)),
        )
        return {k: v for k, v in existing.items() if not k.startswith("_")}

    async def query(
        self, entity_type: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Query entities of a given type with optional filters."""
        rows = await self._db.fetchall(
            "SELECT entity_id, data FROM entities WHERE entity_type = ?",
            (entity_type,),
        )
        results = []
        for row in rows:
            entity = json.loads(row["data"])
            entity["_entity_type"] = entity_type
            entity["_entity_id"] = row["entity_id"]
            # Python-side filtering (SQLite json_extract optimization in future)
            if filters:
                if all(entity.get(k) == v for k, v in filters.items()):
                    results.append(entity)
            else:
                results.append(entity)
        return results

    async def count(self, entity_type: str) -> int:
        """Return the count of entities of the given type."""
        row = await self._db.fetchone(
            "SELECT COUNT(*) as cnt FROM entities WHERE entity_type = ?",
            (entity_type,),
        )
        return row["cnt"] if row else 0
