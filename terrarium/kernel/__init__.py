"""Semantic Kernel -- static registry of service categories and primitives.

This package provides the semantic classification layer that maps external
services to abstract categories (communication, work_management, etc.) and
defines the canonical primitives within each category.

Re-exports the primary public API surface::

    from terrarium.kernel import SemanticRegistry, SemanticCategory, SemanticPrimitive
"""

from terrarium.kernel.categories import CATEGORIES, SemanticCategory
from terrarium.kernel.primitives import SemanticPrimitive, get_primitives_for_category
from terrarium.kernel.registry import SemanticRegistry

__all__ = [
    "CATEGORIES",
    "SemanticCategory",
    "SemanticPrimitive",
    "SemanticRegistry",
    "get_primitives_for_category",
]
