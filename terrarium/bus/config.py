"""Configuration model for the event bus.

Provides a Pydantic model that centralises all tuneable parameters for
the bus subsystem, including persistence, queue sizing, and middleware
selection.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BusConfig(BaseModel):
    """Configuration for the Terrarium event bus.

    Attributes:
        db_path: Filesystem path for the SQLite event log.
        queue_size: Default maximum queue depth per subscriber.
        persistence_enabled: Whether to persist events to SQLite.
        middleware: Ordered list of middleware names to activate.
    """

    db_path: str = "terrarium_events.db"
    queue_size: int = 1000
    persistence_enabled: bool = True
    middleware: list[str] = Field(default_factory=lambda: ["logging", "metrics"])
