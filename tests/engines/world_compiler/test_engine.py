"""Tests for WorldCompilerEngine — E2E compilation (D4a)."""

import json
from unittest.mock import AsyncMock

import pytest
import yaml

from volnix.engines.world_compiler.engine import WorldCompilerEngine
from volnix.engines.world_compiler.plan import WorldPlan
from volnix.llm.types import LLMResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_engine(
    pack_registry=None,
    kernel=None,
    service_resolver=None,
    llm_router=None,
):
    """Instantiate and initialize a WorldCompilerEngine with injected deps."""
    engine = WorldCompilerEngine()
    config = {}
    if llm_router:
        config["_llm_router"] = llm_router
    if kernel:
        config["_kernel"] = kernel
    if pack_registry:
        config["_pack_registry"] = pack_registry
    if service_resolver:
        config["_service_resolver"] = service_resolver

    bus = AsyncMock()
    await engine.initialize(config, bus)
    return engine


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWorldCompilerEngine:
    """E2E engine tests for D4a compilation."""

    @pytest.mark.asyncio
    async def test_compile_from_yaml(self, tmp_path, pack_registry, kernel):
        """compile_from_yaml parses a YAML file and returns a WorldPlan."""
        world_file = tmp_path / "world.yaml"
        world_file.write_text(
            yaml.dump(
                {
                    "world": {
                        "name": "YAML E2E",
                        "description": "End-to-end test",
                        "services": {"gmail": "verified/gmail"},
                        "actors": [{"role": "agent", "type": "external", "count": 1}],
                        "mission": "test all paths",
                    }
                }
            )
        )

        engine = await _make_engine(pack_registry=pack_registry, kernel=kernel)
        plan = await engine.compile_from_yaml(str(world_file))

        assert isinstance(plan, WorldPlan)
        assert plan.name == "YAML E2E"
        assert plan.source == "yaml"
        assert plan.mission == "test all paths"
        # Email should be resolved via pack
        if "gmail" in plan.services:
            assert plan.services["gmail"].resolution_source == "tier1_pack"

    @pytest.mark.asyncio
    async def test_compile_from_nl(self, pack_registry, kernel):
        """compile_from_nl uses mock LLM to parse NL and returns WorldPlan."""
        world_json = json.dumps(
            {
                "world": {
                    "name": "NL World",
                    "description": "From natural language",
                    "services": {"gmail": "verified/gmail"},
                    "actors": [{"role": "agent", "type": "external", "count": 1}],
                    "policies": [],
                    "seeds": [],
                    "mission": "",
                }
            }
        )
        settings_json = json.dumps(
            {
                "compiler": {
                    "seed": 42,
                    "behavior": "dynamic",
                    "fidelity": "auto",
                    "mode": "governed",
                    "reality": {"preset": "messy"},
                }
            }
        )
        mock_router = AsyncMock()
        mock_router.route = AsyncMock(
            side_effect=[
                LLMResponse(content=world_json, provider="mock", model="mock", latency_ms=0),
                LLMResponse(content=settings_json, provider="mock", model="mock", latency_ms=0),
            ]
        )

        engine = await _make_engine(
            pack_registry=pack_registry,
            kernel=kernel,
            llm_router=mock_router,
        )
        plan = await engine.compile_from_nl("Support team with email")

        assert isinstance(plan, WorldPlan)
        assert plan.source == "nl"
        assert plan.name == "NL World"

    @pytest.mark.asyncio
    async def test_no_settings_defaults(self, tmp_path):
        """When no compiler settings file is given, defaults are used."""
        world_file = tmp_path / "world.yaml"
        world_file.write_text(
            yaml.dump(
                {
                    "world": {
                        "name": "Default Settings",
                        "services": {"gmail": "verified/gmail"},
                        "actors": [],
                    }
                }
            )
        )

        engine = await _make_engine()
        plan = await engine.compile_from_yaml(str(world_file))

        assert plan.seed == 42
        assert plan.behavior == "dynamic"
        assert plan.fidelity == "auto"
        assert plan.mode == "governed"

    @pytest.mark.asyncio
    async def test_preserves_reality(self, tmp_path, pack_registry, kernel):
        """Compiler settings reality preset flows into WorldPlan conditions."""
        world_file = tmp_path / "world.yaml"
        world_file.write_text(
            yaml.dump(
                {
                    "world": {
                        "name": "Reality Test",
                        "services": {},
                        "actors": [],
                    }
                }
            )
        )
        settings_file = tmp_path / "settings.yaml"
        settings_file.write_text(
            yaml.dump(
                {
                    "compiler": {
                        "reality": {"preset": "hostile"},
                    }
                }
            )
        )

        engine = await _make_engine(pack_registry=pack_registry, kernel=kernel)
        plan = await engine.compile_from_yaml(str(world_file), str(settings_file))

        # Hostile preset should produce non-zero friction
        assert plan.conditions.friction.hostile > 0
        assert "dimensions" in plan.reality_prompt_context

    @pytest.mark.asyncio
    async def test_preserves_actors(self, tmp_path):
        """Actor specs from YAML are preserved in WorldPlan."""
        world_file = tmp_path / "world.yaml"
        world_file.write_text(
            yaml.dump(
                {
                    "world": {
                        "name": "Actor Test",
                        "services": {},
                        "actors": [
                            {
                                "role": "agent",
                                "type": "external",
                                "count": 3,
                                "personality": "grumpy",
                            },
                            {"role": "customer", "type": "internal", "count": 100},
                        ],
                    }
                }
            )
        )

        engine = await _make_engine()
        plan = await engine.compile_from_yaml(str(world_file))

        assert len(plan.actor_specs) == 2
        assert plan.actor_specs[0]["role"] == "agent"
        assert plan.actor_specs[0]["personality"] == "grumpy"
        assert plan.actor_specs[1]["count"] == 100
