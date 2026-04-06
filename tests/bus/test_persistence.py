"""Tests for volnix.bus.persistence — durable event storage."""

from datetime import UTC, datetime

import pytest

from volnix.bus.persistence import BusPersistence
from volnix.core.events import Event
from volnix.core.types import EventId, Timestamp
from volnix.persistence.sqlite import SQLiteDatabase


def _make_event(event_type: str = "test.event", event_id: str | None = None) -> Event:
    """Helper to create a test Event."""
    return Event(
        event_type=event_type,
        timestamp=Timestamp(
            world_time=datetime(2025, 1, 1, tzinfo=UTC),
            wall_time=datetime.now(UTC),
            tick=1,
        ),
        **({"event_id": EventId(event_id)} if event_id else {}),
    )


@pytest.fixture
async def db(tmp_path):
    """Create a temporary SQLite database."""
    database = SQLiteDatabase(str(tmp_path / "bus_test.db"))
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def persistence(db):
    """Create and initialize a BusPersistence."""
    p = BusPersistence(db)
    await p.initialize()
    return p


async def test_bus_persistence_initialize(db):
    """initialize() should create the event_log table."""
    p = BusPersistence(db)
    assert await db.table_exists("event_log") is False
    await p.initialize()
    assert await db.table_exists("event_log") is True


async def test_bus_persistence_persist(persistence):
    """persist() should store an event and return a sequence_id."""
    event = _make_event()
    seq = await persistence.persist(event)
    assert seq == 1


async def test_bus_persistence_query_all(persistence):
    """query() with no filters should return all events in order."""
    e1 = _make_event("type.a")
    e2 = _make_event("type.b")
    e3 = _make_event("type.c")
    await persistence.persist(e1)
    await persistence.persist(e2)
    await persistence.persist(e3)

    events = await persistence.query()
    assert len(events) == 3
    assert events[0].event_type == "type.a"
    assert events[1].event_type == "type.b"
    assert events[2].event_type == "type.c"


async def test_bus_persistence_query_by_type(persistence):
    """query(event_types=...) should filter by event type."""
    await persistence.persist(_make_event("type.a"))
    await persistence.persist(_make_event("type.b"))
    await persistence.persist(_make_event("type.a"))

    events = await persistence.query(event_types=["type.a"])
    assert len(events) == 2
    assert all(e.event_type == "type.a" for e in events)


async def test_bus_persistence_query_range(persistence):
    """query(from_sequence=...) should filter by sequence range."""
    await persistence.persist(_make_event("e1"))
    await persistence.persist(_make_event("e2"))
    await persistence.persist(_make_event("e3"))

    events = await persistence.query(from_sequence=2)
    assert len(events) == 2
    assert events[0].event_type == "e2"
    assert events[1].event_type == "e3"


async def test_bus_persistence_query_limit(persistence):
    """query(limit=...) should cap results."""
    for i in range(5):
        await persistence.persist(_make_event(f"e{i}"))

    events = await persistence.query(limit=3)
    assert len(events) == 3


async def test_bus_persistence_get_count(persistence):
    """get_count() should return the total number of persisted events."""
    assert await persistence.get_count() == 0
    await persistence.persist(_make_event())
    await persistence.persist(_make_event())
    assert await persistence.get_count() == 2


async def test_bus_persistence_get_latest_sequence(persistence):
    """get_latest_sequence() should return the max sequence_id."""
    assert await persistence.get_latest_sequence() == 0
    await persistence.persist(_make_event())
    assert await persistence.get_latest_sequence() == 1
    await persistence.persist(_make_event())
    assert await persistence.get_latest_sequence() == 2


async def test_bus_persistence_shutdown_is_noop(persistence):
    """shutdown() should be a no-op (does not close the database)."""
    await persistence.persist(_make_event())
    await persistence.shutdown()
    # Database should still be usable after shutdown
    count = await persistence.get_count()
    assert count == 1
