"""Tests for volnix.registry.composition."""

from volnix.core.protocols import PipelineStep
from volnix.registry.composition import create_default_registry
from volnix.registry.registry import EngineRegistry


def test_create_default_registry():
    reg = create_default_registry()
    assert isinstance(reg, EngineRegistry)
    # After B.10 the legacy GameEngine is deleted — only GameOrchestrator
    # is registered (under the ``"game"`` key).
    assert len(reg.list_engines()) == 12


def test_all_engines_registered():
    reg = create_default_registry()
    expected = {
        "state",
        "policy",
        "permission",
        "budget",
        "responder",
        "adapter",
        "animator",
        "reporter",
        "feedback",
        "world_compiler",
        "agency",
        "game",
    }
    assert set(reg.list_engines()) == expected


def test_topo_sort_no_cycles():
    reg = create_default_registry()
    order = reg.resolve_initialization_order()
    assert order[0] == "state"
    assert len(order) == 12
    # adapter depends on permission — must come after
    assert order.index("permission") < order.index("adapter")
    # agency depends on state — must come after
    assert order.index("state") < order.index("agency")
    # game depends on state and budget — must come after both
    assert order.index("state") < order.index("game")
    assert order.index("budget") < order.index("game")
    # Exact expected order (deterministic Kahn's with sorted queues)
    expected = [
        "state",
        "agency",
        "animator",
        "budget",
        "feedback",
        "game",
        "permission",
        "adapter",
        "policy",
        "reporter",
        "responder",
        "world_compiler",
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
