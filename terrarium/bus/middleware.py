"""Bus middleware for cross-cutting concerns.

Provides a protocol for event bus middleware, a chain that applies
middleware in order, and two built-in implementations: logging and
metrics collection.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from terrarium.core.events import Event


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
        ...

    def add(self, middleware: BusMiddleware) -> None:
        """Append a middleware to the end of the chain.

        Args:
            middleware: The middleware instance to add.
        """
        ...

    async def process_before(self, event: Event) -> Event | None:
        """Run all ``before_publish`` hooks in order.

        If any middleware returns ``None``, the event is dropped and
        subsequent middleware is not called.

        Args:
            event: The event to process.

        Returns:
            The (possibly transformed) event, or ``None`` if dropped.
        """
        ...

    async def process_after(self, event: Event) -> None:
        """Run all ``after_publish`` hooks in order.

        Args:
            event: The event that was published.
        """
        ...


# ---------------------------------------------------------------------------
# Built-in middleware
# ---------------------------------------------------------------------------


class LoggingMiddleware:
    """Middleware that logs event publication for observability."""

    async def before_publish(self, event: Event) -> Event | None:
        """Log the event before publication.

        Args:
            event: The event about to be published.

        Returns:
            The unmodified event.
        """
        ...

    async def after_publish(self, event: Event) -> None:
        """Log successful publication.

        Args:
            event: The event that was published.
        """
        ...


class MetricsMiddleware:
    """Middleware that collects event throughput and latency metrics."""

    async def before_publish(self, event: Event) -> Event | None:
        """Record pre-publish timing.

        Args:
            event: The event about to be published.

        Returns:
            The unmodified event.
        """
        ...

    async def after_publish(self, event: Event) -> None:
        """Record post-publish metrics.

        Args:
            event: The event that was published.
        """
        ...
