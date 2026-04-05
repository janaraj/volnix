"""Tests for volnix.bus.replay — event replay by range, time, and type."""
import asyncio
import pytest
from datetime import datetime, timezone

from volnix.bus.fanout import TopicFanout
from volnix.bus.persistence import BusPersistence
from volnix.bus.replay import ReplayEngine
from volnix.bus.types import Subscription
from volnix.core.events import Event
from volnix.core.types import Timestamp
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
    database = SQLiteDatabase(str(tmp_path / "replay_test.db"))
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def persistence(db):
    """Create and initialize a BusPersistence."""
    p = BusPersistence(db)
    await p.initialize()
    return p


@pytest.fixture
def fanout():
    """Create a TopicFanout."""
    return TopicFanout()


@pytest.fixture
def engine(persistence, fanout):
    """Create a ReplayEngine."""
    return ReplayEngine(persistence, fanout)


async def test_replay_range(engine, persistence, fanout):
    """replay_range() should replay events within sequence range via fanout."""
    await persistence.persist(_make_event("e1"))
    await persistence.persist(_make_event("e2"))
    await persistence.persist(_make_event("e3"))

    # Set up a subscriber to capture fanout events
    queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)

    async def noop(e: Event) -> None:
        pass

    sub = Subscription(event_type="e1", callback=noop, queue=queue)
    fanout.add_subscriber("e1", sub)

    # We also need a wildcard to capture all
    wq: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)
    wsub = Subscription(event_type="*", callback=noop, queue=wq)
    fanout.add_subscriber("*", wsub)

    count = await engine.replay_range(from_sequence=1)
    assert count == 3
    assert wq.qsize() == 3


async def test_replay_range_with_to_sequence(engine, persistence, fanout):
    """replay_range() with to_sequence should stop at the specified sequence."""
    await persistence.persist(_make_event("e1"))
    await persistence.persist(_make_event("e2"))
    await persistence.persist(_make_event("e3"))
    await persistence.persist(_make_event("e4"))

    wq: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)

    async def noop(e: Event) -> None:
        pass

    wsub = Subscription(event_type="*", callback=noop, queue=wq)
    fanout.add_subscriber("*", wsub)

    count = await engine.replay_range(from_sequence=1, to_sequence=2)
    assert count == 2


async def test_replay_range_with_event_types(engine, persistence, fanout):
    """replay_range() with event_types filter should only replay matching."""
    await persistence.persist(_make_event("type.a"))
    await persistence.persist(_make_event("type.b"))
    await persistence.persist(_make_event("type.a"))

    wq: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)

    async def noop(e: Event) -> None:
        pass

    wsub = Subscription(event_type="*", callback=noop, queue=wq)
    fanout.add_subscriber("*", wsub)

    count = await engine.replay_range(from_sequence=1, event_types=["type.a"])
    assert count == 2


async def test_replay_to_callback(engine, persistence):
    """replay_to_callback() should deliver events to the callback."""
    await persistence.persist(_make_event("x"))
    await persistence.persist(_make_event("y"))

    received: list[Event] = []

    async def cb(event: Event) -> None:
        received.append(event)

    count = await engine.replay_to_callback(cb)
    assert count == 2
    assert len(received) == 2
    assert received[0].event_type == "x"
    assert received[1].event_type == "y"


async def test_replay_to_callback_with_filter(engine, persistence):
    """replay_to_callback() with event_types should filter."""
    await persistence.persist(_make_event("a"))
    await persistence.persist(_make_event("b"))
    await persistence.persist(_make_event("a"))

    received: list[Event] = []

    async def cb(event: Event) -> None:
        received.append(event)

    count = await engine.replay_to_callback(cb, event_types=["a"])
    assert count == 2
    assert all(e.event_type == "a" for e in received)


async def test_replay_to_callback_from_sequence(engine, persistence):
    """replay_to_callback() with from_sequence filters by sequence."""
    await persistence.persist(_make_event("first"))
    await persistence.persist(_make_event("second"))
    await persistence.persist(_make_event("third"))

    received: list[Event] = []

    async def cb(event: Event) -> None:
        received.append(event)

    count = await engine.replay_to_callback(cb, from_sequence=2)
    assert count == 2
    assert received[0].event_type == "second"
    assert received[1].event_type == "third"


async def test_replay_timerange(tmp_path):
    """Test replaying events within a time range."""
    db = SQLiteDatabase(str(tmp_path / "test.db"))
    await db.connect()
    persistence = BusPersistence(db)
    await persistence.initialize()
    fanout = TopicFanout()
    replay = ReplayEngine(persistence, fanout)

    # Persist some events
    for i in range(3):
        event = _make_event(f"timerange_{i}")
        await persistence.persist(event)

    # Replay by time range (broad range to catch all)
    start = datetime(2020, 1, 1)
    end = datetime(2030, 1, 1)
    count = await replay.replay_timerange(start, end)
    assert count == 3

    await db.close()
