"""Service resolver -- orchestrates the resolution chain.

Tries sources in confidence order:
1. Tier 1 Pack
2. Tier 2 Profile
3. Context Hub
4. OpenAPI spec
5. LLM inference (D4 callback)
6. Kernel classification (primitives only)
"""

import logging
from collections.abc import Awaitable, Callable

from volnix.kernel.external_spec import ExternalSpecProvider
from volnix.kernel.registry import SemanticRegistry
from volnix.kernel.surface import APIOperation, ServiceSurface

logger = logging.getLogger(__name__)

# Type for the LLM inference callback (injected by D4)
LLMInferCallback = Callable[[str, str, list[dict]], Awaitable[ServiceSurface | None]]


class ServiceResolver:
    """Resolves a service name to a ServiceSurface.

    The resolution chain:
    1. Pack (Tier 1) -- from pack_registry
    2. Profile (Tier 2) -- from pack_registry profiles
    3. External specs (Context Hub, OpenAPI) -- from providers list
    4. LLM inference -- from injected callback (D4 adds this)
    5. Kernel classification -- primitives as weak signal
    """

    def __init__(
        self,
        kernel: SemanticRegistry,
        providers: list[ExternalSpecProvider] | None = None,
        llm_infer: LLMInferCallback | None = None,
    ) -> None:
        self._kernel = kernel
        self._providers = providers or []
        self._llm_infer = llm_infer  # D4 injects this

    async def resolve(self, service_name: str) -> ServiceSurface | None:
        """Try each source in order. Return first successful resolution."""
        name = service_name.lower()

        # Steps 1-2 (pack/profile) are handled by the caller (D4 compiler)
        # because they require PackRegistry which isn't a kernel dependency.
        # This resolver handles steps 3-6.

        # Step 3-4: External spec providers
        for provider in self._providers:
            try:
                if await provider.is_available() and await provider.supports(name):
                    spec = await provider.fetch(name)
                    if spec:
                        surface = self._surface_from_spec(spec, name, provider.provider_name)
                        if surface:
                            logger.info("Resolved '%s' via %s", name, provider.provider_name)
                            return surface
            except Exception as exc:
                logger.warning("Provider %s failed for '%s': %s", provider.provider_name, name, exc)

        # FIX-22: Compute category + primitives once, reuse in LLM block and kernel fallback
        category = self._kernel.get_category(name)
        primitives = self._kernel.get_primitives(category) if category else []

        # Step 5: LLM inference (if D4 injected the callback)
        if self._llm_infer:
            try:
                surface = await self._llm_infer(name, category or "", primitives)
                if surface:
                    logger.info("Resolved '%s' via LLM inference", name)
                    return surface
            except Exception as exc:
                logger.warning("LLM inference failed for '%s': %s", name, exc)

        # Step 6: Kernel classification (weakest signal)
        # FIX-14/FIX-15: fidelity_tier=2 for all external/inferred sources. The spec
        # only defines Tier 1 (packs) and Tier 2 (everything else). We use confidence
        # to differentiate quality within Tier 2.
        # This surface has empty operations and needs LLM bootstrapping before use.
        # confidence=0.1 distinguishes it from other Tier 2 sources (e.g. OpenAPI=0.5).
        if category:
            logger.info("Resolved '%s' via kernel classification -> %s", name, category)
            return ServiceSurface(
                service_name=name,
                category=category,
                source="kernel_inference",
                fidelity_tier=2,
                operations=[],
                entity_schemas={
                    p["name"]: {"type": "object", "fields": p.get("fields", {})} for p in primitives
                },
                state_machines={},
                confidence=0.1,
            )

        return None

    def _surface_from_spec(
        self, spec: dict, service_name: str, source: str
    ) -> ServiceSurface | None:
        """Convert an external spec dict to a ServiceSurface."""
        category = self._kernel.get_category(service_name) or "unknown"
        operations = []

        # If spec has parsed operations (from OpenAPI)
        for op_data in spec.get("operations", []):
            operations.append(
                APIOperation(
                    name=op_data.get("name", ""),
                    service=service_name,
                    description=op_data.get("description", ""),
                    http_method=op_data.get("http_method", "POST"),
                    http_path=op_data.get("http_path", ""),
                    parameters=op_data.get("parameters", {}),
                    required_params=op_data.get("required_params", []),
                    response_schema=op_data.get("response_schema", {}),
                )
            )

        # FIX-14: fidelity_tier=2 for all external sources. Differentiate via confidence.
        return ServiceSurface(
            service_name=service_name,
            category=category,
            source=source,
            fidelity_tier=2,
            operations=operations,
            confidence=0.7 if source == "context_hub" else 0.5,
            raw_spec=spec.get("raw_content", ""),
        )
