"""Tests for volnix.registry.health."""
import pytest
from unittest.mock import AsyncMock
from volnix.registry.registry import EngineRegistry
from volnix.registry.health import HealthAggregator
from volnix.registry.wiring import wire_engines
from volnix.config.schema import VolnixConfig
from tests.registry.conftest import make_mock_engine, make_mock_bus


@pytest.mark.asyncio
async def test_health_check_all():
    reg = EngineRegistry()
    reg.register(make_mock_engine("state"))
    reg.register(make_mock_engine("policy", deps=["state"]))
    await wire_engines(reg, make_mock_bus(), VolnixConfig())
    health = HealthAggregator(reg)
    results = await health.check_all()
    assert len(results) == 2
    assert results["state"]["healthy"] is True
    assert results["policy"]["healthy"] is True


@pytest.mark.asyncio
async def test_health_check_single():
    reg = EngineRegistry()
    reg.register(make_mock_engine("state"))
    await wire_engines(reg, make_mock_bus(), VolnixConfig())
    health = HealthAggregator(reg)
    result = await health.check_engine("state")
    assert result["engine"] == "state"
    assert result["started"] is True


@pytest.mark.asyncio
async def test_is_healthy_all_pass():
    reg = EngineRegistry()
    reg.register(make_mock_engine("state"))
    await wire_engines(reg, make_mock_bus(), VolnixConfig())
    health = HealthAggregator(reg)
    await health.check_all()
    assert health.is_healthy() is True


@pytest.mark.asyncio
async def test_is_healthy_one_fail():
    reg = EngineRegistry()
    reg.register(make_mock_engine("state"))
    reg.register(make_mock_engine("policy", deps=["state"]))
    await wire_engines(reg, make_mock_bus(), VolnixConfig())
    reg.get("policy")._healthy = False
    health = HealthAggregator(reg)
    await health.check_all()
    assert health.is_healthy() is False


def test_is_healthy_before_check():
    reg = EngineRegistry()
    health = HealthAggregator(reg)
    assert health.is_healthy() is False


@pytest.mark.asyncio
async def test_health_check_error():
    reg = EngineRegistry()
    engine = make_mock_engine("broken")
    reg.register(engine)
    engine.health_check = AsyncMock(side_effect=RuntimeError("crash"))
    health = HealthAggregator(reg)
    results = await health.check_all()
    assert results["broken"]["healthy"] is False
    assert "error" in results["broken"]


@pytest.mark.asyncio
async def test_check_missing_engine():
    reg = EngineRegistry()
    health = HealthAggregator(reg)
    with pytest.raises(KeyError):
        await health.check_engine("nonexistent")
