"""Core EventBus implementation.

The EventBus is the central nervous system of Volnix.  It accepts
published events, fans them out to topic subscribers, persists them to
an append-only SQLite log (when enabled), and supports replay of
historical events.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

from volnix.bus.config import BusConfig
from volnix.bus.fanout import TopicFanout
from volnix.bus.middleware import MiddlewareChain
from volnix.bus.persistence import BusPersistence
from volnix.bus.types import BusMetrics, Subscriber, Subscription
from volnix.core.events import Event
from volnix.persistence.database import Database


class EventBus:
    """Asynchronous publish/subscribe event bus with persistence and replay.

    Parameters:
        config: Bus configuration controlling persistence, queue sizes,
                and middleware selection.
        db: Optional :class:`Database` instance for persistence.
              Required when ``config.persistence_enabled`` is ``True``.
    """

    def __init__(self, config: BusConfig, db: Database | None = None) -> None:
        self._config = config
        self._db = db
        self._fanout = TopicFanout()
        self._middleware = MiddlewareChain()
        self._persistence: BusPersistence | None = None
        self._events_published: int = 0
        self._events_delivered: int = 0
        self._events_dropped: int = 0
        self._persistence_errors: int = 0
        self._initialized: bool = False

    async def initialize(self) -> None:
        """Set up persistence, middleware chain, and internal state."""
        if self._config.persistence_enabled:
            if self._db is None:
                raise ValueError("persistence_enabled is True but no Database was provided")
            self._persistence = BusPersistence(self._db)
            await self._persistence.initialize()
        self._initialized = True

    async def shutdown(self) -> None:
        """Cancel all consumer tasks. Does NOT close the database."""
        for sub in self._fanout.all_subscriptions():
            if sub.task is not None and not sub.task.done():
                sub.task.cancel()
                try:
                    await sub.task
                except asyncio.CancelledError:
                    pass
        if self._persistence is not None:
            await self._persistence.shutdown()
        self._initialized = False

    async def subscribe(
        self,
        event_type: str,
        callback: Subscriber,
        queue_size: int | None = None,
    ) -> None:
        """Register a subscriber for a given event type.

        Creates a :class:`Subscription` with a bounded queue and starts
        a background consumer task that drains the queue and calls the
        callback for each event.

        Args:
            event_type: The event type string to subscribe to, or ``"*"``
                        for wildcard (receives ALL events).
            callback: Async callable invoked for each matching event.
            queue_size: Maximum number of events buffered before back-pressure.
        """
        effective_queue_size = queue_size if queue_size is not None else self._config.queue_size
        sub = Subscription(
            event_type=event_type,
            callback=callback,
            queue=asyncio.Queue(maxsize=effective_queue_size),
        )
        task = asyncio.create_task(self._consumer(sub))
        sub.task = task
        self._fanout.add_subscriber(event_type, sub)

    async def unsubscribe(self, event_type: str, callback: Subscriber) -> None:
        """Remove a previously registered subscriber.

        Args:
            event_type: The event type the subscriber was registered for.
            callback: The exact callback reference to remove.
        """
        self._fanout.remove_subscriber(event_type, callback)

    async def publish(self, event: Event) -> None:
        """Publish an event to all matching subscribers.

        Pipeline: middleware_before -> persist -> fanout -> middleware_after.
        Persist BEFORE fanout so the log is never behind.

        Args:
            event: The event to publish.

        Raises:
            RuntimeError: If the bus has not been initialized or has been shut down.
        """
        if not self._initialized:
            raise RuntimeError("EventBus is not initialized or has been shut down")

        # Middleware before
        processed = await self._middleware.process_before(event)
        if processed is None:
            return  # Event dropped by middleware

        # Persist before fanout
        if self._persistence is not None:
            try:
                await self._persistence.persist(processed)
            except Exception:
                logger.error(
                    "Event persistence failed for event %s",
                    event.event_type if hasattr(event, "event_type") else type(event).__name__,
                    exc_info=True,
                )
                self._persistence_errors += 1

        # Fanout
        drops = await self._fanout.fanout(processed)
        self._events_dropped += drops
        self._events_published += 1

        # Middleware after (fire-and-forget)
        await self._middleware.process_after(processed)

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
        if self._persistence is None:
            return []

        events = await self._persistence.query(
            from_sequence=from_sequence,
            event_types=event_types,
        )

        if callback is not None:
            for evt in events:
                await callback(evt)
            return []

        return events

    async def get_event_count(self) -> int:
        """Return the total number of persisted events."""
        if self._persistence is None:
            return 0
        return await self._persistence.get_count()

    async def get_metrics(self) -> BusMetrics:
        """Return a snapshot of current bus metrics."""
        return BusMetrics(
            events_published=self._events_published,
            events_delivered=self._events_delivered,
            events_dropped=self._events_dropped,
            persistence_errors=self._persistence_errors,
        )

    def add_middleware(self, middleware: object) -> None:
        """Add a middleware to the bus middleware chain.

        Args:
            middleware: A middleware instance conforming to
                       :class:`BusMiddleware` protocol.
        """
        self._middleware.add(middleware)  # type: ignore[arg-type]

    async def _consumer(self, sub: Subscription) -> None:
        """Background consumer task that drains a subscriber's queue.

        Runs indefinitely, calling the subscriber's callback for each
        event.  Exceptions in the callback are silently swallowed so
        that one failure does not crash the bus or other subscribers.
        """
        while True:
            try:
                event = await sub.queue.get()
                try:
                    await sub.callback(event)
                    self._events_delivered += 1
                except Exception:
                    logger.exception(
                        "Subscriber callback failed for event %s",
                        event.event_type if hasattr(event, "event_type") else type(event).__name__,
                    )
            except asyncio.CancelledError:
                break
