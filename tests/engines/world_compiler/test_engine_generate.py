"""Tests for WorldCompilerEngine.generate_world() — D4b orchestration."""

from __future__ import annotations

import json

import pytest

from unittest.mock import AsyncMock

from terrarium.actors.registry import ActorRegistry
from terrarium.core.errors import CompilerError
from terrarium.engines.world_compiler.engine import WorldCompilerEngine
from terrarium.engines.world_compiler.plan import WorldPlan, ServiceResolution
from terrarium.kernel.registry import SemanticRegistry
from terrarium.kernel.surface import ServiceSurface
from terrarium.llm.types import LLMResponse
from terrarium.packs.registry import PackRegistry
from terrarium.packs.verified.email.pack import EmailPack
from terrarium.reality.presets import load_preset


# ── Helpers ──────────────────────────────────────────────────────


def _make_mock_llm_router():
    """Mock LLM router that returns valid JSON for all compiler sub-components.

    Returns a dict that works for entity generation (falls through to [parsed]),
    seed expansion (has entities_to_create/modify keys), and personality
    generation (has style/strengths/weaknesses keys).
    """
    def _route_side_effect(*args, **kwargs):
        # Inspect the LLMRequest to determine which template is calling
        request = args[0] if args else kwargs.get("request")
        system = getattr(request, "system_prompt", "") or ""
        user = getattr(request, "user_content", "") or ""
        combined = (system + user).lower()

        if "personality profiles for actors" in combined or "distinct personalities for" in combined:
            payload = [
                {
                    "style": "balanced",
                    "response_time": "5m",
                    "strengths": ["adaptable"],
                    "weaknesses": ["generic"],
                    "description": "A balanced actor",
                    "traits": {},
                },
            ]
        elif "seed" in combined or "scenario" in combined:
            payload = {
                "entities_to_create": [],
                "entities_to_modify": [],
            }
        else:
            # Entity generation — return list format
            payload = [
                {"id": "email_001", "email_id": "email_001", "from_addr": "a@b.com",
                 "to_addr": "c@d.com", "subject": "Test", "body": "Hello", "status": "sent"},
            ]

        return LLMResponse(
            content=json.dumps(payload),
            provider="mock", model="gemini-3-flash-preview", latency_ms=0,
        )

    router = AsyncMock()
    router.route = AsyncMock(side_effect=_route_side_effect)
    return router


async def _make_engine(
    llm_router=None, state_engine=None, actor_registry=None
):
    """Build a WorldCompilerEngine with injected dependencies."""
    if llm_router is None:
        llm_router = _make_mock_llm_router()

    kernel = SemanticRegistry()
    await kernel.initialize()
    pack_reg = PackRegistry()
    pack_reg.register(EmailPack())

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


def _make_plan_with_email() -> WorldPlan:
    surface = ServiceSurface.from_pack(EmailPack())
    return WorldPlan(
        name="Test World",
        description="Test",
        seed=42,
        services={
            "email": ServiceResolution(
                service_name="email",
                spec_reference="verified/email",
                surface=surface,
                resolution_source="tier1_pack",
            )
        },
        actor_specs=[
            {"role": "support-agent", "type": "external", "count": 2}
        ],
        conditions=load_preset("messy"),
        reality_prompt_context={},
    )


# ── generate_world requires LLM ─────────────────────────────────


class TestGenerateWorldRequiresLLM:
    """generate_world() raises CompilerError without LLM."""

    @pytest.mark.asyncio
    async def test_no_llm_raises(self) -> None:
        engine = await _make_engine()
        # Remove the LLM router to simulate no LLM
        engine._llm_router = None
        plan = _make_plan_with_email()
        with pytest.raises(CompilerError, match="Cannot generate world"):
            await engine.generate_world(plan)


# ── generate_world with mock LLM ────────────────────────────────


