"""Semantic Kernel -- static service classification registry.

Maps service names to categories and provides canonical primitives.
33+ pre-mapped services across 9 categories. Dynamic registration supported.
"""
import logging
import tomllib
from pathlib import Path
from typing import Any

from terrarium.kernel.categories import CATEGORIES, SemanticCategory
from terrarium.kernel.primitives import get_primitives_for_category, SemanticPrimitive

logger = logging.getLogger(__name__)


class SemanticRegistry:

    def __init__(self) -> None:
        self._categories: dict[str, SemanticCategory] = {}
        self._service_map: dict[str, str] = {}
        self._initialized = False

    async def initialize(self) -> None:
        # FIX-16: Make initialize() idempotent
        if self._initialized:
            return
        self._categories = dict(CATEGORIES)
        toml_path = Path(__file__).parent / "data" / "services.toml"
        if toml_path.exists():
            with toml_path.open("rb") as f:
                data = tomllib.load(f)
            for svc, cat in data.get("services", {}).items():
                if cat in self._categories:
                    self._service_map[svc.lower()] = cat
                else:
                    logger.warning("Service '%s' maps to unknown category '%s'", svc, cat)
        self._initialized = True
        logger.info("Kernel: %d categories, %d services", len(self._categories), len(self._service_map))

    def _check_initialized(self) -> None:
        """Guard: raise if registry has not been initialized."""
        if not self._initialized:
            raise RuntimeError("SemanticRegistry not initialized. Call await initialize() first.")

    def get_category(self, service_name: str) -> str | None:
        self._check_initialized()
        return self._service_map.get(service_name.lower())

    def get_primitives(self, category: str) -> list[dict[str, Any]]:
        self._check_initialized()
        return [p.model_dump() for p in get_primitives_for_category(category)]

    def get_service_mapping(self, service_name: str) -> dict[str, Any] | None:
        cat = self.get_category(service_name)
        if cat is None:
            return None
        cat_obj = self._categories.get(cat)
        return {
            "service": service_name,
            "category": cat,
            "category_description": cat_obj.description if cat_obj else "",
            "primitives": [p.name for p in get_primitives_for_category(cat)],
        }

    def list_categories(self) -> list[str]:
        self._check_initialized()
        return sorted(self._categories.keys())

    def list_services(self, category: str | None = None) -> list[str]:
        self._check_initialized()
        if category is None:
            return sorted(self._service_map.keys())
        return sorted(s for s, c in self._service_map.items() if c == category)

    def register_service(self, service_name: str, category: str) -> None:
        if category not in self._categories:
            raise ValueError(f"Unknown category: '{category}'. Valid: {self.list_categories()}")
        self._service_map[service_name.lower()] = category

    def has_service(self, service_name: str) -> bool:
        return service_name.lower() in self._service_map

    def has_category(self, category: str) -> bool:
        return category in self._categories
