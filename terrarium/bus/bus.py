"""Core EventBus implementation.

The EventBus is the central nervous system of Terrarium.  It accepts
published events, fans them out to topic subscribers, persists them to
an append-only SQLite log (when enabled), and supports replay of
historical events.
"""

from __future__ import annotations

from terrarium.core.events import Event

from terrarium.bus.config import BusConfig
from terrarium.bus.types import BusMetrics, Subscriber


class EventBus:
    """Asynchronous publish/subscribe event bus with persistence and replay.

    Parameters:
        config: Bus configuration controlling persistence, queue sizes,
                and middleware selection.
    """

    def __init__(self, config: BusConfig) -> None:
        ...

    async def initialize(self) -> None:
        """Set up persistence, middleware chain, and internal state."""
        ...

    async def shutdown(self) -> None:
        """Drain queues, cancel background tasks, and close persistence."""
        ...

    async def subscribe(
        self,
        event_type: str,
        callback: Subscriber,
        queue_size: int = 1000,
    ) -> None:
        """Register a subscriber for a given event type.

        Args:
            event_type: The event type string to subscribe to.
            callback: Async callable invoked for each matching event.
            queue_size: Maximum number of events buffered before back-pressure.
        """
        ...

    async def unsubscribe(self, event_type: str, callback: Subscriber) -> None:
        """Remove a previously registered subscriber.

        Args:
            event_type: The event type the subscriber was registered for.
            callback: The exact callback reference to remove.
        """
        ...

    async def publish(self, event: Event) -> None:
        """Publish an event to all matching subscribers.

        The event is optionally persisted and then fanned out to all
        subscribers registered for the event's ``event_type``.

        Args:
            event: The event to publish.
        """
        ...

    async def replay(
        self,
        from_sequence: int = 0,
        event_types: list[str] | None = None,
        callback: Subscriber | None = None,
    ) -> list[Event]:
        """Replay persisted events, optionally filtering by type.

        Args:
            from_sequence: Start replaying from this sequence number.
            event_types: Optional list of event types to include.
            callback: If provided, events are delivered to this callback
                      instead of being returned.

        Returns:
            List of replayed events (empty when a callback is used).
        """
        ...

    async def get_event_count(self) -> int:
        """Return the total number of persisted events."""
        ...

    async def get_metrics(self) -> BusMetrics:
        """Return a snapshot of current bus metrics."""
        ...
