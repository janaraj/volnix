"""Causal graph -- tracks cause-effect relationships between events."""

from __future__ import annotations

import logging
from collections import deque

from terrarium.core.types import EventId
from terrarium.persistence.database import Database

logger = logging.getLogger(__name__)


class CausalGraph:
    """Directed acyclic graph of causal relationships between events.

    Tables are created by :mod:`terrarium.engines.state.migrations` via
    ``MigrationRunner`` -- this class contains business logic only.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def add_edge(self, cause_id: EventId, effect_id: EventId) -> None:
        """Record that *cause_id* causally led to *effect_id*.

        Uses ``INSERT OR IGNORE`` so duplicate edges are silently skipped.
        """
        await self._db.execute(
            "INSERT OR IGNORE INTO causal_edges (cause_id, effect_id) VALUES (?, ?)",
            (str(cause_id), str(effect_id)),
        )

    async def get_causes(self, event_id: EventId) -> list[EventId]:
        """Return the direct causes of an event."""
        rows = await self._db.fetchall(
            "SELECT cause_id FROM causal_edges WHERE effect_id = ?", (str(event_id),)
        )
        return [EventId(row["cause_id"]) for row in rows]

    async def get_effects(self, event_id: EventId) -> list[EventId]:
        """Return the direct effects of an event."""
        rows = await self._db.fetchall(
            "SELECT effect_id FROM causal_edges WHERE cause_id = ?", (str(event_id),)
        )
        return [EventId(row["effect_id"]) for row in rows]

    async def get_chain(
        self, event_id: EventId, direction: str = "backward", max_depth: int = 50
    ) -> list[EventId]:
        """Walk the causal chain in the given direction up to *max_depth*.

        ``direction="backward"`` walks causes; ``"forward"`` walks effects.
        Uses BFS traversal with deque.
        """
        visited: set[str] = set()
        result: list[EventId] = []
        queue: deque[tuple[EventId, int]] = deque([(event_id, 0)])
        while queue:
            current, depth = queue.popleft()
            key = str(current)
            if key in visited or depth > max_depth:
                continue
            visited.add(key)
            if current != event_id:
                result.append(current)
            neighbors = (
                await self.get_causes(current)
                if direction == "backward"
                else await self.get_effects(current)
            )
            for n in neighbors:
                if str(n) not in visited:
                    queue.append((n, depth + 1))
        return result

    async def get_roots(self, event_id: EventId) -> list[EventId]:
        """Return the root causes (events with no ancestors) of an event."""
        chain = await self.get_chain(event_id, "backward")
        if not chain:
            return [event_id]
        roots = []
        for eid in chain:
            causes = await self.get_causes(eid)
            if not causes:
                roots.append(eid)
        return roots if roots else [event_id]
