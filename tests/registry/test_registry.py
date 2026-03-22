"""Tests for terrarium.registry.registry — EngineRegistry."""
import pytest
from terrarium.registry.registry import EngineRegistry
from terrarium.core.errors import EngineDependencyError
from terrarium.core.protocols import PipelineStep
from tests.registry.conftest import make_mock_engine


def test_register_engine():
    reg = EngineRegistry()
    engine = make_mock_engine("state")
    reg.register(engine)
    assert "state" in reg.list_engines()


def test_register_overwrites():
    reg = EngineRegistry()
    e1 = make_mock_engine("state")
    e2 = make_mock_engine("state")
    reg.register(e1)
    reg.register(e2)
    assert reg.get("state") is e2


def test_register_empty_name_raises():
    reg = EngineRegistry()
    engine = make_mock_engine("")
    # Override to have empty name
    type(engine).engine_name = ""
    with pytest.raises(ValueError):
        reg.register(engine)


def test_get_engine():
    reg = EngineRegistry()
    engine = make_mock_engine("state")
    reg.register(engine)
    assert reg.get("state") is engine


def test_get_engine_missing():
    reg = EngineRegistry()
    with pytest.raises(KeyError, match="not registered"):
        reg.get("nonexistent")


def test_get_step_found():
    reg = EngineRegistry()
    engine = make_mock_engine("state", step_name_val="commit")
    reg.register(engine)
    step = reg.get_step("commit")
    assert step is engine


def test_get_step_not_found():
    reg = EngineRegistry()
    reg.register(make_mock_engine("state"))
    assert reg.get_step("nonexistent") is None


def test_get_pipeline_steps():
    reg = EngineRegistry()
    # 6 with step_name, 4 without
    reg.register(make_mock_engine("state", step_name_val="commit"))
    reg.register(make_mock_engine("policy", deps=["state"], step_name_val="policy"))
    reg.register(make_mock_engine("permission", deps=["state"], step_name_val="permission"))
    reg.register(make_mock_engine("budget", deps=["state"], step_name_val="budget"))
    reg.register(make_mock_engine("responder", deps=["state"], step_name_val="responder"))
    reg.register(make_mock_engine("adapter", deps=["state", "permission"], step_name_val="capability"))
    reg.register(make_mock_engine("animator", deps=["state"]))
    reg.register(make_mock_engine("reporter", deps=["state"]))
    reg.register(make_mock_engine("feedback", deps=["state"]))
    reg.register(make_mock_engine("world_compiler", deps=["state"]))
    steps = reg.get_pipeline_steps()
    assert len(steps) == 6
    assert set(steps.keys()) == {"commit", "policy", "permission", "budget", "responder", "capability"}


def test_get_protocol_match():
    reg = EngineRegistry()
    engine = make_mock_engine("state", step_name_val="commit")
    reg.register(engine)
    result = reg.get_protocol("state", PipelineStep)
    assert result is engine


def test_get_protocol_mismatch():
    reg = EngineRegistry()
    engine = make_mock_engine("animator")  # no step_name -> not PipelineStep
    reg.register(engine)
    with pytest.raises(TypeError, match="does not satisfy"):
        reg.get_protocol("animator", PipelineStep)


def test_list_engines_empty():
    reg = EngineRegistry()
    assert reg.list_engines() == []


def test_topological_sort():
    reg = EngineRegistry()
    reg.register(make_mock_engine("state"))
    reg.register(make_mock_engine("policy", deps=["state"]))
    reg.register(make_mock_engine("permission", deps=["state"]))
    reg.register(make_mock_engine("adapter", deps=["state", "permission"]))
    order = reg.resolve_initialization_order()
    assert order[0] == "state"
    assert order.index("permission") < order.index("adapter")
    assert order.index("state") < order.index("policy")


def test_topological_sort_full_graph():
    reg = EngineRegistry()
    reg.register(make_mock_engine("state"))
    reg.register(make_mock_engine("policy", deps=["state"]))
    reg.register(make_mock_engine("permission", deps=["state"]))
    reg.register(make_mock_engine("budget", deps=["state"]))
    reg.register(make_mock_engine("responder", deps=["state"]))
    reg.register(make_mock_engine("adapter", deps=["state", "permission"]))
    reg.register(make_mock_engine("animator", deps=["state"]))
    reg.register(make_mock_engine("reporter", deps=["state"]))
    reg.register(make_mock_engine("feedback", deps=["state"]))
    reg.register(make_mock_engine("world_compiler", deps=["state"]))
    order = reg.resolve_initialization_order()
    assert len(order) == 10
    assert order[0] == "state"
    assert order.index("adapter") > order.index("permission")


