"""Condition overlays -- post-MVP expansion mechanism.

Overlays add focused condition dimensions without polluting core config.
Each overlay is self-contained: it defines new dimensions and how they
shape world data.  The :class:`OverlayRegistry` manages registration and
composition, following the same pattern as ``PackRegistry``.
"""

from __future__ import annotations

import abc
from typing import Any, ClassVar

from volnix.core.errors import RealityError

# ---------------------------------------------------------------------------
# Base overlay protocol
# ---------------------------------------------------------------------------


class Overlay(abc.ABC):
    """Abstract base for a condition overlay."""

    overlay_name: ClassVar[str] = ""
    description: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not getattr(cls, "overlay_name", ""):
            raise TypeError(f"Overlay subclass {cls.__name__} must define overlay_name")

    @abc.abstractmethod
    def get_dimensions(self) -> dict[str, Any]:
        """Return additional dimension definitions this overlay adds."""
        ...

    @abc.abstractmethod
    def apply(self, world_plan: dict[str, Any], dimension_values: dict[str, Any]) -> dict[str, Any]:
        """Apply overlay conditions to the world plan."""
        ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class OverlayRegistry:
    """Manages registration and composition of condition overlays."""

    def __init__(self) -> None:
        self._overlays: dict[str, Overlay] = {}

    def register(self, overlay: Overlay) -> None:
        """Register an overlay instance."""
        if overlay.overlay_name in self._overlays:
            raise RealityError(f"Overlay '{overlay.overlay_name}' already registered")
        self._overlays[overlay.overlay_name] = overlay

    def get(self, name: str) -> Overlay | None:
        """Retrieve a registered overlay by name."""
        return self._overlays.get(name)

    def list_overlays(self) -> list[dict[str, str]]:
        """List all registered overlays with name and description."""
        return [
            {"name": o.overlay_name, "description": o.description} for o in self._overlays.values()
        ]

    def compose(
        self,
        overlay_names: list[str],
        world_plan: dict[str, Any],
        values: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply a sequence of overlays to a world plan.

        Parameters
        ----------
        overlay_names:
            Ordered list of overlay names to apply.
        world_plan:
            The base world plan dictionary.
        values:
            Dimension values keyed by overlay name.

        Returns
        -------
        dict:
            The world plan with all overlays applied.
        """
        result = dict(world_plan)
        for name in overlay_names:
            overlay = self._overlays.get(name)
            if overlay is None:
                raise RealityError(
                    f"Unknown overlay: '{name}'. Available: {sorted(self._overlays.keys())}"
                )
            overlay_values = values.get(name, {})
            result = overlay.apply(result, overlay_values)
        return result


# ---------------------------------------------------------------------------
# Post-MVP overlay stubs
# ---------------------------------------------------------------------------


class EconomicsOverlay(Overlay):
    """Overlay adding economic-pressure dimensions (budget constraints, etc.)."""

    overlay_name: ClassVar[str] = "economics"
    description: ClassVar[str] = "Economic pressure and budget constraint dimensions."

    def get_dimensions(self) -> dict[str, Any]:
        return {}

    def apply(self, world_plan: dict[str, Any], dimension_values: dict[str, Any]) -> dict[str, Any]:
        return world_plan


class ComplianceOverlay(Overlay):
    """Overlay adding regulatory-compliance dimensions."""

    overlay_name: ClassVar[str] = "compliance"
    description: ClassVar[str] = "Regulatory compliance and audit dimensions."

    def get_dimensions(self) -> dict[str, Any]:
        return {}

    def apply(self, world_plan: dict[str, Any], dimension_values: dict[str, Any]) -> dict[str, Any]:
        return world_plan


class MarketNoiseOverlay(Overlay):
    """Overlay adding market-noise dimensions (price fluctuation, etc.)."""

    overlay_name: ClassVar[str] = "market_noise"
    description: ClassVar[str] = "Market noise and price fluctuation dimensions."

    def get_dimensions(self) -> dict[str, Any]:
        return {}

    def apply(self, world_plan: dict[str, Any], dimension_values: dict[str, Any]) -> dict[str, Any]:
        return world_plan


class DeviceReliabilityOverlay(Overlay):
    """Overlay adding device / hardware reliability dimensions."""

    overlay_name: ClassVar[str] = "device_reliability"
    description: ClassVar[str] = "Device and hardware reliability dimensions."

    def get_dimensions(self) -> dict[str, Any]:
        return {}

    def apply(self, world_plan: dict[str, Any], dimension_values: dict[str, Any]) -> dict[str, Any]:
        return world_plan


class OrgPoliticsOverlay(Overlay):
    """Overlay adding organizational-politics dimensions."""

    overlay_name: ClassVar[str] = "org_politics"
    description: ClassVar[str] = "Organizational politics and internal friction dimensions."

    def get_dimensions(self) -> dict[str, Any]:
        return {}

    def apply(self, world_plan: dict[str, Any], dimension_values: dict[str, Any]) -> dict[str, Any]:
        return world_plan