class TestGenerateWorldWithMockLLM:
    """generate_world() works with mock LLM router."""

    @pytest.mark.asyncio
    async def test_returns_entities(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        assert "entities" in result
        assert isinstance(result["entities"], dict)

    @pytest.mark.asyncio
    async def test_returns_actors(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        assert "actors" in result
        assert len(result["actors"]) == 2  # count=2 from spec

    @pytest.mark.asyncio
    async def test_returns_report(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        assert "report" in result
        assert "TERRARIUM WORLD GENERATION REPORT" in result["report"]

    @pytest.mark.asyncio
    async def test_returns_warnings(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        assert "warnings" in result
        assert isinstance(result["warnings"], list)


# ── generate_world with StateEngine ──────────────────────────────


class TestGenerateWorldWithState:
    """generate_world() populates StateEngine when available."""

    @pytest.mark.asyncio
    async def test_populates_state(self) -> None:
        state = AsyncMock()
        state.populate_entities = AsyncMock(return_value=10)
        state.snapshot = AsyncMock(return_value="snap_001")
        engine = await _make_engine(state_engine=state)
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        state.populate_entities.assert_called_once()
        state.snapshot.assert_called_once_with("initial_world")
        assert result["snapshot_id"] == "snap_001"

    @pytest.mark.asyncio
    async def test_registers_actors(self) -> None:
        registry = ActorRegistry()
        engine = await _make_engine(actor_registry=registry)
        plan = _make_plan_with_email()
        await engine.generate_world(plan)
        assert registry.count() == 2


# ── generate_world with seeds ────────────────────────────────────


class TestGenerateWorldWithSeeds:
    """Seeds are processed during generation."""

    @pytest.mark.asyncio
    async def test_seeds_processed_count(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email().model_copy(
            update={
                "seeds": [
                    "VIP customer with urgent ticket",
                    "Overdue invoice",
                ],
            }
        )
        result = await engine.generate_world(plan)
        assert result["seeds_processed"] == 2

    @pytest.mark.asyncio
    async def test_no_seeds_zero_count(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        assert result["seeds_processed"] == 0


# ── resolve_service_schema ───────────────────────────────────────


class TestGenerateWorldEntityContent:
    """Verify generated entities have proper fields, not just counts."""

    @pytest.mark.asyncio
    async def test_entities_have_ids(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        for entity_type, entities in result["entities"].items():
            for entity in entities:
                assert "id" in entity, f"{entity_type} entity missing 'id'"
                assert entity["id"], f"{entity_type} entity has empty 'id'"

    @pytest.mark.asyncio
    async def test_actors_have_personalities(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        for actor in result["actors"]:
            assert actor.role, "Actor missing role"
            assert actor.personality is not None, "Actor missing personality"
            assert actor.personality.style in (
                "methodical", "creative", "aggressive", "cautious", "balanced"
            )

    @pytest.mark.asyncio
    async def test_report_has_entity_counts(self) -> None:
        engine = await _make_engine()
        plan = _make_plan_with_email()
        result = await engine.generate_world(plan)
        report = result["report"]
        assert "GENERATED ENTITIES:" in report
        assert "TOTAL:" in report
        assert "ACTORS:" in report
        assert "STATUS:" in report
        # Total should match actual entity count
        total = sum(len(v) for v in result["entities"].values())
        assert f"TOTAL: {total} entities" in report


class TestExpandReality:
    """expand_reality() delegates to ConditionExpander."""

    @pytest.mark.asyncio
    async def test_expand_reality_messy(self) -> None:
        engine = await _make_engine()
        conditions = await engine.expand_reality("messy")
        assert conditions.information.staleness == 30
        assert conditions.reliability.failures == 20

    @pytest.mark.asyncio
    async def test_expand_reality_with_overrides(self) -> None:
        engine = await _make_engine()
        conditions = await engine.expand_reality(
            "ideal", overrides={"friction": "actively_hostile"}
        )
        assert conditions.friction.uncooperative == 75
        # Other dimensions stay ideal
        assert conditions.information.staleness == 0


class TestResolveServiceSchema:
    @pytest.mark.asyncio
    async def test_resolve_unknown_service_raises(self) -> None:
        engine = await _make_engine()
        # Unknown service with no resolution available
        with pytest.raises(Exception):
            await engine.resolve_service_schema("nonexistent_service_xyz")
