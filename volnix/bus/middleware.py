"""Bus middleware for cross-cutting concerns.

Provides a protocol for event bus middleware, a chain that applies
middleware in order, and two built-in implementations: logging and
metrics collection.
"""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

from volnix.core.events import Event


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class BusMiddleware(Protocol):
    """Protocol for event bus middleware.

    Middleware can inspect or transform events before publication and
    perform side effects after publication.
    """

    async def before_publish(self, event: Event) -> Event | None:
        """Called before an event is published.

        May return a (possibly modified) event to continue processing,
        or ``None`` to drop the event.

        Args:
            event: The event about to be published.

        Returns:
            The event to publish, or ``None`` to suppress it.
        """
        ...

    async def after_publish(self, event: Event) -> None:
        """Called after an event has been published and fanned out.

        Args:
            event: The event that was just published.
        """
        ...


# ---------------------------------------------------------------------------
# Middleware chain
# ---------------------------------------------------------------------------


class MiddlewareChain:
    """Ordered chain of middleware applied to every published event."""

    def __init__(self) -> None:
        self._middleware: list[BusMiddleware] = []

    def add(self, middleware: BusMiddleware) -> None:
        """Append a middleware to the end of the chain.

        Args:
            middleware: The middleware instance to add.
        """
        self._middleware.append(middleware)

    async def process_before(self, event: Event) -> Event | None:
        """Run all ``before_publish`` hooks in order.

        If any middleware returns ``None``, the event is dropped and
        subsequent middleware is not called.

        Args:
            event: The event to process.

        Returns:
            The (possibly transformed) event, or ``None`` if dropped.
        """
        current: Event | None = event
        for mw in self._middleware:
            if current is None:
                return None
            current = await mw.before_publish(current)
        return current

    async def process_after(self, event: Event) -> None:
        """Run all ``after_publish`` hooks in order (fire-and-forget).

        Exceptions in individual middleware are silently swallowed so
        that one failing middleware does not block the rest.

        Args:
            event: The event that was published.
        """
        for mw in self._middleware:
            try:
                await mw.after_publish(event)
            except Exception:
                logger.warning("Middleware after_publish failed", exc_info=True)


# ---------------------------------------------------------------------------
# Built-in middleware
# ---------------------------------------------------------------------------


class LoggingMiddleware:
    """Middleware that logs event publication for observability.

    Maintains an in-memory ``log`` list for easy inspection in tests.
    """

    def __init__(self) -> None:
        self.log: list[str] = []

    async def before_publish(self, event: Event) -> Event | None:
        """Log the event before publication.

        Args:
            event: The event about to be published.

        Returns:
            The unmodified event.
        """
        self.log.append(f"before:{event.event_type}:{event.event_id}")
        return event

    async def after_publish(self, event: Event) -> None:
        """Log successful publication.

        Args:
            event: The event that was published.
        """
        self.log.append(f"after:{event.event_type}:{event.event_id}")


class MetricsMiddleware:
    """Middleware that collects event throughput metrics.

    Attributes:
        before_count: Number of events that passed through ``before_publish``.
        after_count: Number of events that passed through ``after_publish``.
    """

    def __init__(self) -> None:
        self.before_count: int = 0
        self.after_count: int = 0

    async def before_publish(self, event: Event) -> Event | None:
        """Record pre-publish count.

        Args:
            event: The event about to be published.

        Returns:
            The unmodified event.
        """
        self.before_count += 1
        return event

    async def after_publish(self, event: Event) -> None:
        """Record post-publish count.

        Args:
            event: The event that was published.
        """
        self.after_count += 1
