"""Topic-based fan-out dispatcher.

TopicFanout manages the mapping from event type strings to subscriber
entries and handles asynchronous delivery to all matching subscribers.
Wildcard ``"*"`` subscriptions receive ALL events.
"""
from __future__ import annotations

import asyncio

from terrarium.core.events import Event
from terrarium.bus.types import Subscriber, Subscription


class TopicFanout:
    """Manages topic-to-subscriber mappings and event fan-out delivery.

    Each event type maps to zero or more :class:`Subscription` entries.
    When an event is fanned out, it is placed into every matching
    subscriber's queue for asynchronous processing.

    Wildcard subscribers (event_type ``"*"``) receive every event.
    """

    def __init__(self) -> None:
        self._subscriptions: dict[str, list[Subscription]] = {}
        self._wildcard: list[Subscription] = []

    def add_subscriber(self, event_type: str, entry: Subscription) -> None:
        """Register a subscription entry for a given event type.

        Args:
            event_type: The event type string to subscribe to, or ``"*"``
                        for wildcard.
            entry: The subscription bookkeeping object.
        """
        if event_type == "*":
            self._wildcard.append(entry)
        else:
            self._subscriptions.setdefault(event_type, []).append(entry)

    def remove_subscriber(self, event_type: str, callback: Subscriber) -> None:
        """Remove a subscriber by callback reference.

        Also cancels the subscriber's background consumer task if running.
        Events already queued may still be partially delivered before
        cancellation takes effect.

        Args:
            event_type: The event type the subscriber was registered for.
            callback: The callback to remove.
        """
        if event_type == "*":
            for sub in self._wildcard:
                if sub.callback is callback:
                    if sub.task is not None and not sub.task.done():
                        sub.task.cancel()
                    self._wildcard.remove(sub)
                    return
        else:
            subs = self._subscriptions.get(event_type, [])
            for sub in subs:
                if sub.callback is callback:
                    if sub.task is not None and not sub.task.done():
                        sub.task.cancel()
                    subs.remove(sub)
                    return

    async def fanout(self, event: Event) -> int:
        """Deliver an event to all subscribers registered for its type.

        Matching subscribers (by topic) plus all wildcard subscribers
        receive the event via their bounded queues.  When a queue is full,
        the oldest event is dropped (back-pressure) to make room.

        Args:
            event: The event to fan out.

        Returns:
            Number of events dropped due to back-pressure.
        """
        targets: list[Subscription] = []
        targets.extend(self._subscriptions.get(event.event_type, []))
        targets.extend(self._wildcard)

        drops = 0
        for sub in targets:
            if sub.queue.full():
                # Back-pressure: drop oldest when queue full
                try:
                    sub.queue.get_nowait()
                    drops += 1
                except asyncio.QueueEmpty:
                    pass
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                # Should not happen after dropping, but guard anyway
                drops += 1
        return drops

    def get_subscriber_count(self, event_type: str | None = None) -> int:
        """Return the number of active subscribers.

        Args:
            event_type: If provided, count only subscribers for this type.
                        If ``None``, return the total across all types
                        (including wildcards).

        Returns:
            Number of active subscribers.
        """
        if event_type is not None:
            if event_type == "*":
                return len(self._wildcard)
            return len(self._subscriptions.get(event_type, []))
        total = sum(len(subs) for subs in self._subscriptions.values())
        total += len(self._wildcard)
        return total

    def all_subscriptions(self) -> list[Subscription]:
        """Return a flat list of all subscriptions (topic + wildcard).

        Useful for shutdown to cancel all consumer tasks.

        Returns:
            List of all subscription entries.
        """
        result: list[Subscription] = []
        for subs in self._subscriptions.values():
            result.extend(subs)
        result.extend(self._wildcard)
        return result
