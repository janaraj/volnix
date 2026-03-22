"""Tests for terrarium.registry.composition."""
import pytest
from terrarium.registry.composition import create_default_registry
from terrarium.registry.registry import EngineRegistry
from terrarium.core.protocols import PipelineStep, StateEngineProtocol


def test_create_default_registry():
    reg = create_default_registry()
    assert isinstance(reg, EngineRegistry)
    assert len(reg.list_engines()) == 10


def test_all_engines_registered():
    reg = create_default_registry()
    expected = {
        "state", "policy", "permission", "budget", "responder",
        "adapter", "animator", "reporter", "feedback", "world_compiler",
    }
    assert set(reg.list_engines()) == expected


def test_topo_sort_no_cycles():
    reg = create_default_registry()
    order = reg.resolve_initialization_order()
    assert order[0] == "state"
    assert len(order) == 10
    # adapter depends on permission — must come after
    assert order.index("permission") < order.index("adapter")
    # Exact expected order (deterministic Kahn's with sorted queues)
    expected = [
        "state", "animator", "budget", "feedback", "permission",
        "adapter", "policy", "reporter", "responder", "world_compiler",
    ]
    assert order == expected


def test_pipeline_steps_complete():
    reg = create_default_registry()
    steps = reg.get_pipeline_steps()
    expected_steps = {"commit", "policy", "permission", "budget", "responder", "capability"}
    assert set(steps.keys()) == expected_steps


def test_protocol_resolution():
    reg = create_default_registry()
    # StateEngine implements PipelineStep (step_name="commit")
    state = reg.get_protocol("state", PipelineStep)
    assert state.step_name == "commit"
