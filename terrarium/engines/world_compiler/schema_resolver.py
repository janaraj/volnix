"""Schema resolver -- resolves service schemas via verified packs, profiles, or LLM."""

from __future__ import annotations

from typing import Any

from terrarium.llm.router import LLMRouter


class SchemaResolver:
    """Resolves service schemas through a tiered fallback strategy.

    Resolution order:
    1. Verified service pack
    2. Curated profile
    3. External API specification
    4. LLM inference
    """

    def __init__(
        self, kernel: Any, pack_registry: dict[str, Any], llm_router: LLMRouter
    ) -> None:
        self._kernel = kernel
        self._pack_registry = pack_registry
        self._llm_router = llm_router

    async def resolve(self, service_name: str) -> dict[str, Any]:
        """Resolve a service schema (ServiceSchema) by name."""
        ...

    def _check_verified_pack(self, service_name: str) -> dict[str, Any] | None:
        """Check if a verified service pack exists for the service."""
        ...

    def _check_curated_profile(self, service_name: str) -> dict[str, Any] | None:
        """Check if a curated profile exists for the service."""
        ...

    async def _check_external_spec(self, service_name: str) -> dict[str, Any] | None:
        """Attempt to fetch an external API specification for the service."""
        ...

    async def _bootstrap_service(
        self, service_name: str, category: str
    ) -> dict[str, Any]:
        """Bootstrap service surface at compile time."""
        ...
