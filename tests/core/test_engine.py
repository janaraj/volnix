"""Tests for volnix.core.engine — BaseEngine lifecycle and event wiring."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from volnix.core.engine import BaseEngine
from volnix.core.events import Event
from volnix.core.types import Timestamp


class ConcreteEngine(BaseEngine):
    engine_name = "test_engine"
    subscriptions = ["world", "simulation"]
    dependencies = ["state"]

    async def _handle_event(self, event):
        pass


def _make_event():
    return Event(
        event_type="test",
        timestamp=Timestamp(
            world_time=datetime.now(UTC),
            wall_time=datetime.now(UTC),
            tick=0,
        ),
    )


class TestBaseEngine:
    """Verify BaseEngine class variables, lifecycle, and event plumbing."""

    def test_base_engine_class_vars(self):
        e = ConcreteEngine()
        assert e.engine_name == "test_engine"
        assert e.subscriptions == ["world", "simulation"]
        assert e.dependencies == ["state"]

    async def test_engine_lifecycle_initialize(self):
        e = ConcreteEngine()
        bus = AsyncMock()
        await e.initialize({"key": "val"}, bus)
        assert e._config == {"key": "val"}
        assert e._bus is bus
        assert e._healthy is True

    async def test_engine_lifecycle_start_stop(self):
        e = ConcreteEngine()
        bus = AsyncMock()
        bus.subscribe = AsyncMock()
        bus.unsubscribe = AsyncMock()
        await e.initialize({}, bus)
        await e.start()
        assert e._started is True
        assert bus.subscribe.call_count == 2  # world, simulation
        await e.stop()
        assert e._started is False

    async def test_engine_health_check(self):
        e = ConcreteEngine()
        await e.initialize({}, AsyncMock())
        result = await e.health_check()
        assert result["engine"] == "test_engine"
        assert result["healthy"] is True
        assert result["started"] is False

    async def test_engine_event_subscription(self):
        e = ConcreteEngine()
        bus = AsyncMock()
        bus.subscribe = AsyncMock()
        await e.initialize({}, bus)
        await e.start()
        topics = [call.args[0] for call in bus.subscribe.call_args_list]
        assert "world" in topics
        assert "simulation" in topics

    async def test_engine_publish(self):
        e = ConcreteEngine()
        bus = AsyncMock()
        bus.publish = AsyncMock()
        await e.initialize({}, bus)
        event = _make_event()
        await e.publish(event)
        bus.publish.assert_called_once_with(event)


# Additional tests outside the class:


async def test_init_defaults():
    e = ConcreteEngine()
    assert e._bus is None
    assert e._config == {}
    assert e._started is False
    assert e._healthy is False
    assert e._dependencies == {}


async def test_publish_no_bus():
    e = ConcreteEngine()
    event = _make_event()
    await e.publish(event)  # should not raise


async def test_dispatch_calls_handle():
    e = ConcreteEngine()
    e._handle_event = AsyncMock()
    event = _make_event()
    await e._dispatch_event(event)
    e._handle_event.assert_called_once_with(event)


async def test_dispatch_error_publishes():
    e = ConcreteEngine()
    bus = AsyncMock()
    bus.publish = AsyncMock()
    await e.initialize({}, bus)
    e._handle_event = AsyncMock(side_effect=ValueError("test error"))
    event = _make_event()
    await e._dispatch_event(event)
    # Should have published an error event
    assert bus.publish.called
