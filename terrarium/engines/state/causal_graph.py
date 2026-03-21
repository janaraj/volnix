"""Causal graph -- tracks cause-effect relationships between events."""

from __future__ import annotations

from terrarium.core import EventId
from terrarium.persistence.database import Database


class CausalGraph:
    """Directed acyclic graph of causal relationships between events."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def initialize(self) -> None:
        """Create tables / indexes if they do not exist."""
        ...

    async def add_edge(self, cause_id: EventId, effect_id: EventId) -> None:
        """Record that *cause_id* causally led to *effect_id*."""
        ...

    async def get_causes(self, event_id: EventId) -> list[EventId]:
        """Return the direct causes of an event."""
        ...

    async def get_effects(self, event_id: EventId) -> list[EventId]:
        """Return the direct effects of an event."""
        ...

    async def get_chain(
        self, event_id: EventId, direction: str, max_depth: int = 50
    ) -> list[EventId]:
        """Walk the causal chain in the given direction up to *max_depth*."""
        ...

    async def get_roots(self, event_id: EventId) -> list[EventId]:
        """Return the root causes (events with no ancestors) of an event."""
        ...
