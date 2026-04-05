"""Tests for volnix.engines.state.causal_graph -- CausalGraph DAG operations."""
import pytest
from volnix.core.types import EventId
from volnix.engines.state.causal_graph import CausalGraph


async def test_add_and_get_causes(graph):
    """A->B edge means get_causes(B) == [A]."""
    a, b = EventId("a"), EventId("b")
    await graph.add_edge(a, b)

    causes = await graph.get_causes(b)
    assert len(causes) == 1
    assert causes[0] == a


async def test_add_and_get_effects(graph):
    """A->B edge means get_effects(A) == [B]."""
    a, b = EventId("a"), EventId("b")
    await graph.add_edge(a, b)

    effects = await graph.get_effects(a)
    assert len(effects) == 1
    assert effects[0] == b


async def test_chain_backward_linear(graph):
    """Linear chain A->B->C->D: get_chain(D, backward) returns [C, B, A]."""
    a, b, c, d = EventId("a"), EventId("b"), EventId("c"), EventId("d")
    await graph.add_edge(a, b)
    await graph.add_edge(b, c)
    await graph.add_edge(c, d)

    chain = await graph.get_chain(d, "backward")
    chain_ids = [str(eid) for eid in chain]
    assert "c" in chain_ids
    assert "b" in chain_ids
    assert "a" in chain_ids
    assert len(chain) == 3


async def test_chain_forward(graph):
    """Linear chain A->B->C: get_chain(A, forward) returns [B, C]."""
    a, b, c = EventId("a"), EventId("b"), EventId("c")
    await graph.add_edge(a, b)
    await graph.add_edge(b, c)

    chain = await graph.get_chain(a, "forward")
    chain_ids = [str(eid) for eid in chain]
    assert "b" in chain_ids
    assert "c" in chain_ids
    assert len(chain) == 2


async def test_chain_branching(graph):
    """Branching: A->C, B->C means get_chain(C, backward) contains both A and B."""
    a, b, c = EventId("a"), EventId("b"), EventId("c")
    await graph.add_edge(a, c)
    await graph.add_edge(b, c)

    chain = await graph.get_chain(c, "backward")
    chain_ids = set(str(eid) for eid in chain)
    assert "a" in chain_ids
    assert "b" in chain_ids


async def test_chain_max_depth(graph):
    """Chain of 10 nodes, max_depth=3 returns only 3 ancestors."""
    nodes = [EventId(f"n{i}") for i in range(10)]
    for i in range(9):
        await graph.add_edge(nodes[i], nodes[i + 1])

    chain = await graph.get_chain(nodes[9], "backward", max_depth=3)
    assert len(chain) <= 3


async def test_get_roots(graph):
    """A->B->C->D: get_roots(D) == [A] (the only node with no parents)."""
    a, b, c, d = EventId("a"), EventId("b"), EventId("c"), EventId("d")
    await graph.add_edge(a, b)
    await graph.add_edge(b, c)
    await graph.add_edge(c, d)

    roots = await graph.get_roots(d)
    root_ids = [str(r) for r in roots]
    assert "a" in root_ids
    assert len(roots) == 1


async def test_duplicate_edge_idempotent(graph):
    """Adding the same edge twice results in only one entry."""
    a, b = EventId("a"), EventId("b")
    await graph.add_edge(a, b)
    await graph.add_edge(a, b)

    causes = await graph.get_causes(b)
    assert len(causes) == 1


async def test_unknown_event_empty(graph):
    """get_causes and get_effects on unknown event return empty lists."""
    causes = await graph.get_causes(EventId("unknown"))
    effects = await graph.get_effects(EventId("unknown"))
    assert causes == []
    assert effects == []


async def test_diamond_pattern(graph):
    """Diamond: A->C, A->D, B->C, B->D, C->E, D->E.

    get_chain(E, backward) should find all ancestors: A, B, C, D.
    """
    a, b, c, d, e = (EventId(x) for x in "abcde")
    await graph.add_edge(a, c)
    await graph.add_edge(a, d)
    await graph.add_edge(b, c)
    await graph.add_edge(b, d)
    await graph.add_edge(c, e)
    await graph.add_edge(d, e)

    chain = await graph.get_chain(e, "backward")
    chain_ids = set(str(eid) for eid in chain)
    assert chain_ids == {"a", "b", "c", "d"}
