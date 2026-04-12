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

from volnix.core.errors import YAMLParseError
from volnix.engines.world_compiler.plan import WorldPlan
from volnix.reality.expander import ConditionExpander

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
        compiler_settings = (
            self._load_yaml(compiler_settings_path) if compiler_settings_path else {}
        )
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
        deliverable_config = world.get("deliverable", {})
        collaboration_config = world.get("collaboration", {})

        # Process reality — read from world section, fall back to compiler
        conditions, reality_ctx = self._extract_reality(world, compiler)

        # World + compiler metadata
        meta = self._extract_compiler_metadata(world, compiler)

        # Extract optional game configuration
        game_config = self._extract_game_config(world_def)

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
            deliverable_config=deliverable_config,
            collaboration_config=collaboration_config,
            animator_settings=world.get("animator", {}) or compiler.get("animator", {}),
            game=game_config,
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

    def _extract_reality(self, world: dict, compiler: dict) -> tuple[Any, dict]:
        """Extract reality section → (WorldConditions, prompt_context)."""
        reality = world.get("reality", {}) or compiler.get("reality", {})
        preset = reality.get("preset", "messy")

        # Warn about unknown reality keys
        known_dims = {
            "preset",
            "information",
            "reliability",
            "friction",
            "complexity",
            "boundaries",
        }
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

    def _extract_compiler_metadata(self, world: dict, compiler: dict) -> dict[str, Any]:
        """Extract seed, behavior, fidelity, mode.

        Reads from world section first (where blueprints define them),
        falls back to compiler section for backward compatibility.
        Seed stays in compiler — it's a compilation parameter.
        """
        return {
            "seed": compiler.get("seed", 42),
            "behavior": world.get("behavior") or compiler.get("behavior", "dynamic"),
            "fidelity": world.get("fidelity") or compiler.get("fidelity", "auto"),
            "mode": world.get("mode") or compiler.get("mode", "governed"),
        }

    def _extract_game_config(self, raw: dict) -> Any:
        """Extract game configuration from blueprint YAML.

        Event-driven only: the Cycle B plan §3.3 specified that legacy
        round-based keys (``rounds`` / ``turn_protocol`` /
        ``between_rounds`` / ``resource_reset_per_round``) must be
        hard-rejected once migration is complete. B-cleanup.3 flipped
        the soft-warn path to the hard-reject path the plan originally
        mandated.

        Validation:

        - Legacy round-based keys raise ``YAMLParseError`` with a clear
          migration message pointing to the event-driven replacements.
        - Declared but empty ``entities.deals`` logs a warning (the
          compile still succeeds, but the game has nothing to score).
        - ``game.type_config.negotiation_fields`` (the pre-NF1 nested
          shape) is auto-migrated with a warning for out-of-tree
          blueprints — the in-tree blueprints were flattened in
          B-cleanup.1b.
        - :class:`pydantic.ValidationError` from bad field types
          (e.g. ``max_events: "none"``) is wrapped in
          :class:`YAMLParseError` with a blueprint-pointing message.
        """
        game_raw = raw.get("game") or raw.get("world", {}).get("game")
        if not game_raw or not game_raw.get("enabled", False):
            return None
        from pydantic import ValidationError

        from volnix.engines.game.definition import GameDefinition

        # NF8 (B-cleanup.3): hard-reject legacy round-based keys. The
        # Cycle B plan §3.3 mandated this; implementation soft-warned
        # by mistake. Now that migration is complete, reject loudly so
        # a stale blueprint fails the compile with a clear actionable
        # message rather than silently running with the round config
        # ignored.
        _LEGACY_ROUND_KEYS = (
            "rounds",
            "turn_protocol",
            "between_rounds",
            "resource_reset_per_round",
        )
        rejected = [k for k in _LEGACY_ROUND_KEYS if k in game_raw]
        if rejected:
            raise YAMLParseError(
                f"Blueprint ``game`` section uses legacy round-based keys: "
                f"{rejected}. These were removed in Cycle B. Migrate to "
                f"``flow.type: event_driven``, ``game.entities``, and "
                f"``game.negotiation_fields``. See ``docs/games.md`` or the "
                f"Cycle B cleanup plan for the migration guide."
            )

        entities_raw = game_raw.get("entities") or {}
        has_new_entities = bool(entities_raw.get("deals"))

        # NF1 migration: the nested ``game.type_config.negotiation_fields``
        # shape was flattened to top-level ``game.negotiation_fields`` in
        # B-cleanup.1b. ``GameDefinition.type_config`` no longer exists and
        # Pydantic's default ``extra="ignore"`` would silently drop the
        # nested key. Pop it here with a warning and auto-migrate the
        # contained negotiation_fields list so out-of-tree blueprints keep
        # working for one release before authors migrate.
        if "type_config" in game_raw:
            tc = game_raw.pop("type_config") or {}
            if (
                isinstance(tc, dict)
                and "negotiation_fields" in tc
                and "negotiation_fields" not in game_raw
            ):
                logger.warning(
                    "Blueprint uses legacy ``game.type_config.negotiation_fields``. "
                    "Migrate to flattened ``game.negotiation_fields``. "
                    "Auto-migrating for this run."
                )
                game_raw["negotiation_fields"] = tc["negotiation_fields"]
            else:
                logger.warning(
                    "Blueprint declares ``game.type_config`` but this field "
                    "was removed in NF1 (B-cleanup.1b). Ignoring."
                )

        # Warn if enabled but no deals declared — compile succeeds but
        # the orchestrator will have nothing to negotiate over.
        if not has_new_entities:
            logger.warning(
                "Blueprint sets ``game.enabled: true`` but declares no "
                "``game.entities.deals``. The GameOrchestrator will start "
                "with nothing to score."
            )

        # Warn if scoring_mode is behavioral but target_terms are declared —
        # those are competitive-mode-only and will be silently dropped.
        scoring_mode = str(game_raw.get("scoring_mode", "behavioral"))
        if scoring_mode == "behavioral" and entities_raw.get("target_terms"):
            logger.warning(
                "Blueprint declares ``game.entities.target_terms`` in "
                "behavioral scoring mode — these will be silently dropped "
                "at materialization (competitive mode only)."
            )

        try:
            return GameDefinition(**game_raw)
        except ValidationError as exc:
            # Surface a clear compiler-level error that points back to
            # the blueprint rather than leaking Pydantic's raw output.
            raise YAMLParseError(f"Invalid ``game`` section in blueprint: {exc}") from exc
