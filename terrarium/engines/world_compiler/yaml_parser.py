"""YAML parser for world definition + compiler settings files.

Handles both YAML file paths and pre-loaded dicts (from NL parser).
Integrates with D1 ConditionExpander for reality section processing.
"""
from __future__ import annotations
import copy
import logging
from pathlib import Path
from typing import Any

import yaml

from terrarium.core.errors import YAMLParseError
from terrarium.engines.world_compiler.plan import WorldPlan
from terrarium.reality.expander import ConditionExpander

logger = logging.getLogger(__name__)


class YAMLParser:
    """Parses world definition + compiler settings YAML → WorldPlan components."""

    def __init__(self, condition_expander: ConditionExpander | None = None) -> None:
        self._expander = condition_expander or ConditionExpander()

    async def parse(
        self,
        world_def_path: str | Path,
        compiler_settings_path: str | Path | None = None,
    ) -> tuple[WorldPlan, dict[str, Any]]:
        """Parse YAML files → (partial WorldPlan, service_specs).

        Returns:
            WorldPlan with empty services (caller resolves them)
            + dict mapping service_name → spec_reference string
        """
        world_def = self._load_yaml(world_def_path)
        compiler_settings = self._load_yaml(compiler_settings_path) if compiler_settings_path else {}
        return await self.parse_from_dicts(world_def, compiler_settings)

    async def parse_from_dicts(
        self,
        world_def: dict[str, Any],
        compiler_settings: dict[str, Any] | None = None,
    ) -> tuple[WorldPlan, dict[str, Any]]:
        """Parse dicts → (partial WorldPlan, service_specs)."""
        compiler_settings = compiler_settings or {}
        world = world_def.get("world", world_def)
        compiler = compiler_settings.get("compiler", compiler_settings)

        # Extract sections
        service_specs = self._extract_service_specs(world.get("services", {}))
        actor_specs = self._extract_actor_specs(world.get("actors", []))
        policies = world.get("policies", [])
        seeds = world.get("seeds", [])
        mission = world.get("mission", "")

        # Process reality via D1 ConditionExpander
        conditions, reality_ctx = self._extract_reality(compiler)

        # Compiler metadata
        meta = self._extract_compiler_metadata(compiler)

        plan = WorldPlan(
            name=world.get("name", "Unnamed World"),
            description=world.get("description", ""),
            seed=meta.get("seed", 42),
            behavior=meta.get("behavior", "dynamic"),
            fidelity=meta.get("fidelity", "auto"),
            mode=meta.get("mode", "governed"),
            services={},  # Empty — caller fills via CompilerServiceResolver
            actor_specs=actor_specs,
            conditions=conditions,
            reality_prompt_context=reality_ctx,
            policies=policies,
            seeds=seeds,
            mission=mission,
            animator_settings=compiler.get("animator", {}),
            source="yaml",
        )
        return plan, service_specs

    def _load_yaml(self, path: str | Path) -> dict[str, Any]:
        """Load a YAML file. Raises YAMLParseError on failure."""
        path = Path(path)
        try:
            with path.open("r") as f:
                data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            raise YAMLParseError(f"YAML file not found: {path}")
        except yaml.YAMLError as exc:
            raise YAMLParseError(f"Invalid YAML in {path}: {exc}")

    def _extract_service_specs(self, services: dict) -> dict[str, Any]:
        """Extract service_name → spec_reference mapping.

        Handles all formats from the spec:
        - Simple: gmail: verified/gmail
        - Complex: web: {provider: verified/browser, sites: [...]}
        - Bare: stripe (no prefix)
        """
        specs: dict[str, Any] = {}
        if isinstance(services, dict):
            for name, value in services.items():
                specs[name] = value  # str or dict
        return specs

    def _extract_actor_specs(self, actors: list) -> list[dict[str, Any]]:
        """Extract actor specs, preserving ALL YAML fields."""
        return [copy.deepcopy(a) for a in actors] if actors else []

    def _extract_reality(self, compiler: dict) -> tuple[Any, dict]:
        """Extract reality section → (WorldConditions, prompt_context)."""
        reality = compiler.get("reality", {})
        preset = reality.get("preset", "messy")

        # Warn about unknown reality keys
        known_dims = {"preset", "information", "reliability", "friction", "complexity", "boundaries"}
        unknown = set(reality.keys()) - known_dims
        if unknown:
            logger.warning("Unknown reality keys (ignored): %s", unknown)

        # Build overrides from non-preset fields
        overrides: dict[str, Any] = {}
        for dim_name in ("information", "reliability", "friction", "complexity", "boundaries"):
            if dim_name in reality:
                overrides[dim_name] = reality[dim_name]

        # Expand via D1
        conditions = self._expander.expand(preset, overrides if overrides else None)
        prompt_ctx = self._expander.build_prompt_context(conditions)

        return conditions, prompt_ctx

    def _extract_compiler_metadata(self, compiler: dict) -> dict[str, Any]:
        """Extract seed, behavior, fidelity, mode."""
        return {
            "seed": compiler.get("seed", 42),
            "behavior": compiler.get("behavior", "dynamic"),
            "fidelity": compiler.get("fidelity", "auto"),
            "mode": compiler.get("mode", "governed"),
        }
