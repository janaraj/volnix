"""Tests for terrarium.config.validation — cross-section config validation."""
import pytest
from terrarium.config.schema import TerrariumConfig
from terrarium.config.validation import ConfigValidator


@pytest.fixture
def validator():
    return ConfigValidator()


@pytest.fixture
def default_config():
    return TerrariumConfig()


def test_validate_pipeline_steps_valid(validator, default_config):
    """Valid pipeline steps produce no errors."""
    engines = ["permission", "policy", "budget", "capability", "responder", "validation", "commit"]
    errors = validator.validate_pipeline_steps(default_config, engines)
    assert errors == []


def test_validate_pipeline_steps_invalid(validator):
    """Pipeline steps referencing missing engines produce errors."""
    config = TerrariumConfig.model_validate({
        "pipeline": {"steps": ["permission", "nonexistent_step"]}
    })
    engines = ["permission", "policy", "budget"]
    errors = validator.validate_pipeline_steps(config, engines)
    assert len(errors) == 1
    assert "nonexistent_step" in errors[0]


def test_validate_llm_routing_valid(validator):
    """Valid LLM routing with matching providers produces no errors."""
    config = TerrariumConfig.model_validate({
        "llm": {
            "providers": {"anthropic": {"type": "anthropic"}},
            "routing": {"world_compiler": {"provider": "anthropic", "model": "claude"}},
        }
    })
    errors = validator.validate_llm_routing(config)
    assert errors == []


def test_validate_llm_routing_invalid(validator):
    """LLM routing referencing unknown provider produces errors."""
    config = TerrariumConfig.model_validate({
        "llm": {
            "providers": {"anthropic": {"type": "anthropic"}},
            "routing": {"world_compiler": {"provider": "nonexistent", "model": "m"}},
        }
    })
    errors = validator.validate_llm_routing(config)
    assert len(errors) == 1
    assert "nonexistent" in errors[0]


def test_validate_cross_references(validator, default_config):
    """Default config passes cross-reference validation."""
    errors = validator.validate_cross_references(default_config)
    assert errors == []


def test_validate_all(validator, default_config):
    """Default config passes all validation checks."""
    errors = validator.validate_all(default_config)
    assert errors == []


def test_validate_reality_preset_invalid(validator):
    """Invalid reality preset produces an error."""
    config = TerrariumConfig.model_validate({
        "simulation": {"reality": {"preset": "fantasy"}}
    })
    errors = validator.validate_cross_references(config)
    assert any("fantasy" in e for e in errors)


def test_validate_simulation_mode_invalid(validator):
    """Invalid simulation mode produces an error."""
    config = TerrariumConfig.model_validate({
        "simulation": {"mode": "chaos"}
    })
    errors = validator.validate_cross_references(config)
    assert any("chaos" in e for e in errors)


def test_validate_all_returns_empty_when_valid(validator, default_config):
    """validate_all returns an empty list for a fully valid default config."""
    errors = validator.validate_all(default_config)
    assert isinstance(errors, list)
    assert len(errors) == 0
