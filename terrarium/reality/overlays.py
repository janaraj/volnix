"""Condition overlays -- post-MVP expansion mechanism.

Overlays add focused condition dimensions without polluting core config.
Each overlay is self-contained: it defines new dimensions and how they
shape world data.
"""

from __future__ import annotations

import abc
from typing import Any, ClassVar


# ---------------------------------------------------------------------------
# Base overlay protocol
# ---------------------------------------------------------------------------


class Overlay(abc.ABC):
    """Abstract base for a condition overlay."""

    overlay_name: ClassVar[str]
    description: ClassVar[str]

    @abc.abstractmethod
    def get_dimensions(self) -> dict[str, Any]:
        """Return additional dimension definitions this overlay adds."""
        ...

    @abc.abstractmethod
    def apply(self, world_plan: dict, dimension_values: dict) -> dict:
        """Apply overlay conditions to the world plan."""
        ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class OverlayRegistry:
    """Manages registration and composition of condition overlays."""

    def __init__(self) -> None:
        ...

    def register(self, overlay: Overlay) -> None:
        """Register an overlay instance."""
        ...

    def get(self, name: str) -> Overlay | None:
        """Retrieve a registered overlay by name."""
        ...

    def list_overlays(self) -> list[dict[str, str]]:
        """List all registered overlays with name and description."""
        ...

    def compose(
        self,
        overlay_names: list[str],
        world_plan: dict,
        values: dict,
    ) -> dict:
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
        ...


# ---------------------------------------------------------------------------
# Post-MVP overlay stubs
# ---------------------------------------------------------------------------


class EconomicsOverlay(Overlay):
    """Overlay adding economic-pressure dimensions (budget constraints, etc.)."""

    overlay_name: ClassVar[str] = "economics"
    description: ClassVar[str] = "Economic pressure and budget constraint dimensions."

    def get_dimensions(self) -> dict[str, Any]:
        ...

    def apply(self, world_plan: dict, dimension_values: dict) -> dict:
        ...


class ComplianceOverlay(Overlay):
    """Overlay adding regulatory-compliance dimensions."""

    overlay_name: ClassVar[str] = "compliance"
    description: ClassVar[str] = "Regulatory compliance and audit dimensions."

    def get_dimensions(self) -> dict[str, Any]:
        ...

    def apply(self, world_plan: dict, dimension_values: dict) -> dict:
        ...


class MarketNoiseOverlay(Overlay):
    """Overlay adding market-noise dimensions (price fluctuation, etc.)."""

    overlay_name: ClassVar[str] = "market_noise"
    description: ClassVar[str] = "Market noise and price fluctuation dimensions."

    def get_dimensions(self) -> dict[str, Any]:
        ...

    def apply(self, world_plan: dict, dimension_values: dict) -> dict:
        ...


class DeviceReliabilityOverlay(Overlay):
    """Overlay adding device / hardware reliability dimensions."""

    overlay_name: ClassVar[str] = "device_reliability"
    description: ClassVar[str] = "Device and hardware reliability dimensions."

    def get_dimensions(self) -> dict[str, Any]:
        ...

    def apply(self, world_plan: dict, dimension_values: dict) -> dict:
        ...


class OrgPoliticsOverlay(Overlay):
    """Overlay adding organizational-politics dimensions."""

    overlay_name: ClassVar[str] = "org_politics"
    description: ClassVar[str] = "Organizational politics and internal friction dimensions."

    def get_dimensions(self) -> dict[str, Any]:
        ...

    def apply(self, world_plan: dict, dimension_values: dict) -> dict:
        ...
