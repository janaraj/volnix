"""Tests for terrarium.registry.wiring."""
import pytest
from unittest.mock import AsyncMock
from terrarium.registry.registry import EngineRegistry
from terrarium.registry.wiring import wire_engines, inject_dependencies, shutdown_engines
from terrarium.config.schema import TerrariumConfig
from tests.registry.conftest import make_mock_engine, make_mock_bus


@pytest.mark.asyncio
async def test_wire_engines():
    reg = EngineRegistry()
    reg.register(make_mock_engine("state"))
    reg.register(make_mock_engine("policy", deps=["state"]))
    bus = make_mock_bus()
    config = TerrariumConfig()
    await wire_engines(reg, bus, config)
    for name in reg.list_engines():
        engine = reg.get(name)
        assert engine._started is True
        assert engine._bus is bus
        assert engine._healthy is True


@pytest.mark.asyncio
async def test_wire_respects_order():
    init_order = []
    reg = EngineRegistry()
    state = make_mock_engine("state")
    policy = make_mock_engine("policy", deps=["state"])

    orig_init_state = state.initialize
    async def track_state(config, bus):
        init_order.append("state")
        await orig_init_state(config, bus)
    state.initialize = track_state

    orig_init_policy = policy.initialize
    async def track_policy(config, bus):
        init_order.append("policy")
        await orig_init_policy(config, bus)
    policy.initialize = track_policy

    reg.register(state)
    reg.register(policy)
    await wire_engines(reg, make_mock_bus(), TerrariumConfig())
    assert init_order.index("state") < init_order.index("policy")


@pytest.mark.asyncio
async def test_wire_config_extraction():
    reg = EngineRegistry()
    reg.register(make_mock_engine("state"))
    config = TerrariumConfig()
    await wire_engines(reg, make_mock_bus(), config)
    engine = reg.get("state")
    # StateConfig has db_path field
    assert "db_path" in engine._config


@pytest.mark.asyncio
async def test_wire_bus_subscriptions():
    reg = EngineRegistry()
    reg.register(make_mock_engine("state", subs=["world", "simulation"]))
    bus = make_mock_bus()
    await wire_engines(reg, bus, TerrariumConfig())
    topics = [call.args[0] for call in bus.subscribe.call_args_list]
    assert "world" in topics
    assert "simulation" in topics


@pytest.mark.asyncio
async def test_wire_missing_config_graceful():
    """Engine without a matching config section gets empty dict."""
    reg = EngineRegistry()
    engine = make_mock_engine("nonexistent_engine")
    reg.register(engine)
    await wire_engines(reg, make_mock_bus(), TerrariumConfig())
    assert engine._config == {}


@pytest.mark.asyncio
async def test_inject_dependencies():
    reg = EngineRegistry()
    state = make_mock_engine("state")
    policy = make_mock_engine("policy", deps=["state"])
    reg.register(state)
    reg.register(policy)
    await inject_dependencies(policy, reg)
    assert "state" in policy._dependencies
    assert policy._dependencies["state"] is state


@pytest.mark.asyncio
async def test_inject_empty_deps():
    reg = EngineRegistry()
    engine = make_mock_engine("state")
    reg.register(engine)
    await inject_dependencies(engine, reg)
    assert engine._dependencies == {}


@pytest.mark.asyncio
async def test_shutdown_engines():
    reg = EngineRegistry()
    reg.register(make_mock_engine("state"))
    reg.register(make_mock_engine("policy", deps=["state"]))
    bus = make_mock_bus()
    await wire_engines(reg, bus, TerrariumConfig())
    # All started
    assert reg.get("state")._started is True
    assert reg.get("policy")._started is True
    await shutdown_engines(reg)
    assert reg.get("state")._started is False
    assert reg.get("policy")._started is False
