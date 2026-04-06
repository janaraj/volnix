"""Tests for volnix.engines.adapter.engine -- AdapterEngine capability checks."""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from volnix.engines.adapter.engine import AgentAdapterEngine
from volnix.core.context import ActionContext
from volnix.core.types import ActorId, ServiceId, StepVerdict


def _make_engine(pack_registry=None):
    """Create an AgentAdapterEngine, optionally with a pack_registry."""
    engine = AgentAdapterEngine()
    engine._config = {}
    engine._bus = MagicMock()
    if pack_registry is not None:
        engine._pack_registry = pack_registry
    return engine


def _make_ctx(action="email_send"):
    """Create a minimal ActionContext for testing."""
    now = datetime.now(timezone.utc)
    return ActionContext(
        request_id="req-test-001",
        actor_id=ActorId("actor-test"),
        service_id=ServiceId("gmail"),
        action=action,
        input_data={},
        world_time=now,
        wall_time=now,
        tick=1,
    )


@pytest.mark.asyncio
async def test_adapter_engine_init():
    """AdapterEngine can be instantiated."""
    engine = _make_engine()
    assert engine.engine_name == "adapter"
    assert engine.step_name == "capability"


@pytest.mark.asyncio
async def test_adapter_capability_check_exists():
    """When pack_registry has the tool, execute returns ALLOW."""
    pack_registry = MagicMock()
    pack_registry.has_tool.return_value = True
    engine = _make_engine(pack_registry=pack_registry)

    ctx = _make_ctx("email_send")
    result = await engine.execute(ctx)

    assert result.verdict == StepVerdict.ALLOW
    assert "email_send" in result.message
    pack_registry.has_tool.assert_called_once_with("email_send")


@pytest.mark.asyncio
async def test_adapter_capability_check_gap():
    """When pack_registry doesn't have the tool, execute returns ERROR with event."""
    pack_registry = MagicMock()
    pack_registry.has_tool.return_value = False
    engine = _make_engine(pack_registry=pack_registry)

    ctx = _make_ctx("nonexistent_tool")
    result = await engine.execute(ctx)

    assert result.verdict == StepVerdict.ERROR
    assert "nonexistent_tool" in result.message
    assert len(result.events) == 1
    assert result.events[0].event_type == "capability.gap"
    assert result.events[0].requested_tool == "nonexistent_tool"


@pytest.mark.asyncio
async def test_adapter_no_pack_registry_passthrough():
    """Without pack_registry, execute returns ALLOW (backward compat)."""
    engine = _make_engine()
    assert engine._pack_registry is None

    ctx = _make_ctx("email_send")
    result = await engine.execute(ctx)

    assert result.verdict == StepVerdict.ALLOW
    assert "pass-through" in result.message


@pytest.mark.asyncio
async def test_adapter_handle_event():
    """_handle_event logs but does not raise."""
    engine = _make_engine()
    from volnix.core.events import Event
    from volnix.core.types import Timestamp

    now = datetime.now(timezone.utc)
    event = Event(
        event_type="test.event",
        timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
    )
    # Should not raise
    await engine._handle_event(event)
