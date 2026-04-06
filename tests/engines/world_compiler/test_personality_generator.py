"""Tests for CompilerPersonalityGenerator — D4b actor personality generation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from volnix.core.errors import CompilerError
from volnix.engines.world_compiler.generation_context import WorldGenerationContext
from volnix.engines.world_compiler.personality_generator import (
    CompilerPersonalityGenerator,
)
from volnix.engines.world_compiler.plan import WorldPlan
from volnix.llm.types import LLMResponse
from volnix.reality.presets import load_preset


def _make_ctx(conditions=None, description="test world") -> WorldGenerationContext:
    """Build a WorldGenerationContext for tests."""
    return WorldGenerationContext(
        WorldPlan(
            name="Test",
            description=description,
            seed=42,
            conditions=conditions or load_preset("messy"),
            reality_prompt_context={},
        )
    )


# ── Protocol compliance ──────────────────────────────────────────


class TestProtocolCompliance:
    """CompilerPersonalityGenerator has required methods."""

    def test_has_required_methods(self) -> None:
        gen = CompilerPersonalityGenerator()
        assert hasattr(gen, "generate_personality")
        assert hasattr(gen, "generate_friction_profile")
        assert hasattr(gen, "generate_batch")


# ── No LLM raises CompilerError ─────────────────────────────────


class TestNoLLMRaises:
    """Without LLM, generator raises CompilerError."""

    @pytest.mark.asyncio
    async def test_personality_raises_without_llm(self) -> None:
        gen = CompilerPersonalityGenerator(llm_router=None)
        ctx = _make_ctx()
        with pytest.raises(CompilerError, match="LLM router required"):
            await gen.generate_personality("agent", "hint", ctx)

    @pytest.mark.asyncio
    async def test_batch_raises_without_llm(self) -> None:
        gen = CompilerPersonalityGenerator(llm_router=None)
        conditions = load_preset("messy")
        ctx = _make_ctx(conditions=conditions)
        specs = [{"role": "agent", "type": "external", "count": 1}]
        with pytest.raises(CompilerError, match="LLM router required"):
            await gen.generate_batch(specs, conditions, ctx)


# ── LLM generation ──────────────────────────────────────────────


class TestLLMGeneration:
    """With LLM, enriches personalities."""

    @pytest.mark.asyncio
    async def test_llm_personality(self) -> None:
        router = AsyncMock()
        router.route = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "style": "creative",
                        "response_time": "2m",
                        "strengths": ["empathetic"],
                        "weaknesses": ["slow"],
                        "description": "A creative agent",
                        "traits": {"patience": "high"},
                    }
                ),
                provider="mock",
                model="mock",
                latency_ms=0,
            )
        )
        gen = CompilerPersonalityGenerator(llm_router=router, seed=42)
        ctx = _make_ctx()
        p = await gen.generate_personality("agent", "creative type", ctx)
        assert p.style == "creative"
        assert "empathetic" in p.strengths

    @pytest.mark.asyncio
    async def test_hostile_world_friction_distribution(self) -> None:
        """Hostile preset produces some actors with friction profiles."""
        router = AsyncMock()
        router.route = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    [
                        {
                            "style": "aggressive",
                            "response_time": "1m",
                            "strengths": ["direct"],
                            "weaknesses": ["impatient"],
                            "description": "An aggressive customer",
                            "traits": {},
                        }
                    ]
                    * 20
                ),
                provider="mock",
                model="mock",
                latency_ms=0,
            )
        )
        gen = CompilerPersonalityGenerator(llm_router=router, seed=42)
        conditions = load_preset("hostile")
        ctx = _make_ctx(conditions=conditions, description="hostile world")
        specs = [{"role": "customer", "type": "internal", "count": 20}]
        actors = await gen.generate_batch(specs, conditions, ctx)
        friction_actors = [a for a in actors if a.friction_profile is not None]
        assert len(friction_actors) > 0
