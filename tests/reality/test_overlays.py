"""Tests for terrarium.reality.overlays -- OverlayRegistry and Overlay ABC.

Tests the registry framework for registering, retrieving, and listing
condition overlays. Also verifies the ABC cannot be directly instantiated.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from terrarium.reality.overlays import Overlay, OverlayRegistry


class _TestOverlay(Overlay):
    """Concrete overlay implementation for testing."""

    overlay_name: ClassVar[str] = "test_overlay"
    description: ClassVar[str] = "A test overlay for unit tests."

    def get_dimensions(self) -> dict[str, Any]:
        return {"test_dim": {"range": [0, 100]}}

    def apply(self, world_plan: dict, dimension_values: dict) -> dict:
        world_plan["test_applied"] = True
        return world_plan


class TestRegistryRegisterAndGet:
    """Register an overlay and retrieve it by name."""

    def test_registry_register_and_get(self) -> None:
        registry = OverlayRegistry()
        overlay = _TestOverlay()
        registry.register(overlay)
        retrieved = registry.get("test_overlay")
        assert retrieved is overlay


class TestRegistryList:
    """list_overlays returns metadata for all registered overlays."""

    def test_registry_list(self) -> None:
        registry = OverlayRegistry()
        overlay = _TestOverlay()
        registry.register(overlay)
        overlays = registry.list_overlays()
        assert len(overlays) >= 1
        names = [o["name"] for o in overlays]
        assert "test_overlay" in names


class TestUnknownOverlayNone:
    """Requesting an unknown overlay name returns None."""

    def test_unknown_overlay_none(self) -> None:
        registry = OverlayRegistry()
        result = registry.get("nonexistent")
        assert result is None


class TestAbcNotInstantiable:
    """The Overlay ABC cannot be directly instantiated."""

    def test_abc_not_instantiable(self) -> None:
        with pytest.raises(TypeError):
            Overlay()  # type: ignore[abstract]


class TestRegistryEmpty:
    """A new registry has no overlays."""

    def test_registry_empty(self) -> None:
        registry = OverlayRegistry()
        overlays = registry.list_overlays()
        assert overlays == []
        assert registry.get("anything") is None
