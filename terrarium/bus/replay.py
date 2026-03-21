"""Replay engine for re-processing historical events.

ReplayEngine coordinates with the persistence layer and the topic fanout
dispatcher to replay events by sequence range, time range, or to a
specific callback.
"""

from __future__ import annotations

from datetime import datetime

from terrarium.bus.fanout import TopicFanout
from terrarium.bus.persistence import BusPersistence
from terrarium.bus.types import Subscriber


class ReplayEngine:
    """Replays persisted events through the fanout or a custom callback.

    Parameters:
        persistence: The bus persistence backend to read events from.
        fanout: The topic fanout dispatcher for subscriber delivery.
    """

    def __init__(self, persistence: BusPersistence, fanout: TopicFanout) -> None:
        ...

    async def replay_range(
        self,
        from_sequence: int,
        to_sequence: int | None = None,
        event_types: list[str] | None = None,
    ) -> int:
        """Replay events within a sequence ID range.

        Args:
            from_sequence: Start of the sequence range (inclusive).
            to_sequence: End of the sequence range (inclusive). If ``None``,
                         replay to the latest event.
            event_types: Optional filter for specific event types.

        Returns:
            Number of events replayed.
        """
        ...

    async def replay_timerange(self, start: datetime, end: datetime) -> int:
        """Replay events that occurred within a wall-clock time range.

        Args:
            start: Start of the time range (inclusive).
            end: End of the time range (inclusive).

        Returns:
            Number of events replayed.
        """
        ...

    async def replay_to_callback(
        self,
        callback: Subscriber,
        from_sequence: int = 0,
        event_types: list[str] | None = None,
    ) -> int:
        """Replay events and deliver each one to a custom callback.

        Args:
            callback: Async callable to receive each replayed event.
            from_sequence: Start replaying from this sequence number.
            event_types: Optional filter for specific event types.

        Returns:
            Number of events replayed.
        """
        ...
