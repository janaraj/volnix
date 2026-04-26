"""WorldPlan — the contract between D4a (planning) and D4b (generation).

A WorldPlan is the COMPLETE plan for a world: resolved services,
reality conditions, actor specs, policies, seeds. It contains
everything D4b needs to generate entities and populate the StateEngine.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from volnix.engines.game.definition import GameDefinition
from volnix.kernel.surface import ServiceSurface
from volnix.reality.dimensions import WorldConditions


class ServiceResolution(BaseModel, frozen=True):
    """Resolution metadata for a single service."""

    service_name: str
    spec_reference: str  # "verified/gmail", "profiled/stripe", bare "stripe"
    surface: ServiceSurface
    resolution_source: (
        str  # "tier1_pack", "context_hub", "openapi", "llm_inference", "kernel_inference"
    )


class WorldPlan(BaseModel, frozen=True):
    """Complete world plan — output of D4a, input to D4b.

    Contains:
    - Resolved services (each has a ServiceSurface with operations + schemas)
    - Reality conditions (dimensions + LLM prompt context)
    - Actor specs (raw YAML, D4b expands with personalities)
    - Policies, seeds, mission (raw YAML, D4b processes)
    - Behavior + animator settings (for runtime, not compilation)
    """

    # ── Metadata ──
    name: str = ""
    description: str = ""
    seed: int = 42
    behavior: Literal["static", "reactive", "dynamic"] = "dynamic"
    fidelity: Literal["auto", "strict", "exploratory"] = "auto"
    mode: Literal["governed", "ungoverned"] = "governed"
    lightweight: bool = False
    """When True, ``WorldCompilerEngine.generate_world`` short-circuits
    to a pass-through path: validates ``actor_specs`` only, returns
    a result dict with empty entities + actors expanded from the
    consumer-supplied specs. No LLM calls, no entity generation, no
    seed processing. Default ``False`` preserves the existing
    heavyweight pipeline byte-identical.

    Use case: chat-only worlds where the consumer (typically a
    downstream library) has already supplied complete actor specs
    and there are no entities, services, or seeds to populate. A
    lightweight world compiles in <100ms and works without an LLM
    router configured. Surfaces
    ``tnl/world-plan-lightweight-mode.tnl``.
    """

    # ── Resolved services (D4a fills) ──
    services: dict[str, ServiceResolution] = Field(default_factory=dict)

    # ── Actor specs (raw, D4b expands) ──
    actor_specs: list[dict[str, Any]] = Field(default_factory=list)

    # ── Character catalog references (PMF Plan Phase 4C Step 11) ──
    # Optional list of ``CharacterDefinition.id`` values referring
    # to entries in a product-side catalog. Consumers that use a
    # ``CharacterLoader`` catalog populate this field instead of
    # inlining actor specs; the consumer dereferences at plan-build
    # time via ``CharacterDefinition.to_actor_spec()`` and appends
    # to ``actor_specs``. Compiler integration (auto-dereference)
    # is deferred to a later step; until then the field is a
    # structured marker.
    characters: list[str] = Field(default_factory=list)

    # ── Reality (D1) ──
    conditions: WorldConditions = Field(default_factory=WorldConditions)
    reality_prompt_context: dict[str, Any] = Field(default_factory=dict)

    # ── Raw YAML sections (D4b processes) ──
    policies: list[dict[str, Any]] = Field(default_factory=list)
    seeds: list[str] = Field(default_factory=list)
    mission: str = ""

    # ── Collaboration + deliverable ──
    deliverable_config: dict[str, Any] = Field(default_factory=dict)
    collaboration_config: dict[str, Any] = Field(default_factory=dict)

    # ── Runtime settings (carried to engines) ──
    animator_settings: dict[str, Any] = Field(default_factory=dict)

    # ── Game configuration (optional) ──
    game: GameDefinition | None = None

    # ── Blueprint (if detected) ──
    blueprint: str | None = None

    # ── Compilation metadata ──
    source: str = ""  # "yaml" or "nl"
    warnings: list[str] = Field(default_factory=list)

    def validate_plan(self) -> list[str]:
        """Validate plan completeness. Returns list of errors."""
        errors: list[str] = []
        if not self.name:
            errors.append("WorldPlan missing name")
        if not self.services:
            errors.append("WorldPlan has no resolved services")
        for svc_name, res in self.services.items():
            surface_errors = res.surface.validate_surface()
            for se in surface_errors:
                errors.append(f"Service '{svc_name}': {se}")
        if self.fidelity == "strict":
            for svc_name, res in self.services.items():
                if res.surface.confidence < 0.5:
                    errors.append(
                        f"Service '{svc_name}' below strict fidelity (confidence={res.surface.confidence})"
                    )
        return errors

    def validate_character_refs(self, catalog: dict[str, Any] | None) -> list[str]:
        """Validate that every entry in ``self.characters`` has a
        matching entry in ``catalog`` (PMF Plan Phase 4C Step 11
        post-impl audit M3).

        Returns the list of dangling references — character IDs
        that appear in ``self.characters`` but are NOT present as
        keys in ``catalog``. Empty list = all references resolve.
        ``catalog=None`` treats the check as "no catalog wired"
        and returns ``self.characters`` if it's non-empty so the
        consumer sees the misconfiguration explicitly rather
        than silently accepting dangling refs.

        The check is OPT-IN — ``WorldPlan`` doesn't hold a
        reference to a character catalog, so this is a helper
        the consumer calls at plan-assembly time.
        """
        if not self.characters:
            return []
        if catalog is None:
            return list(self.characters)
        return [cid for cid in self.characters if cid not in catalog]

    def get_service_names(self) -> list[str]:
        """All resolved service names."""
        return list(self.services.keys())

    def get_entity_types(self) -> set[str]:
        """All entity types across all resolved services."""
        types: set[str] = set()
        for res in self.services.values():
            types.update(res.surface.entity_schemas.keys())
        return types
