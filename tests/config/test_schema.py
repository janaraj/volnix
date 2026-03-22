"""Tests for terrarium.config.schema — config dataclass defaults and validation."""
import pytest
from terrarium.config.schema import (
    TerrariumConfig,
    SimulationConfig,
    PipelineConfig,
    DashboardConfig,
    FidelityConfig,
)


def test_terrarium_config_defaults():
    """TerrariumConfig() with no args produces valid defaults."""
    config = TerrariumConfig()
    assert config.simulation.mode == "governed"
    assert config.simulation.seed == 42
    assert config.dashboard.enabled is False
    assert config.budget.warning_threshold_pct == 80.0


def test_simulation_config_has_reality():
    """SimulationConfig has a nested reality section with defaults."""
    sim = SimulationConfig()
    assert sim.reality.preset == "realistic"
    assert sim.fidelity.mode == "auto"
    assert sim.time_speed == 1.0


def test_pipeline_config_default_steps():
    """PipelineConfig default steps include the standard pipeline."""
    config = TerrariumConfig()
    assert config.pipeline.steps[0] == "permission"
    assert "commit" in config.pipeline.steps
    assert len(config.pipeline.steps) == 7


def test_llm_config_structure():
    """LLMConfig has defaults, providers dict, and routing dict."""
    config = TerrariumConfig()
    assert config.llm.defaults.max_tokens == 4096
    assert isinstance(config.llm.providers, dict)
    assert isinstance(config.llm.routing, dict)


def test_all_sections_present():
    """All expected sections exist on TerrariumConfig."""
    config = TerrariumConfig()
    expected_sections = [
        "simulation", "pipeline", "bus", "ledger", "persistence",
        "state", "policy", "permission", "budget", "responder",
        "animator", "adapter", "reporter", "feedback", "dashboard",
        "gateway", "runs", "llm", "actors", "templates", "world_compiler",
    ]
    for section in expected_sections:
        assert hasattr(config, section), f"Missing section: {section}"


def test_config_from_dict():
    """TerrariumConfig can be constructed from a partial dict."""
    data = {"simulation": {"seed": 99, "mode": "ungoverned"}}
    config = TerrariumConfig.model_validate(data)
    assert config.simulation.seed == 99
    assert config.simulation.mode == "ungoverned"
    # Other sections should still have defaults
    assert config.bus.queue_size == 1000


def test_all_subsystem_configs_have_defaults():
    """Every subsystem config can be instantiated with no arguments."""
    config = TerrariumConfig()
    # Accessing each section should not raise
    assert config.state.db_path == "data/state.db"
    assert config.policy.condition_timeout_ms == 500
    assert config.permission.cache_ttl_seconds == 300
    assert config.budget.warning_threshold_pct == 80.0
    assert config.responder.max_retries == 2
    assert config.animator.enabled is True
    assert config.adapter.port == 8100
    assert config.reporter.output_dir == "reports"
    assert config.feedback.external_sync_enabled is False
    assert config.world_compiler.default_seed == 42


def test_config_serialization_roundtrip():
    """Config can be serialized to dict and back."""
    original = TerrariumConfig()
    data = original.model_dump()
    restored = TerrariumConfig.model_validate(data)
    assert restored.simulation.seed == original.simulation.seed
    assert restored.pipeline.steps == original.pipeline.steps
    assert restored.budget.critical_threshold_pct == original.budget.critical_threshold_pct


def test_simulation_config_nested():
    """SimulationConfig supports nested reality and fidelity sections."""
    data = {
        "simulation": {
            "seed": 7,
            "reality": {"preset": "harsh"},
            "fidelity": {"mode": "strict"},
        }
    }
    config = TerrariumConfig.model_validate(data)
    assert config.simulation.seed == 7
    assert config.simulation.reality.preset == "harsh"
    assert config.simulation.fidelity.mode == "strict"
