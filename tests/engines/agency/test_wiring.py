"""Tests for Phase 5 wiring: AgencyEngine in registry, config, and protocol."""

from __future__ import annotations

from volnix.config.schema import VolnixConfig
from volnix.core.protocols import AgencyEngineProtocol
from volnix.engines.agency.config import AgencyConfig
from volnix.engines.agency.engine import AgencyEngine
from volnix.registry.composition import create_default_registry
from volnix.simulation.config import SimulationRunnerConfig


def test_agency_engine_in_default_registry():
    """AgencyEngine should be registered in the default composition root."""
    registry = create_default_registry()
    engine = registry.get("agency")
    assert isinstance(engine, AgencyEngine)
    assert engine.engine_name == "agency"


def test_agency_engine_in_engine_list():
    """The 'agency' engine should appear in the list of all registered engines."""
    registry = create_default_registry()
    names = registry.list_engines()
    assert "agency" in names


def test_agency_config_in_volnix_config():
    """VolnixConfig should include an AgencyConfig field with defaults."""
    config = VolnixConfig()
    assert hasattr(config, "agency")
    assert isinstance(config.agency, AgencyConfig)
    assert config.agency.frustration_threshold_tier3 == 0.7
    assert config.agency.batch_size == 5


def test_simulation_runner_config_in_volnix_config():
    """VolnixConfig should include a SimulationRunnerConfig field with defaults."""
    config = VolnixConfig()
    assert hasattr(config, "simulation_runner")
    assert isinstance(config.simulation_runner, SimulationRunnerConfig)
    assert config.simulation_runner.max_logical_time == 86400.0
    assert config.simulation_runner.max_total_events == 50


def test_agency_engine_satisfies_protocol():
    """AgencyEngine should satisfy the AgencyEngineProtocol at runtime."""
    engine = AgencyEngine()
    assert isinstance(engine, AgencyEngineProtocol)


def test_registry_initialization_order_includes_agency():
    """The topological init order should include 'agency' after 'state'."""
    registry = create_default_registry()
    order = registry.resolve_initialization_order()
    assert "agency" in order
    assert order.index("state") < order.index("agency")


def test_default_registry_engine_count():
    """Ensure registration of agency doesn't break existing engine count.

    Previous count was 10 (state, policy, permission, budget, responder,
    adapter, animator, reporter, feedback, world_compiler). Then 11 with
    agency, 12 with game, and 13 with Cycle B's game_orchestrator
    (coexists with legacy game until B.10).
    """
    registry = create_default_registry()
    names = registry.list_engines()
    assert len(names) == 13
