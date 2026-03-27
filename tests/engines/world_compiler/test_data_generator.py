"""Tests for WorldDataGenerator — D4b entity generation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from terrarium.core.errors import CompilerError
from terrarium.engines.world_compiler.data_generator import WorldDataGenerator
from terrarium.engines.world_compiler.generation_context import WorldGenerationContext
from terrarium.engines.world_compiler.plan import ServiceResolution, WorldPlan
from terrarium.kernel.surface import ServiceSurface
from terrarium.llm.types import LLMResponse
from terrarium.reality.dimensions import WorldConditions

# ── Helpers ──────────────────────────────────────────────────────


def _make_plan(
    entity_schemas: dict | None = None,
    state_machines: dict | None = None,
    actor_specs: list | None = None,
) -> WorldPlan:
    surface = ServiceSurface(
        service_name="email",
        category="communication",
        source="tier1_pack",
        fidelity_tier=1,
        entity_schemas=entity_schemas
        or {
            "email": {
                "fields": {
                    "id": "string",
                    "subject": "string",
                    "status": "string",
                }
            }
        },
        state_machines=state_machines or {},
    )
    return WorldPlan(
        name="Test",
        description="test world",
        seed=42,
        services={
            "gmail": ServiceResolution(
                service_name="gmail",
                spec_reference="verified/gmail",
                surface=surface,
                resolution_source="tier1_pack",
            )
        },
        actor_specs=actor_specs
        or [{"role": "agent", "type": "external", "count": 1}],
        conditions=WorldConditions(),
        reality_prompt_context={},
    )


# ── No LLM raises CompilerError ─────────────────────────────────


class TestNoLLMRaises:
    """Without LLM, generator raises CompilerError."""

    @pytest.mark.asyncio
    async def test_generate_raises_without_llm(self) -> None:
        gen = WorldDataGenerator(llm_router=None, seed=42)
        plan = _make_plan()
        ctx = WorldGenerationContext(plan)
        with pytest.raises(CompilerError, match="LLM router required"):
            await gen.generate(plan, ctx)


# ── LLM generation ──────────────────────────────────────────────


class TestGenerateWithLLM:
    """With LLM, generator uses PromptTemplate."""

    @pytest.mark.asyncio
    async def test_llm_generation_returns_entities(self) -> None:
        router = AsyncMock()
        canned = [{"id": "email_001", "subject": "Hello", "status": "unread"}]
        router.route = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(canned),
                provider="mock",
                model="mock",
                latency_ms=0,
            )
        )
        gen = WorldDataGenerator(llm_router=router, seed=42)
        plan = _make_plan()
        ctx = WorldGenerationContext(plan)
        entities = await gen.generate(plan, ctx)
        assert len(entities["email"]) == 1
        assert entities["email"][0]["id"] == "email_001"

    @pytest.mark.asyncio
    async def test_llm_dict_response_with_entity_key(self) -> None:
        """LLM returns {entity_type: [...]} format."""
        router = AsyncMock()
        canned = {"email": [{"id": "e1", "subject": "A", "status": "unread"}]}
        router.route = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(canned),
                provider="mock",
                model="mock",
                latency_ms=0,
            )
        )
        gen = WorldDataGenerator(llm_router=router, seed=42)
        plan = _make_plan()
        ctx = WorldGenerationContext(plan)
        entities = await gen.generate(plan, ctx)
        assert len(entities["email"]) == 1


# ── Count determination ──────────────────────────────────────────


class TestDetermineCount:
    """Entity count comes from actor specs when role matches."""

    def test_count_from_actor_spec(self) -> None:
        gen = WorldDataGenerator(seed=42)
        plan = _make_plan(
            actor_specs=[{"role": "email", "type": "external", "count": 25}]
        )
        assert gen._determine_count("email", plan) == 25

    def test_default_count_10(self) -> None:
        gen = WorldDataGenerator(seed=42)
        plan = _make_plan(
            actor_specs=[{"role": "unrelated", "type": "external", "count": 5}]
        )
        assert gen._determine_count("email", plan) == 10


# ── Section specs and response parsing ───────────────────────────


class TestSectionSpecs:
    """Generation specs are deterministic per entity type."""

    def test_iter_generation_specs(self) -> None:
        gen = WorldDataGenerator(seed=42)
        plan = _make_plan(
            actor_specs=[{"role": "email", "type": "external", "count": 25}]
        )
        specs = gen.iter_generation_specs(plan)
        assert len(specs) == 1
        assert specs[0].entity_type == "email"
        assert specs[0].count == 25


class TestParseGeneratedEntities:
    """Payload normalization supports all expected response shapes."""

    def test_parse_list_payload(self) -> None:
        gen = WorldDataGenerator(seed=42)
        result = gen.parse_generated_entities("email", [{"id": "e1"}], 2)
        assert result == [{"id": "e1"}]

    def test_parse_dict_payload_by_entity_type(self) -> None:
        gen = WorldDataGenerator(seed=42)
        result = gen.parse_generated_entities(
            "email",
            {"email": [{"id": "e1"}, {"id": "e2"}]},
            1,
        )
        assert result == [{"id": "e1"}]
