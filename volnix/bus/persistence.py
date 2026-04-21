"""SQLite append-only event log for the event bus.

BusPersistence writes every published event to a local SQLite database
in an append-only fashion, enabling replay, auditing, and crash recovery.

Receives a :class:`Database` via dependency injection -- does NOT create
its own ``SQLiteDatabase``.  The database lifecycle is managed externally
by :class:`ConnectionManager`.
"""

from __future__ import annotations

import json
from typing import Any

from volnix.core.events import Event
from volnix.core.types import SessionId
from volnix.persistence.append_log import AppendOnlyLog
from volnix.persistence.database import Database


class BusPersistence:
    """Append-only SQLite persistence layer for bus events.

    Parameters:
        db: A :class:`Database` instance (provided via DI, not created here).
    """

    def __init__(self, db: Database) -> None:
        self._db = db
        self._log = AppendOnlyLog(
            db=db,
            table_name="event_log",
            columns=[
                ("event_id", "TEXT NOT NULL"),
                ("event_type", "TEXT NOT NULL"),
                ("run_id", "TEXT"),
                # PMF Plan Phase 4C Step 6 — platform Session
                # correlation. Nullable: events outside a session
                # (animator events during unsessioned runs, etc.)
                # persist NULL.
                ("session_id", "TEXT"),
                ("timestamp_json", "TEXT NOT NULL"),
                ("payload", "TEXT NOT NULL"),
            ],
        )

    async def initialize(self) -> None:
        """Create the event_log table if it does not exist."""
        await self._log.initialize()
        await self._log.create_index("event_type")
        await self._log.create_index("run_id")
        # PMF Plan Phase 4C Step 6 — session_id filter index.
        await self._log.create_index("session_id")
        await self._log.create_index("created_at")

    async def shutdown(self) -> None:
        """No-op -- Database lifecycle is managed by ConnectionManager."""
        pass

    async def persist(self, event: Event) -> int:
        """Persist an event and return its sequence identifier.

        Args:
            event: The event to persist.

        Returns:
            The monotonically increasing sequence ID assigned to the event.
        """
        payload = event.model_dump_json()
        # PMF Plan Phase 4C Step 6 — ``session_id`` is on the
        # ``Event`` base class. Direct attribute access (no
        # ``getattr`` fallback) now that every event carries the
        # field; ``None`` outside a session.
        session_raw = event.session_id
        return await self._log.append(
            {
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "run_id": getattr(event, "run_id", None),
                "session_id": str(session_raw) if session_raw else None,
                "timestamp_json": event.timestamp.model_dump_json(),
                "payload": payload,
            }
        )

    async def query(
        self,
        from_sequence: int = 0,
        to_sequence: int | None = None,
        event_types: list[str] | None = None,
        session_id: SessionId | str | None = None,
        limit: int | None = None,
        order: str = "asc",
    ) -> list[Event]:
        """Query persisted events with optional filters.

        Args:
            from_sequence: Return events with sequence ID >= this value.
            to_sequence: If provided, only return events with sequence ID <= this value.
            event_types: If provided, only return events matching these types.
            session_id: PMF Plan Phase 4C Step 6 — if provided,
                only return events belonging to this platform session.
            limit: Maximum number of events to return.
            order: Sort direction — ``"asc"`` or ``"desc"``.

        Returns:
            Ordered list of matching events.
        """
        filters: dict[str, Any] | None = None
        if event_types:
            filters = {"event_type": event_types}
        if session_id is not None:
            # Equality filter on the indexed session_id column.
            if filters is None:
                filters = {}
            filters["session_id"] = str(session_id)

        range_filters: list[tuple[str, str, Any]] | None = None
        if to_sequence is not None:
            range_filters = [("sequence_id", "<=", to_sequence)]

        rows = await self._log.query(
            from_sequence=from_sequence,
            filters=filters,
            range_filters=range_filters,
            limit=limit,
            order=order,
        )
        events: list[Event] = []
        for row in rows:
            event = Event.model_validate_json(row["payload"])
            events.append(event)
        return events

    async def query_raw(
        self,
        from_sequence: int = 0,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
        order: str = "asc",
    ) -> list[dict[str, Any]]:
        """Query events as raw JSON dicts, preserving all subclass fields.

        Unlike :meth:`query` which deserializes to base ``Event`` (losing
        subclass fields like ``actor_id``), this returns the original JSON
        payloads as dicts.
        """
        rows = await self._log.query(
            from_sequence=from_sequence,
            filters=filters,
            limit=limit,
            order=order,
        )
        results: list[dict[str, Any]] = []
        for row in rows:
            try:
                results.append(json.loads(row["payload"]))
            except (json.JSONDecodeError, KeyError):
                pass
        return results

    async def get_count(self) -> int:
        """Return the total number of persisted events."""
        return await self._log.count()

    async def get_latest_sequence(self) -> int:
        """Return the highest sequence ID in the log."""
        return await self._log.latest_sequence()

    async def query_by_session(
        self,
        session_id: SessionId | str,
        *,
        limit: int | None = None,
        order: str = "asc",
    ) -> list[Event]:
        """Query events for a specific platform Session.

        Convenience wrapper around ``query(session_id=...)``.
        PMF Plan Phase 4C Step 6.

        Args:
            session_id: The platform session identifier.
            limit: Maximum number of events to return.
            order: Sort direction — ``"asc"`` or ``"desc"``.

        Returns:
            Ordered list of events belonging to the session.
        """
        return await self.query(session_id=session_id, limit=limit, order=order)

    async def query_by_time(
        self,
        start_iso: str,
        end_iso: str,
    ) -> list[Event]:
        """Query events within a time range using the created_at column.

        Args:
            start_iso: ISO-format start timestamp (inclusive).
            end_iso: ISO-format end timestamp (inclusive).

        Returns:
            Ordered list of matching events.
        """
        rows = await self._db.fetchall(
            "SELECT * FROM event_log WHERE created_at >= ? AND created_at <= ? "
            "ORDER BY sequence_id ASC",
            (start_iso, end_iso),
        )
        events: list[Event] = []
        for row in rows:
            event = Event.model_validate_json(row["payload"])
            events.append(event)
        return events
