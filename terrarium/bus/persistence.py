"""SQLite append-only event log for the event bus.

BusPersistence writes every published event to a local SQLite database
in an append-only fashion, enabling replay, auditing, and crash recovery.
"""

from __future__ import annotations

from terrarium.core.events import Event


class BusPersistence:
    """Append-only SQLite persistence layer for bus events.

    Parameters:
        db_path: Filesystem path to the SQLite database file.
    """

    def __init__(self, db_path: str) -> None:
        ...

    async def initialize(self) -> None:
        """Open the database connection and ensure the schema exists."""
        ...

    async def shutdown(self) -> None:
        """Flush pending writes and close the database connection."""
        ...

    async def persist(self, event: Event) -> int:
        """Persist an event and return its sequence identifier.

        Args:
            event: The event to persist.

        Returns:
            The monotonically increasing sequence ID assigned to the event.
        """
        ...

    async def query(
        self,
        from_sequence: int = 0,
        event_types: list[str] | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        """Query persisted events with optional filters.

        Args:
            from_sequence: Return events with sequence ID >= this value.
            event_types: If provided, only return events matching these types.
            limit: Maximum number of events to return.

        Returns:
            Ordered list of matching events.
        """
        ...

    async def get_count(self) -> int:
        """Return the total number of persisted events."""
        ...

    async def get_latest_sequence(self) -> int:
        """Return the highest sequence ID in the log."""
        ...