def test_topological_sort_single():
    reg = EngineRegistry()
    reg.register(make_mock_engine("state"))
    assert reg.resolve_initialization_order() == ["state"]


def test_circular_dependency_raises():
    reg = EngineRegistry()
    reg.register(make_mock_engine("a", deps=["b"]))
    reg.register(make_mock_engine("b", deps=["a"]))
    with pytest.raises(EngineDependencyError, match="Circular"):
        reg.resolve_initialization_order()


def test_missing_dependency_raises():
    reg = EngineRegistry()
    reg.register(make_mock_engine("policy", deps=["nonexistent"]))
    with pytest.raises(EngineDependencyError, match="not registered"):
        reg.resolve_initialization_order()


def test_topological_sort_deterministic():
    reg = EngineRegistry()
    reg.register(make_mock_engine("state"))
    reg.register(make_mock_engine("policy", deps=["state"]))
    reg.register(make_mock_engine("budget", deps=["state"]))
    reg.register(make_mock_engine("permission", deps=["state"]))
    first = reg.resolve_initialization_order()
    for _ in range(10):
        assert reg.resolve_initialization_order() == first


def test_topological_sort_empty():
    """Empty registry returns empty list."""
    reg = EngineRegistry()
    assert reg.resolve_initialization_order() == []


def test_topological_sort_linear_chain():
    """Linear chain: C depends on B, B depends on A."""
    reg = EngineRegistry()
    reg.register(make_mock_engine("a"))
    reg.register(make_mock_engine("b", deps=["a"]))
    reg.register(make_mock_engine("c", deps=["b"]))
    assert reg.resolve_initialization_order() == ["a", "b", "c"]


def test_topological_sort_diamond():
    """Diamond: D depends on B and C, B and C both depend on A."""
    reg = EngineRegistry()
    reg.register(make_mock_engine("a"))
    reg.register(make_mock_engine("b", deps=["a"]))
    reg.register(make_mock_engine("c", deps=["a"]))
    reg.register(make_mock_engine("d", deps=["b", "c"]))
    order = reg.resolve_initialization_order()
    assert order == ["a", "b", "c", "d"]


def test_topological_sort_three_node_cycle():
    """3-node cycle: A→B→C→A."""
    reg = EngineRegistry()
    reg.register(make_mock_engine("a", deps=["c"]))
    reg.register(make_mock_engine("b", deps=["a"]))
    reg.register(make_mock_engine("c", deps=["b"]))
    with pytest.raises(EngineDependencyError, match="Circular"):
        reg.resolve_initialization_order()


def test_topological_sort_self_dependency():
    """Self-dependency: A depends on A."""
    reg = EngineRegistry()
    reg.register(make_mock_engine("a", deps=["a"]))
    with pytest.raises(EngineDependencyError, match="Circular"):
        reg.resolve_initialization_order()


def test_topological_sort_multiple_roots():
    """Multiple independent roots, C depends on both."""
    reg = EngineRegistry()
    reg.register(make_mock_engine("alpha"))
    reg.register(make_mock_engine("beta"))
    reg.register(make_mock_engine("gamma", deps=["alpha", "beta"]))
    order = reg.resolve_initialization_order()
    assert order == ["alpha", "beta", "gamma"]  # alpha before beta (lexicographic)


def test_topological_sort_exact_full_graph_order():
    """Full 10-engine graph produces exact deterministic order."""
    reg = EngineRegistry()
    reg.register(make_mock_engine("state"))
    reg.register(make_mock_engine("policy", deps=["state"]))
    reg.register(make_mock_engine("permission", deps=["state"]))
    reg.register(make_mock_engine("budget", deps=["state"]))
    reg.register(make_mock_engine("responder", deps=["state"]))
    reg.register(make_mock_engine("adapter", deps=["state", "permission"]))
    reg.register(make_mock_engine("animator", deps=["state"]))
    reg.register(make_mock_engine("reporter", deps=["state"]))
    reg.register(make_mock_engine("feedback", deps=["state"]))
    reg.register(make_mock_engine("world_compiler", deps=["state"]))
    order = reg.resolve_initialization_order()
    expected = [
        "state", "animator", "budget", "feedback", "permission",
        "adapter", "policy", "reporter", "responder", "world_compiler",
    ]
    assert order == expected
