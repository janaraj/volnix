"""Tests for ``WorldPlan.lightweight=True`` short-circuit
(``tnl/world-plan-lightweight-mode.tnl``).

Locks: the field default, the no-LLM path, the result-dict shape,
the zero-LLM-call invariant, the actor pass-through behavior, and
the state-engine + actor-registry side effects.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from volnix.actors.registry import ActorRegistry
from volnix.engines.world_compiler.engine import WorldCompilerEngine
from volnix.engines.world_compiler.plan import WorldPlan
from volnix.kernel.registry import SemanticRegistry
from volnix.packs.registry import PackRegistry
from volnix.reality.presets import load_preset


async def _make_engine(*, llm_router=None, state_engine=None, actor_registry=None):
    """Construct a WorldCompilerEngine with optional dependencies.

    Mirrors the pattern used by ``test_engine_generate.py`` but lets
    ``llm_router=None`` flow through unchanged so we can verify the
    lightweight branch works without an LLM.
    """
    kernel = SemanticRegistry()
    await kernel.initialize()
    pack_reg = PackRegistry()

    engine = WorldCompilerEngine()
    config = {
        "default_seed": 42,
        "max_entities_per_type": 100,
        "_kernel": kernel,
        "_pack_registry": pack_reg,
        "_llm_router": llm_router,
        "_state_engine": state_engine,
        "_actor_registry": actor_registry,
    }
    bus = AsyncMock()
    await engine.initialize(config, bus)
    return engine


def _lightweight_plan(actor_count: int = 1) -> WorldPlan:
    """Build a minimal lightweight WorldPlan."""
    return WorldPlan(
        name="rehearsal-test",
        description="single-character chat",
        seed=42,
        behavior="reactive",
        fidelity="strict",
        mode="ungoverned",
        lightweight=True,
        actor_specs=[
            {"role": f"character-{i}", "type": "internal", "count": 1} for i in range(actor_count)
        ],
        conditions=load_preset("messy"),
    )


# ─── Plan field default ────────────────────────────────────────────


class TestLightweightFieldDefault:
    """``WorldPlan.lightweight`` defaults to ``False`` so existing
    callers stay byte-identical (Phase 0 oracle clause)."""

    def test_positive_default_false(self) -> None:
        plan = WorldPlan(name="x")
        assert plan.lightweight is False

    def test_positive_explicit_true_accepted(self) -> None:
        plan = WorldPlan(name="x", lightweight=True)
        assert plan.lightweight is True


# ─── No-LLM path ───────────────────────────────────────────────────


class TestLightweightWithoutLLM:
    """Lightweight compilation MUST work without an LLM router
    (TNL: the heavy-path's ``if not self._llm_router: raise`` is
    moved INSIDE the heavy branch so lightweight bypasses it)."""

    @pytest.mark.asyncio
    async def test_positive_no_router_succeeds(self) -> None:
        engine = await _make_engine(llm_router=None)
        plan = _lightweight_plan()
        # Must NOT raise CompilerError despite no LLM router.
        result = await engine.generate_world(plan)
        assert isinstance(result, dict)


# ─── Zero-LLM-call invariant ───────────────────────────────────────


class TestLightweightMakesNoLLMCalls:
    """Lightweight compilation MUST NOT call any LLM, even when an
    LLM router is wired (the consumer passed one but we shouldn't
    burn budget)."""

    @pytest.mark.asyncio
    async def test_positive_router_is_never_called(self) -> None:
        # Wire a mock router; assert .route() is never invoked.
        router = AsyncMock()
        router.route = AsyncMock()
        engine = await _make_engine(llm_router=router)
        plan = _lightweight_plan()
        await engine.generate_world(plan)
        assert router.route.await_count == 0, (
            f"lightweight path called LLM router .route() "
            f"{router.route.await_count} times — must be 0"
        )


# ─── Result dict shape ─────────────────────────────────────────────


class TestLightweightResultShape:
    """The result dict MUST have the same key surface as the heavy
    path so downstream callers (``app.create_world``,
    ``WorldManager.mark_generated``, ``generation.json`` writer)
    work unchanged."""

    @pytest.mark.asyncio
    async def test_positive_required_keys_present(self) -> None:
        engine = await _make_engine(llm_router=None)
        plan = _lightweight_plan()
        result = await engine.generate_world(plan)

        # Every key downstream callers look up:
        for key in (
            "entities",
            "actors",
            "subscriptions",
            "warnings",
            "seeds_processed",
            "snapshot_id",
            "validation_report",
            "retry_counts",
            "compiled_policies",
            "applied_seed_invariants",
        ):
            assert key in result, f"missing key {key!r} in lightweight result"

    @pytest.mark.asyncio
    async def test_positive_entities_is_empty_dict(self) -> None:
        engine = await _make_engine(llm_router=None)
        plan = _lightweight_plan()
        result = await engine.generate_world(plan)
        assert result["entities"] == {}, "lightweight worlds have no generated entities"

    @pytest.mark.asyncio
    async def test_positive_seeds_processed_is_zero(self) -> None:
        engine = await _make_engine(llm_router=None)
        plan = _lightweight_plan()
        result = await engine.generate_world(plan)
        assert result["seeds_processed"] == 0
        assert result["retry_counts"] == {}
        assert result["applied_seed_invariants"] == {}

    @pytest.mark.asyncio
    async def test_positive_validation_report_is_empty(self) -> None:
        engine = await _make_engine(llm_router=None)
        plan = _lightweight_plan()
        result = await engine.generate_world(plan)
        assert result["validation_report"] == {"sections": {}, "final_world": {}}


# ─── Actor pass-through ────────────────────────────────────────────


class TestLightweightActorPassThrough:
    """``actor_specs`` MUST be expanded via the existing non-LLM
    ``CompilerPersonalityGenerator.expand_actor_structure`` path
    (which calls ``SimpleActorGenerator.generate_batch`` — verified
    LLM-free at personality_generator.py:48)."""

    @pytest.mark.asyncio
    async def test_positive_one_actor_per_spec(self) -> None:
        engine = await _make_engine(llm_router=None)
        plan = _lightweight_plan(actor_count=3)
        result = await engine.generate_world(plan)
        assert len(result["actors"]) == 3

    @pytest.mark.asyncio
    async def test_positive_zero_actors_succeeds(self) -> None:
        # Empty actor_specs is a valid lightweight world (e.g., a
        # placeholder world that gets actors pinned later).
        engine = await _make_engine(llm_router=None)
        plan = WorldPlan(name="empty", lightweight=True)
        result = await engine.generate_world(plan)
        assert result["actors"] == []


# ─── Actor registry side effect ────────────────────────────────────


class TestLightweightActorRegistry:
    """When an actor_registry is wired, lightweight MUST register
    actors (matching the heavy path's behavior at line 472)."""

    @pytest.mark.asyncio
    async def test_positive_actors_registered_when_registry_wired(self) -> None:
        registry = ActorRegistry()
        engine = await _make_engine(llm_router=None, actor_registry=registry)
        plan = _lightweight_plan(actor_count=2)
        await engine.generate_world(plan)
        # ActorRegistry exposes actor_count or similar — use the
        # public API to verify
        assert len(registry.list_actors()) == 2


# ─── Heavy path still requires LLM (regression guard) ──────────────


class TestHeavyPathStillRequiresLLM:
    """The TNL moves the ``if not self._llm_router`` guard INSIDE the
    heavy branch. Verify the heavy path still raises when no router
    is wired — protects against accidentally bypassing the guard
    for the wrong plans."""

    @pytest.mark.asyncio
    async def test_negative_heavyweight_no_router_still_raises(self) -> None:
        from volnix.core.errors import CompilerError

        engine = await _make_engine(llm_router=None)
        # lightweight=False (default) — still requires LLM
        plan = WorldPlan(name="heavy", lightweight=False)
        with pytest.raises(CompilerError, match="Cannot generate world"):
            await engine.generate_world(plan)
