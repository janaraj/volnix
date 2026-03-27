"""WorldPlan — the contract between D4a (planning) and D4b (generation).

A WorldPlan is the COMPLETE plan for a world: resolved services,
reality conditions, actor specs, policies, seeds. It contains
everything D4b needs to generate entities and populate the StateEngine.
"""
from __future__ import annotations
from typing import Any, Literal

from pydantic import BaseModel, Field

from terrarium.kernel.surface import ServiceSurface
from terrarium.reality.dimensions import WorldConditions


class ServiceResolution(BaseModel, frozen=True):
    """Resolution metadata for a single service."""
    service_name: str
    spec_reference: str          # "verified/gmail", "profiled/stripe", bare "stripe"
    surface: ServiceSurface
    resolution_source: str       # "tier1_pack", "context_hub", "openapi", "llm_inference", "kernel_inference"


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

    # ── Resolved services (D4a fills) ──
    services: dict[str, ServiceResolution] = Field(default_factory=dict)

    # ── Actor specs (raw, D4b expands) ──
    actor_specs: list[dict[str, Any]] = Field(default_factory=list)

    # ── Reality (D1) ──
    conditions: WorldConditions = Field(default_factory=WorldConditions)
    reality_prompt_context: dict[str, Any] = Field(default_factory=dict)

    # ── Raw YAML sections (D4b processes) ──
    policies: list[dict[str, Any]] = Field(default_factory=list)
    seeds: list[str] = Field(default_factory=list)
    mission: str = ""

    # ── Runtime settings (carried to engines) ──
    animator_settings: dict[str, Any] = Field(default_factory=dict)

    # ── Blueprint (if detected) ──
    blueprint: str | None = None

    # ── Compilation metadata ──
    source: str = ""                # "yaml" or "nl"
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
                    errors.append(f"Service '{svc_name}' below strict fidelity (confidence={res.surface.confidence})")
        return errors

    def get_service_names(self) -> list[str]:
        """All resolved service names."""
        return list(self.services.keys())

    def get_entity_types(self) -> set[str]:
        """All entity types across all resolved services."""
        types: set[str] = set()
        for res in self.services.values():
            types.update(res.surface.entity_schemas.keys())
        return types
