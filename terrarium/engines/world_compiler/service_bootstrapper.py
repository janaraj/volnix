"""Service bootstrapper -- compile-time inference for unknown services.

When a user mentions a service with no Tier 1 pack or Tier 2 profile,
the bootstrapper infers a service surface (tools, schemas, state model)
at compile time. The result is used as a Tier 2 profile at runtime.

This replaces the old "Tier 3 runtime inference" concept. Inference
is now strictly a compilation step, not a runtime mode.
"""
from __future__ import annotations

from typing import Any

from terrarium.core.types import ServiceId, FidelitySource


class ServiceSurface:
    """The output of bootstrapping -- a compiled service surface."""

    # (BaseModel with: service_name, category, tools, entity_schemas,
    #  state_machines, behavioral_annotations, response_templates,
    #  fidelity_source=BOOTSTRAPPED)
    ...


class ServiceBootstrapper:
    def __init__(self, kernel: Any = None, llm_router: Any = None) -> None: ...

    async def bootstrap(self, service_name: str, category: str) -> ServiceSurface:
        """Bootstrap a service surface from name + category + LLM knowledge.

        This runs at compile time. The output ServiceSurface is used as a
        Tier 2 profile during the runtime phase.
        """
        ...

    async def bootstrap_from_external_spec(
        self, service_name: str, spec_source: str
    ) -> ServiceSurface:
        """Bootstrap from an external specification (OpenAPI, Context Hub, etc.)."""
        ...

    async def capture_surface(self, service_name: str, run_id: str) -> ServiceSurface:
        """Capture a bootstrapped surface from a completed run for reuse."""
        ...

    async def compile_to_pack(self, surface: ServiceSurface, output_dir: str) -> str:
        """Compile a ServiceSurface into a Tier 1 verified pack (code generation)."""
        ...
