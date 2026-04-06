"""Bus-specific type aliases, data containers, and metric models.

Defines the callable signature for event subscribers, the internal
subscription bookkeeping dataclass, and the frozen metrics snapshot
exposed by the bus for observability.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pydantic import BaseModel

from volnix.core.events import Event

# ---------------------------------------------------------------------------
# Callable alias
# ---------------------------------------------------------------------------

Subscriber = Callable[[Event], Awaitable[None]]
"""Async callback signature for event subscribers."""

# ---------------------------------------------------------------------------
# Internal bookkeeping
# ---------------------------------------------------------------------------


@dataclass
class Subscription:
    """Tracks a single subscriber registration within the bus.

    Attributes:
        event_type: The event type string this subscription listens for.
        callback: The async callable to invoke for matching events.
        queue: Bounded asyncio queue used for back-pressure.
        task: The background asyncio task draining the queue.
    """

    event_type: str
    callback: Subscriber
    queue: asyncio.Queue[Event] = field(default_factory=lambda: asyncio.Queue(maxsize=1000))
    task: asyncio.Task[None] | None = None


# ---------------------------------------------------------------------------
# Metrics snapshot
# ---------------------------------------------------------------------------


class BusMetrics(BaseModel, frozen=True):
    """Immutable snapshot of event bus operational metrics.

    Attributes:
        events_published: Total events accepted by the bus.
        events_delivered: Total events successfully delivered to subscribers.
        events_dropped: Events dropped due to full queues or errors.
        persistence_errors: Errors encountered while persisting events.
    """

    events_published: int = 0
    events_delivered: int = 0
    events_dropped: int = 0
    persistence_errors: int = 0
