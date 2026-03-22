"""Full service resolution chain for the world compiler.

Bridges PackRegistry (Tier 1/2) with ServiceResolver (external specs + kernel).
"""
from __future__ import annotations
import logging
from typing import Any

from terrarium.core.errors import (
    KernelError,
    PackNotFoundError,
    ServiceResolutionError,
)
from terrarium.engines.world_compiler.plan import ServiceResolution
from terrarium.kernel.registry import SemanticRegistry
from terrarium.kernel.resolver import ServiceResolver
from terrarium.kernel.surface import ServiceSurface
from terrarium.packs.registry import PackRegistry

logger = logging.getLogger(__name__)


class CompilerServiceResolver:
    """Resolves ALL services in a world definition."""

    def __init__(
        self,
        pack_registry: PackRegistry | None = None,
        kernel: SemanticRegistry | None = None,
        resolver: ServiceResolver | None = None,
    ) -> None:
        self._packs = pack_registry
        self._kernel = kernel
        self._resolver = resolver

    def get_available_categories(self) -> str:
        """Return comma-separated list of available semantic categories."""
        if self._kernel:
            return ", ".join(self._kernel.list_categories())
        return ""

    def get_available_packs(self) -> str:
        """Return comma-separated list of available pack names."""
        if self._packs:
            return ", ".join(p["pack_name"] for p in self._packs.list_packs())
        return ""

    async def resolve_all(
        self,
        service_specs: dict[str, Any],
        fidelity_mode: str = "auto",
    ) -> tuple[dict[str, ServiceResolution], list[str]]:
        """Resolve ALL services. Returns (resolutions, warnings)."""
        resolutions: dict[str, ServiceResolution] = {}
        warnings: list[str] = []

        for svc_name, spec_ref in service_specs.items():
            try:
                resolution = await self.resolve_one(svc_name, spec_ref, fidelity_mode)
                if resolution:
                    resolutions[svc_name] = resolution
                else:
                    warnings.append(f"Could not resolve service '{svc_name}'")
            except (PackNotFoundError, ServiceResolutionError, KernelError, KeyError, ValueError) as exc:
                warnings.append(f"Error resolving '{svc_name}': {exc}")

        return resolutions, warnings

    async def resolve_one(
        self,
        service_name: str,
        spec_reference: Any,
        fidelity_mode: str = "auto",
    ) -> ServiceResolution | None:
        """Resolve a single service through the full chain."""
        tier, name = self._parse_spec_reference(spec_reference)

        # Step 1: Verified pack
        if tier == "verified" and self._packs:
            try:
                pack = self._packs.get_pack(name)
                surface = ServiceSurface.from_pack(pack)
                return ServiceResolution(
                    service_name=service_name,
                    spec_reference=str(spec_reference),
                    surface=surface,
                    resolution_source="tier1_pack",
                )
            except Exception:
                logger.debug("No verified pack for '%s'", name)

        # Step 2: Profiled service
        if tier == "profiled" and self._packs:
            try:
                # Try to get the base pack that the profile extends
                # Profile name often matches the service name
                profiles = self._packs.get_profiles_for_pack(name)
                if profiles:
                    # Use base pack's surface, marked as tier2_profile
                    try:
                        base_pack = self._packs.get_pack(profiles[0].extends_pack)
                        surface = ServiceSurface.from_pack(base_pack)
                        # Override fidelity to Tier 2
                        surface = ServiceSurface(
                            service_name=service_name,
                            category=surface.category,
                            source="tier2_profile",
                            fidelity_tier=2,
                            operations=surface.operations,
                            entity_schemas=surface.entity_schemas,
                            state_machines=surface.state_machines,
                            confidence=0.8,
                        )
                        return ServiceResolution(
                            service_name=service_name,
                            spec_reference=str(spec_reference),
                            surface=surface,
                            resolution_source="tier2_profile",
                        )
                    except Exception:
                        logger.debug("Could not resolve base pack for profile '%s'", name)
            except Exception:
                pass

        # Steps 3-6: External specs + kernel (via D3 ServiceResolver)
        if self._resolver:
            surface = await self._resolver.resolve(service_name)
            if surface:
                # Check fidelity threshold in strict mode
                if fidelity_mode == "strict" and surface.confidence < 0.5:
                    logger.warning("Skipping '%s' in strict mode (confidence=%.1f)", service_name, surface.confidence)
                    return None
                return ServiceResolution(
                    service_name=service_name,
                    spec_reference=str(spec_reference),
                    surface=surface,
                    resolution_source=surface.source,
                )

        return None

    def _parse_spec_reference(self, spec_ref: Any) -> tuple[str, str]:
        """Parse spec reference into (tier, name).

        'verified/email' → ('verified', 'email')
        'profiled/stripe' → ('profiled', 'stripe')
        'stripe' → ('auto', 'stripe')
        dict → ('complex', pack_name_from_provider_key)
        """
        if isinstance(spec_ref, dict):
            provider = spec_ref.get("provider", "")
            if "/" in provider:
                parts = provider.split("/", 1)
                return parts[0], parts[1]
            return "complex", provider
        if isinstance(spec_ref, str) and "/" in spec_ref:
            parts = spec_ref.split("/", 1)
            return parts[0], parts[1]
        return "auto", str(spec_ref)
