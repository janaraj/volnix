"""Topic-based fan-out dispatcher.

TopicFanout manages the mapping from event type strings to subscriber
entries and handles asynchronous delivery to all matching subscribers.
"""

from __future__ import annotations

from terrarium.core.events import Event

from terrarium.bus.types import Subscriber, Subscription


class TopicFanout:
    """Manages topic-to-subscriber mappings and event fan-out delivery.

    Each event type maps to zero or more :class:`Subscription` entries.
    When an event is fanned out, it is placed into every matching
    subscriber's queue for asynchronous processing.
    """

    def __init__(self) -> None:
        ...

    def add_subscriber(self, event_type: str, entry: Subscription) -> None:
        """Register a subscription entry for a given event type.

        Args:
            event_type: The event type string to subscribe to.
            entry: The subscription bookkeeping object.
        """
        ...

    def remove_subscriber(self, event_type: str, callback: Subscriber) -> None:
        """Remove a subscriber by callback reference.

        Args:
            event_type: The event type the subscriber was registered for.
            callback: The callback to remove.
        """
        ...

    async def fanout(self, event: Event) -> None:
        """Deliver an event to all subscribers registered for its type.

        Args:
            event: The event to fan out.
        """
        ...

    def get_subscriber_count(self, event_type: str | None = None) -> int:
        """Return the number of active subscribers.

        Args:
            event_type: If provided, count only subscribers for this type.
                        If ``None``, return the total across all types.

        Returns:
            Number of active subscribers.
        """
        ...
