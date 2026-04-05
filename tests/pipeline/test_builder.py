"""Tests for volnix.pipeline.builder -- pipeline construction from config."""

import pytest

from volnix.core.context import ActionContext, StepResult
from volnix.core.types import StepVerdict
from volnix.pipeline.builder import build_pipeline_from_config
from volnix.pipeline.config import PipelineConfig
from volnix.pipeline.dag import PipelineDAG


# ---------------------------------------------------------------------------
# MockStep helper
# ---------------------------------------------------------------------------

class MockStep:
    """Configurable mock pipeline step for testing."""

    def __init__(self, name, verdict=StepVerdict.ALLOW):
        self._name = name
        self._verdict = verdict

    @property
    def step_name(self):
        return self._name

    async def execute(self, ctx):
        return StepResult(step_name=self._name, verdict=self._verdict)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_from_config():
    """Config has 3 steps, registry has them -- DAG with 3 steps."""
    registry = {
        "a": MockStep("a"),
        "b": MockStep("b"),
        "c": MockStep("c"),
    }
    config = PipelineConfig(steps=["a", "b", "c"])
    dag = build_pipeline_from_config(config, registry)
    assert isinstance(dag, PipelineDAG)
    assert dag.step_names == ["a", "b", "c"]


def test_build_missing_step_raises():
    """Step not in registry -- ValueError."""
    registry = {"a": MockStep("a")}
    config = PipelineConfig(steps=["a", "b"])
    with pytest.raises(ValueError, match="Pipeline step 'b' not found"):
        build_pipeline_from_config(config, registry)


def test_build_preserves_order():
    """Steps in DAG match config order."""
    registry = {
        "c": MockStep("c"),
        "a": MockStep("a"),
        "b": MockStep("b"),
    }
    config = PipelineConfig(steps=["c", "a", "b"])
    dag = build_pipeline_from_config(config, registry)
    assert dag.step_names == ["c", "a", "b"]


def test_build_empty_steps():
    """PipelineConfig(steps=[]) -- empty DAG."""
    registry = {"a": MockStep("a")}
    config = PipelineConfig(steps=[])
    dag = build_pipeline_from_config(config, registry)
    assert dag.step_names == []


def test_build_partial_registry():
    """Registry has extra steps not in config -- only needed ones used."""
    registry = {
        "a": MockStep("a"),
        "b": MockStep("b"),
        "c": MockStep("c"),
        "d": MockStep("d"),
        "e": MockStep("e"),
    }
    config = PipelineConfig(steps=["b", "d"])
    dag = build_pipeline_from_config(config, registry)
    assert dag.step_names == ["b", "d"]
