"""Tests for CompilerSeedProcessor — D4b seed expansion and application."""

from __future__ import annotations

import json

import pytest

from unittest.mock import AsyncMock

from terrarium.core.errors import CompilerError
from terrarium.engines.world_compiler.generation_context import WorldGenerationContext
from terrarium.engines.world_compiler.plan import WorldPlan
from terrarium.engines.world_compiler.seed_processor import CompilerSeedProcessor
from terrarium.llm.types import LLMResponse


# ── Helpers ──────────────────────────────────────────────────────


def _make_entities() -> dict:
    return {
        "email": [
            {"id": "email_001", "subject": "Hello", "status": "unread"},
            {"id": "email_002", "subject": "Urgent", "status": "unread"},
        ],
        "customer": [
            {"id": "cust_001", "name": "Alice"},
        ],
    }


def _make_plan() -> WorldPlan:
    return WorldPlan(name="Test", description="test world", seed=42)


def _make_ctx() -> WorldGenerationContext:
    return WorldGenerationContext(_make_plan())


# ── No LLM raises CompilerError ─────────────────────────────────


class TestNoLLMRaises:
    """Without LLM, seed processor raises CompilerError."""

    @pytest.mark.asyncio
    async def test_process_all_raises_without_llm(self) -> None:
        proc = CompilerSeedProcessor(llm_router=None)
        ctx = _make_ctx()
        with pytest.raises(CompilerError, match="LLM router required"):
            await proc.process_all(["seed"], _make_entities(), ctx)

    @pytest.mark.asyncio
    async def test_expand_raises_without_llm(self) -> None:
        proc = CompilerSeedProcessor(llm_router=None)
        base_vars = _make_ctx().for_seed_expansion()
        with pytest.raises(CompilerError, match="LLM router required"):
            await proc.expand_seed("seed", _make_entities(), base_vars)


# ── Apply modifications ──────────────────────────────────────────


class TestApplyModifications:
    """apply_modifications creates and modifies entities."""

    def test_create_new_entity(self) -> None:
        proc = CompilerSeedProcessor()
        entities = _make_entities()
        mods = {
            "entities_to_create": [
                {
                    "entity_type": "email",
                    "fields": {"id": "email_vip", "subject": "VIP Issue"},
                },
            ],
            "entities_to_modify": [],
        }
        result = proc.apply_modifications(mods, entities)
        assert len(result["email"]) == 3
        assert any(e["id"] == "email_vip" for e in result["email"])

    def test_modify_existing_entity(self) -> None:
        proc = CompilerSeedProcessor()
        entities = _make_entities()
        mods = {
            "entities_to_create": [],
            "entities_to_modify": [
                {
                    "entity_type": "email",
                    "entity_id": "email_001",
                    "field_updates": {"status": "flagged"},
                },
            ],
        }
        result = proc.apply_modifications(mods, entities)
        e1 = next(e for e in result["email"] if e["id"] == "email_001")
        assert e1["status"] == "flagged"

    def test_create_new_entity_type(self) -> None:
        proc = CompilerSeedProcessor()
        entities = _make_entities()
        mods = {
            "entities_to_create": [
                {
                    "entity_type": "ticket",
                    "fields": {"id": "ticket_001", "priority": "high"},
                },
            ],
            "entities_to_modify": [],
        }
        result = proc.apply_modifications(mods, entities)
        assert "ticket" in result
        assert len(result["ticket"]) == 1

    def test_modify_nonexistent_entity_noop(self) -> None:
        proc = CompilerSeedProcessor()
        entities = _make_entities()
        mods = {
            "entities_to_create": [],
            "entities_to_modify": [
                {
                    "entity_type": "email",
                    "entity_id": "nonexistent",
                    "field_updates": {"status": "flagged"},
                },
            ],
        }
        result = proc.apply_modifications(mods, entities)
        # No modification applied, entities unchanged
        assert len(result["email"]) == 2


# ── LLM expansion ───────────────────────────────────────────────


class TestExpandNlSeeds:
    """expand_nl_seeds converts descriptions to Seed models."""

    @pytest.mark.asyncio
    async def test_expand_nl_seeds_returns_seeds(self) -> None:
        from terrarium.reality.seeds import Seed

        proc = CompilerSeedProcessor(llm_router=None)
        seeds = await proc.expand_nl_seeds(["VIP scenario", "Angry customer"])
        assert len(seeds) == 2
        assert all(isinstance(s, Seed) for s in seeds)
        assert seeds[0].description == "VIP scenario"
        assert seeds[1].description == "Angry customer"


class TestExpandWithLLM:
    """With LLM, seeds are expanded to structured modifications."""

    @pytest.mark.asyncio
    async def test_llm_expand_returns_mods(self) -> None:
        router = AsyncMock()
        router.route = AsyncMock(
            return_value=LLMResponse(
                content=json.dumps(
                    {
                        "entities_to_create": [
                            {
                                "entity_type": "email",
                                "fields": {"id": "email_vip", "subject": "VIP"},
                            },
                        ],
                        "entities_to_modify": [],
                    }
                ),
                provider="mock",
                model="mock",
                latency_ms=0,
            )
        )
        proc = CompilerSeedProcessor(llm_router=router)
        base_vars = _make_ctx().for_seed_expansion()
        mods = await proc.expand_seed(
            "Add VIP email", _make_entities(), base_vars
        )
        assert len(mods["entities_to_create"]) == 1

