"""Tests for volnix.core.errors — custom exception hierarchy."""
import pytest
from volnix.core.errors import (
    VolnixError, ConfigError, EngineError, EngineInitError,
    EngineDependencyError, PipelineStepError, ValidationError,
)


def test_volnix_error_context():
    err = VolnixError("something broke", context={"key": "val"})
    assert str(err) == "something broke"
    assert err.message == "something broke"
    assert err.context == {"key": "val"}


def test_config_error_hierarchy():
    err = ConfigError("bad config")
    assert isinstance(err, VolnixError)
    assert err.message == "bad config"


def test_engine_error_has_engine_name():
    err = EngineError("init failed", engine_name="state")
    assert err.engine_name == "state"
    assert err.message == "init failed"
    assert isinstance(err, VolnixError)


def test_pipeline_step_error_has_step_name():
    err = PipelineStepError("step failed", step_name="policy")
    assert err.step_name == "policy"
    assert err.message == "step failed"


def test_validation_error_has_type():
    err = ValidationError("invalid", validation_type="schema")
    assert err.validation_type == "schema"
    assert err.message == "invalid"


def test_error_inheritance():
    err = EngineDependencyError("missing dep", engine_name="policy")
    assert isinstance(err, EngineDependencyError)
    assert isinstance(err, EngineError)
    assert isinstance(err, VolnixError)
    assert isinstance(err, Exception)
