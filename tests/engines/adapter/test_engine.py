"""Tests for volnix.engines.adapter.engine -- AdapterEngine capability checks."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from volnix.core.context import ActionContext
from volnix.core.types import ActorId, ServiceId, StepVerdict
from volnix.engines.adapter.engine import AgentAdapterEngine


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
    now = datetime.now(UTC)
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

    now = datetime.now(UTC)
    event = Event(
        event_type="test.event",
        timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
    )
    # Should not raise
    await engine._handle_event(event)


# ---------------------------------------------------------------------------
# Game-action short-circuit
# ---------------------------------------------------------------------------


def _make_game_ctx(action: str = "negotiate_propose") -> ActionContext:
    """Context for a game action (service_id == 'game')."""
    now = datetime.now(UTC)
    return ActionContext(
        request_id="req-game-001",
        actor_id=ActorId("buyer-test"),
        service_id=ServiceId("game"),
        action=action,
        input_data={
            "deal_id": "deal-001",
            "price": 80,
            "delivery_weeks": 3,
            "payment_days": 45,
            "warranty_months": 18,
        },
        world_time=now,
        wall_time=now,
        tick=1,
    )


@pytest.mark.asyncio
async def test_game_action_resolves_without_pack_lookup():
    """Game actions with service_id='game' ALLOW without consulting packs.

    The GameRunner registers structured game-move tools (e.g.
    ``negotiate_propose``) directly on the agency engine; they have no
    Tier 1 pack or Tier 2 profile backing. The capability step must
    short-circuit to ALLOW before attempting to look them up, otherwise
    the pipeline blocks at ``BLOCKED_AT_CAPABILITY``.
    """
    pack_registry = MagicMock()
    pack_registry.has_tool.return_value = False  # not in any pack
    engine = _make_engine(pack_registry=pack_registry)

    ctx = _make_game_ctx(action="negotiate_propose")
    result = await engine.execute(ctx)

    assert result.verdict == StepVerdict.ALLOW
    assert "negotiate_propose" in result.message
    assert result.events[0].event_type == "capability.resolved"
    assert result.events[0].resolved_tier == "game"
    # Crucially: pack_registry must NOT be consulted for game actions
    pack_registry.has_tool.assert_not_called()


@pytest.mark.asyncio
async def test_game_action_short_circuit_covers_all_negotiation_tools():
    """All four negotiation tools take the game short-circuit."""
    pack_registry = MagicMock()
    pack_registry.has_tool.return_value = False
    engine = _make_engine(pack_registry=pack_registry)

    for action in (
        "negotiate_propose",
        "negotiate_counter",
        "negotiate_accept",
        "negotiate_reject",
    ):
        ctx = _make_game_ctx(action=action)
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.ALLOW, f"{action} was blocked"
        assert result.events[0].resolved_tier == "game"

    pack_registry.has_tool.assert_not_called()


@pytest.mark.asyncio
async def test_non_game_action_still_checks_packs():
    """Regression guard: real services still go through pack lookup."""
    pack_registry = MagicMock()
    pack_registry.has_tool.return_value = True
    engine = _make_engine(pack_registry=pack_registry)

    ctx = _make_ctx("email_send")  # service_id="gmail", NOT "game"
    result = await engine.execute(ctx)

    assert result.verdict == StepVerdict.ALLOW
    # For non-game actions, pack_registry IS consulted
    pack_registry.has_tool.assert_called_once_with("email_send")
