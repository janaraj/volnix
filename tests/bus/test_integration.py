"""Integration tests for the event bus with real persistence."""
import asyncio
import pytest
from datetime import datetime, timezone

from volnix.bus.bus import EventBus
from volnix.bus.config import BusConfig
from volnix.bus.middleware import MetricsMiddleware
from volnix.core.events import Event
from volnix.core.types import Timestamp
from volnix.persistence.config import PersistenceConfig
from volnix.persistence.manager import ConnectionManager
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


async def test_bus_with_real_persistence(tmp_path):
    """Full lifecycle: ConnectionManager -> EventBus with persistence."""
    # Set up ConnectionManager
    config = PersistenceConfig(base_dir=str(tmp_path))
    mgr = ConnectionManager(config)
    await mgr.initialize()

    # Get a database via ConnectionManager
    db = await mgr.get_connection("events")

    # Create EventBus with the managed database
    bus_config = BusConfig(persistence_enabled=True)
    bus = EventBus(bus_config, db=db)
    await bus.initialize()

    # Subscribe and publish
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    await bus.subscribe("test.event", handler)

    e1 = _make_event("test.event")
    await bus.publish(e1)
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0].event_id == e1.event_id

    # Verify persistence
    count = await bus.get_event_count()
    assert count == 1

    # Shutdown bus (does NOT close db)
    await bus.shutdown()

    # ConnectionManager closes everything
    await mgr.shutdown()


async def test_publish_persist_replay_cycle(tmp_path):
    """Publish -> persist -> replay -> verify cycle."""
    db = SQLiteDatabase(str(tmp_path / "cycle.db"))
    await db.connect()

    bus_config = BusConfig(persistence_enabled=True)
    bus = EventBus(bus_config, db=db)
    await bus.initialize()

    # Publish several events
    events = [_make_event(f"type.{i}") for i in range(5)]
    for e in events:
        await bus.publish(e)

    # Verify event count
    assert await bus.get_event_count() == 5

    # Replay all
    replayed = await bus.replay()
    assert len(replayed) == 5
    for i, e in enumerate(replayed):
        assert e.event_type == f"type.{i}"

    # Replay with type filter
    replayed_filtered = await bus.replay(event_types=["type.2"])
    assert len(replayed_filtered) == 1
    assert replayed_filtered[0].event_type == "type.2"

    # Replay from sequence
    replayed_range = await bus.replay(from_sequence=3)
    assert len(replayed_range) == 3

    # Replay to callback
    callback_received: list[Event] = []

    async def cb(event: Event) -> None:
        callback_received.append(event)

    await bus.replay(callback=cb)
    assert len(callback_received) == 5

    await bus.shutdown()
    await db.close()


async def test_bus_middleware_with_persistence(tmp_path):
    """Middleware and persistence should work together."""
    db = SQLiteDatabase(str(tmp_path / "mw.db"))
    await db.connect()

    bus_config = BusConfig(persistence_enabled=True)
    bus = EventBus(bus_config, db=db)
    metrics = MetricsMiddleware()
    bus.add_middleware(metrics)
    await bus.initialize()

    await bus.publish(_make_event("a"))
    await bus.publish(_make_event("b"))

    assert metrics.before_count == 2
    assert metrics.after_count == 2
    assert await bus.get_event_count() == 2

    await bus.shutdown()
    await db.close()


async def test_bus_multiple_subscribers_and_replay(tmp_path):
    """Multiple subscribers and replay should all work together."""
    db = SQLiteDatabase(str(tmp_path / "multi.db"))
    await db.connect()

    bus_config = BusConfig(persistence_enabled=True)
    bus = EventBus(bus_config, db=db)
    await bus.initialize()

    received_a: list[Event] = []
    received_all: list[Event] = []

    async def handler_a(event: Event) -> None:
        received_a.append(event)

    async def handler_all(event: Event) -> None:
        received_all.append(event)

    await bus.subscribe("type.a", handler_a)
    await bus.subscribe("*", handler_all)

    await bus.publish(_make_event("type.a"))
    await bus.publish(_make_event("type.b"))
    await asyncio.sleep(0.05)

    assert len(received_a) == 1
    assert len(received_all) == 2

    # Replay should also work
    replayed = await bus.replay()
    assert len(replayed) == 2

    await bus.shutdown()
    await db.close()
