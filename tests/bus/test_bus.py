"""Tests for volnix.bus.bus — EventBus publish/subscribe and metrics."""
import asyncio
import pytest
from datetime import datetime, timezone

from volnix.bus.bus import EventBus
from volnix.bus.config import BusConfig
from volnix.bus.middleware import LoggingMiddleware, MetricsMiddleware
from volnix.bus.types import BusMetrics
from volnix.core.events import Event
from volnix.core.types import EventId, Timestamp
from volnix.persistence.sqlite import SQLiteDatabase


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


@pytest.fixture
async def db(tmp_path):
    """Create a temporary SQLite database."""
    database = SQLiteDatabase(str(tmp_path / "bus_test.db"))
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def bus_no_persist():
    """EventBus without persistence."""
    config = BusConfig(persistence_enabled=False)
    bus = EventBus(config, db=None)
    await bus.initialize()
    yield bus
    await bus.shutdown()


@pytest.fixture
async def bus_with_persist(db):
    """EventBus with persistence enabled."""
    config = BusConfig(persistence_enabled=True)
    bus = EventBus(config, db=db)
    await bus.initialize()
    yield bus
    await bus.shutdown()


async def test_bus_initialize(bus_no_persist):
    """initialize() should set up the bus without errors."""
    assert bus_no_persist._initialized is True


async def test_bus_initialize_persistence_requires_db():
    """initialize() should raise ValueError when persistence is on but no db."""
    config = BusConfig(persistence_enabled=True)
    bus = EventBus(config, db=None)
    with pytest.raises(ValueError, match="persistence_enabled"):
        await bus.initialize()


async def test_bus_publish_subscribe(bus_no_persist):
    """Events published to a type should be received by subscribers."""
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    await bus_no_persist.subscribe("test.event", handler)

    event = _make_event("test.event")
    await bus_no_persist.publish(event)
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].event_id == event.event_id


async def test_bus_wildcard_subscription(bus_no_persist):
    """Wildcard '*' subscribers should receive events of all types."""
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    await bus_no_persist.subscribe("*", handler)

    await bus_no_persist.publish(_make_event("type.a"))
    await bus_no_persist.publish(_make_event("type.b"))
    await bus_no_persist.publish(_make_event("type.c"))
    await asyncio.sleep(0.05)

    assert len(received) == 3


async def test_bus_unsubscribe(bus_no_persist):
    """After unsubscribe, the callback should stop receiving events."""
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    await bus_no_persist.subscribe("test.event", handler)
    await bus_no_persist.publish(_make_event("test.event"))
    await asyncio.sleep(0.05)
    assert len(received) == 1

    await bus_no_persist.unsubscribe("test.event", handler)
    await bus_no_persist.publish(_make_event("test.event"))
    await asyncio.sleep(0.05)
    # No new events should arrive
    assert len(received) == 1


async def test_bus_event_count(bus_with_persist):
    """get_event_count() should track the number of persisted events."""
    assert await bus_with_persist.get_event_count() == 0

    await bus_with_persist.publish(_make_event())
    await bus_with_persist.publish(_make_event())
    assert await bus_with_persist.get_event_count() == 2


async def test_bus_event_count_no_persistence(bus_no_persist):
    """get_event_count() returns 0 when persistence is off."""
    await bus_no_persist.publish(_make_event())
    assert await bus_no_persist.get_event_count() == 0


async def test_bus_metrics(bus_no_persist):
    """get_metrics() should return a BusMetrics snapshot."""
    await bus_no_persist.publish(_make_event())
    await bus_no_persist.publish(_make_event())

    metrics = await bus_no_persist.get_metrics()
    assert isinstance(metrics, BusMetrics)
    assert metrics.events_published == 2


async def test_bus_replay(bus_with_persist):
    """replay() should return persisted events."""
    e1 = _make_event("type.a")
    e2 = _make_event("type.b")
    await bus_with_persist.publish(e1)
    await bus_with_persist.publish(e2)

    events = await bus_with_persist.replay()
    assert len(events) == 2
    assert events[0].event_type == "type.a"
    assert events[1].event_type == "type.b"


async def test_bus_replay_with_callback(bus_with_persist):
    """replay(callback=...) should deliver events to the callback."""
    await bus_with_persist.publish(_make_event("x"))
    await bus_with_persist.publish(_make_event("y"))

    received: list[Event] = []

    async def cb(event: Event) -> None:
        received.append(event)

    result = await bus_with_persist.replay(callback=cb)
    assert result == []  # empty when callback used
    assert len(received) == 2


async def test_bus_replay_no_persistence(bus_no_persist):
    """replay() returns empty when persistence is disabled."""
    await bus_no_persist.publish(_make_event())
    events = await bus_no_persist.replay()
    assert events == []


async def test_bus_middleware_integration(bus_no_persist):
    """Middleware hooks should be invoked during publish."""
    metrics = MetricsMiddleware()
    bus_no_persist.add_middleware(metrics)

    await bus_no_persist.publish(_make_event())
    await bus_no_persist.publish(_make_event())

    assert metrics.before_count == 2
    assert metrics.after_count == 2


async def test_bus_consumer_failure_does_not_crash():
    """A failing callback should not crash the bus or other subscribers."""
    config = BusConfig(persistence_enabled=False)
    bus = EventBus(config, db=None)
    await bus.initialize()

    good_received: list[Event] = []

    async def failing_handler(event: Event) -> None:
        raise RuntimeError("subscriber error")

    async def good_handler(event: Event) -> None:
        good_received.append(event)

    await bus.subscribe("test", failing_handler)
    await bus.subscribe("test", good_handler)

    await bus.publish(_make_event("test"))
    await asyncio.sleep(0.05)

    # Good handler should still receive events despite failing handler
    assert len(good_received) == 1

    await bus.shutdown()


async def test_bus_shutdown_cancels_tasks(bus_no_persist):
    """shutdown() should cancel all consumer tasks."""
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    await bus_no_persist.subscribe("test", handler)
    await bus_no_persist.publish(_make_event("test"))
    await asyncio.sleep(0.05)
    assert len(received) == 1

    await bus_no_persist.shutdown()

    # After shutdown, published events should not be delivered
    # (bus is shut down, but publishing still goes through fanout
    # to the queue -- the consumer task is cancelled so it won't drain)
