"""Tests for terrarium.core.errors — custom exception hierarchy."""
import pytest
from terrarium.core.errors import (
    TerrariumError, ConfigError, EngineError,
    PipelineStepError, ValidationError,
)


def test_terrarium_error_context():
    ...


def test_config_error_hierarchy():
    ...


def test_engine_error_has_engine_name():
    ...


def test_pipeline_step_error_has_step_name():
    ...


def test_validation_error_has_type():
    ...


def test_error_inheritance():
    ...
