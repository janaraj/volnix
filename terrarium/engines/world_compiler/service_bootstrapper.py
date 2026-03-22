"""Service bootstrapper — compile-time inference for unknown services.

When no Tier 1 pack or Tier 2 profile exists, the bootstrapper infers
a service surface at compile time. The result is used as Tier 2 at runtime.

Uses: ServiceResolver (D3), SemanticRegistry (D3), LLMRouter (B3).
capture_surface() and compile_to_pack() are Phase G4 (promotion pipeline).
"""

from __future__ import annotations

import logging
from typing import Any

from terrarium.kernel.surface import ServiceSurface

logger = logging.getLogger(__name__)


class ServiceBootstrapper:
    """Bootstraps service surfaces for unknown services at compile time."""

    def __init__(
        self,
        kernel: Any = None,
        resolver: Any = None,
        llm_router: Any = None,
    ) -> None:
        self._kernel = kernel
        self._resolver = resolver
        self._llm_router = llm_router

    async def bootstrap(
        self, service_name: str, category: str
    ) -> ServiceSurface | None:
        """Bootstrap a service surface from name + category.

        Delegates to ServiceResolver.resolve() which runs the full
        resolution chain: context hub -> openapi -> kernel -> LLM inference.
        Returns None if resolution fails.
        """
        if self._resolver:
            try:
                surface = await self._resolver.resolve(service_name)
                if surface:
                    return surface
            except Exception as exc:
                logger.warning(
                    "Bootstrap resolution failed for %s: %s",
                    service_name,
                    exc,
                )

        # Minimal fallback surface
        if self._kernel:
            try:
                return ServiceSurface(
                    service_name=service_name,
                    category=category,
                    source="kernel_bootstrap",
                    fidelity_tier=2,
                    confidence=0.2,
                    operations=[],
                    entity_schemas={},
                    state_machines={},
                )
            except Exception:
                pass

        return None

    async def bootstrap_from_external_spec(
        self, service_name: str, spec_source: str
    ) -> ServiceSurface | None:
        """Bootstrap from an external specification (OpenAPI URL, etc.).

        Uses the resolver's OpenAPI provider if available.
        """
        if self._resolver and hasattr(self._resolver, "resolve_from_spec"):
            try:
                return await self._resolver.resolve_from_spec(
                    service_name, spec_source
                )
            except Exception as exc:
                logger.warning(
                    "External spec bootstrap failed for %s from %s: %s",
                    service_name,
                    spec_source,
                    exc,
                )

        # If resolver doesn't support spec resolution, try direct resolve
        if self._resolver:
            try:
                return await self._resolver.resolve(service_name)
            except Exception:
                pass

        return None

    async def capture_surface(
        self, service_name: str, run_id: str
    ) -> ServiceSurface:
        """Capture a bootstrapped surface from a completed run for reuse.

        Phase G4 — promotion pipeline: capture -> compile-pack -> verify -> promote.
        Not implemented in D4b.
        """
        raise NotImplementedError(
            "Phase G4 — promotion pipeline: capture -> compile-pack -> "
            "verify -> promote. This captures a runtime-profiled surface "
            "for promotion to a verified pack."
        )

    async def compile_to_pack(
        self, surface: ServiceSurface, output_dir: str
    ) -> str:
        """Compile a ServiceSurface into a Tier 1 verified pack.

        Phase G4 — promotion pipeline: capture -> compile-pack -> verify -> promote.
        Not implemented in D4b.
        """
        raise NotImplementedError(
            "Phase G4 — promotion pipeline: capture -> compile-pack -> "
            "verify -> promote. This generates a verified pack from a "
            "captured service surface."
        )
