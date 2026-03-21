"""Semantic registry for mapping services to categories and primitives.

The :class:`SemanticRegistry` loads static data from TOML files on disk
and provides lookup methods for service-to-category mappings, category
metadata, and per-category primitives.
"""

from __future__ import annotations

from terrarium.kernel.categories import SemanticCategory
from terrarium.kernel.primitives import SemanticPrimitive


class SemanticRegistry:
    """Central registry mapping services to semantic categories and primitives.

    Data is loaded lazily from TOML files via :meth:`initialize`.  After
    initialisation the registry is read-only except for explicit
    :meth:`register_service` calls.
    """

    def __init__(self) -> None:
        self._categories: dict[str, SemanticCategory] = {}
        self._service_map: dict[str, str] = {}
        self._primitives: dict[str, list[dict]] = {}

    async def initialize(self) -> None:
        """Load category and service mapping data from TOML files."""
        ...

    def get_category(self, service_name: str) -> str | None:
        """Return the category name for *service_name*, or ``None``."""
        ...

    def get_primitives(self, category: str) -> list[dict]:
        """Return the list of primitive dicts for the given *category*."""
        ...

    def get_service_mapping(self, service_name: str) -> dict | None:
        """Return full mapping metadata for a service, or ``None``."""
        ...

    def list_categories(self) -> list[str]:
        """Return a sorted list of all known category names."""
        ...

    def list_services(self, category: str | None = None) -> list[str]:
        """Return service names, optionally filtered by *category*."""
        ...

    def register_service(self, service_name: str, category: str) -> None:
        """Dynamically register a new service-to-category mapping."""
        ...
