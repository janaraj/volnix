"""Tests for terrarium.bus.middleware — before/after hooks, logging, metrics."""
import pytest
from datetime import datetime, timezone

from terrarium.bus.middleware import (
    BusMiddleware,
    LoggingMiddleware,
    MetricsMiddleware,
    MiddlewareChain,
)
from terrarium.core.events import Event
from terrarium.core.types import Timestamp


def _make_event(event_type: str = "test.event") -> Event:
    """Helper to create a test Event."""
    return Event(
        event_type=event_type,
        timestamp=Timestamp(
            world_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            wall_time=datetime.now(timezone.utc),
            tick=1,
        ),
    )


class _PassthroughMiddleware:
    """Middleware that passes events through unchanged."""

    async def before_publish(self, event: Event) -> Event | None:
        return event

    async def after_publish(self, event: Event) -> None:
        pass


class _DroppingMiddleware:
    """Middleware that drops all events."""

    async def before_publish(self, event: Event) -> Event | None:
        return None

    async def after_publish(self, event: Event) -> None:
        pass


class _TransformingMiddleware:
    """Middleware that changes the event's metadata."""

    async def before_publish(self, event: Event) -> Event | None:
        # Pydantic frozen model, so we create a copy with updated metadata
        return event.model_copy(update={"metadata": {"transformed": True}})

    async def after_publish(self, event: Event) -> None:
        pass


class _ErrorAfterMiddleware:
    """Middleware that raises in after_publish."""

    async def before_publish(self, event: Event) -> Event | None:
        return event

    async def after_publish(self, event: Event) -> None:
        raise RuntimeError("after_publish error")


async def test_middleware_chain_before():
    """process_before() should pass events through all middleware in order."""
    chain = MiddlewareChain()
    chain.add(_PassthroughMiddleware())
    chain.add(_PassthroughMiddleware())

    event = _make_event()
    result = await chain.process_before(event)
    assert result is not None
    assert result.event_type == "test.event"


async def test_middleware_chain_after():
    """process_after() should call all middleware after hooks."""
    chain = MiddlewareChain()
    metrics = MetricsMiddleware()
    chain.add(metrics)

    event = _make_event()
    await chain.process_after(event)
    assert metrics.after_count == 1


async def test_middleware_drop_event():
    """process_before() should stop and return None when a middleware drops."""
    chain = MiddlewareChain()
    metrics = MetricsMiddleware()
    chain.add(_DroppingMiddleware())
    chain.add(metrics)  # This should NOT be called

    event = _make_event()
    result = await chain.process_before(event)
    assert result is None
    # The MetricsMiddleware after the drop should not have been called
    assert metrics.before_count == 0


async def test_middleware_transform_event():
    """process_before() should propagate transformed events."""
    chain = MiddlewareChain()
    chain.add(_TransformingMiddleware())

    event = _make_event()
    result = await chain.process_before(event)
    assert result is not None
    assert result.metadata.get("transformed") is True


async def test_middleware_after_error_swallowed():
    """process_after() should swallow exceptions from individual middleware."""
    chain = MiddlewareChain()
    chain.add(_ErrorAfterMiddleware())
    metrics = MetricsMiddleware()
    chain.add(metrics)

    event = _make_event()
    # Should not raise even though _ErrorAfterMiddleware raises
    await chain.process_after(event)
    # MetricsMiddleware should still have been called despite the error
    assert metrics.after_count == 1


async def test_logging_middleware():
    """LoggingMiddleware should record before/after entries."""
    mw = LoggingMiddleware()
    event = _make_event("my.event")

    result = await mw.before_publish(event)
    assert result is event  # unchanged
    assert len(mw.log) == 1
    assert "before:my.event" in mw.log[0]

    await mw.after_publish(event)
    assert len(mw.log) == 2
    assert "after:my.event" in mw.log[1]


async def test_metrics_middleware():
    """MetricsMiddleware should count before/after invocations."""
    mw = MetricsMiddleware()
    assert mw.before_count == 0
    assert mw.after_count == 0

    e1 = _make_event()
    e2 = _make_event()

    await mw.before_publish(e1)
    await mw.before_publish(e2)
    assert mw.before_count == 2

    await mw.after_publish(e1)
    assert mw.after_count == 1


async def test_middleware_chain_empty():
    """An empty chain should pass events through unchanged."""
    chain = MiddlewareChain()
    event = _make_event()

    result = await chain.process_before(event)
    assert result is event

    # after should be a no-op
    await chain.process_after(event)
