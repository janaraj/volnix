"""Tests for terrarium.bus.fanout — fan-out delivery and wildcard matching."""
import asyncio
import pytest
from datetime import datetime, timezone

from terrarium.bus.fanout import TopicFanout
from terrarium.bus.types import Subscription
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


async def _noop_callback(event: Event) -> None:
    """Placeholder async callback that does nothing."""
    pass


async def test_fanout_add_subscriber():
    """add_subscriber() should register a subscription."""
    fanout = TopicFanout()
    sub = Subscription(event_type="test.event", callback=_noop_callback)
    fanout.add_subscriber("test.event", sub)
    assert fanout.get_subscriber_count("test.event") == 1


async def test_fanout_remove_subscriber():
    """remove_subscriber() should unregister the subscription."""
    fanout = TopicFanout()
    sub = Subscription(event_type="test.event", callback=_noop_callback)
    fanout.add_subscriber("test.event", sub)
    assert fanout.get_subscriber_count("test.event") == 1

    fanout.remove_subscriber("test.event", _noop_callback)
    assert fanout.get_subscriber_count("test.event") == 0


async def test_fanout_delivers_to_matching():
    """fanout() should deliver events to subscribers of matching type."""
    fanout = TopicFanout()
    queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)
    sub = Subscription(event_type="my.type", callback=_noop_callback, queue=queue)
    fanout.add_subscriber("my.type", sub)

    event = _make_event("my.type")
    await fanout.fanout(event)

    assert not queue.empty()
    delivered = queue.get_nowait()
    assert delivered.event_id == event.event_id


async def test_fanout_does_not_deliver_to_non_matching():
    """fanout() should NOT deliver to subscribers of different type."""
    fanout = TopicFanout()
    queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)
    sub = Subscription(event_type="other.type", callback=_noop_callback, queue=queue)
    fanout.add_subscriber("other.type", sub)

    event = _make_event("my.type")
    await fanout.fanout(event)

    assert queue.empty()


async def test_fanout_wildcard():
    """Wildcard '*' subscribers should receive ALL events."""
    fanout = TopicFanout()
    queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)
    sub = Subscription(event_type="*", callback=_noop_callback, queue=queue)
    fanout.add_subscriber("*", sub)

    await fanout.fanout(_make_event("type.a"))
    await fanout.fanout(_make_event("type.b"))
    await fanout.fanout(_make_event("type.c"))

    assert queue.qsize() == 3


async def test_fanout_backpressure_drop_oldest():
    """When the queue is full, the oldest event should be dropped."""
    fanout = TopicFanout()
    queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=2)
    sub = Subscription(event_type="test", callback=_noop_callback, queue=queue)
    fanout.add_subscriber("test", sub)

    e1 = _make_event("test")
    e2 = _make_event("test")
    e3 = _make_event("test")

    await fanout.fanout(e1)
    await fanout.fanout(e2)
    # Queue is now full (2/2)
    assert queue.qsize() == 2

    # This should drop e1 (oldest) and add e3
    await fanout.fanout(e3)
    assert queue.qsize() == 2

    # First item should be e2 (e1 was dropped)
    item = queue.get_nowait()
    assert item.event_id == e2.event_id
    item = queue.get_nowait()
    assert item.event_id == e3.event_id


def test_fanout_subscriber_count():
    """get_subscriber_count() should count total and per-type."""
    fanout = TopicFanout()
    sub1 = Subscription(event_type="a", callback=_noop_callback)
    sub2 = Subscription(event_type="a", callback=_noop_callback)
    sub3 = Subscription(event_type="b", callback=_noop_callback)
    sub4 = Subscription(event_type="*", callback=_noop_callback)

    fanout.add_subscriber("a", sub1)
    fanout.add_subscriber("a", sub2)
    fanout.add_subscriber("b", sub3)
    fanout.add_subscriber("*", sub4)

    assert fanout.get_subscriber_count("a") == 2
    assert fanout.get_subscriber_count("b") == 1
    assert fanout.get_subscriber_count("*") == 1
    assert fanout.get_subscriber_count() == 4  # total: 2 + 1 + 1
    assert fanout.get_subscriber_count("nonexistent") == 0


async def test_fanout_multiple_subscribers_same_type():
    """Multiple subscribers for the same type should all receive the event."""
    fanout = TopicFanout()
    q1: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)
    q2: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)

    async def cb1(e: Event) -> None:
        pass

    async def cb2(e: Event) -> None:
        pass

    sub1 = Subscription(event_type="multi", callback=cb1, queue=q1)
    sub2 = Subscription(event_type="multi", callback=cb2, queue=q2)
    fanout.add_subscriber("multi", sub1)
    fanout.add_subscriber("multi", sub2)

    event = _make_event("multi")
    await fanout.fanout(event)

    assert q1.qsize() == 1
    assert q2.qsize() == 1


async def test_fanout_remove_wildcard_subscriber():
    """remove_subscriber() should work for wildcard subscriptions."""
    fanout = TopicFanout()
    sub = Subscription(event_type="*", callback=_noop_callback)
    fanout.add_subscriber("*", sub)
    assert fanout.get_subscriber_count("*") == 1

    fanout.remove_subscriber("*", _noop_callback)
    assert fanout.get_subscriber_count("*") == 0
