"""Tests for terrarium.reality.overlays -- OverlayRegistry and overlay stubs."""

import pytest

from terrarium.reality.overlays import (
    ComplianceOverlay,
    EconomicsOverlay,
    Overlay,
    OverlayRegistry,
)


class TestOverlayRegistry:
    """Verify overlay registration and retrieval."""

    def test_overlay_registry_register(self) -> None:
        """Registering an overlay makes it retrievable by name."""
        ...

    def test_overlay_registry_list(self) -> None:
        """Listing overlays returns name and description for each."""
        ...

    def test_overlay_compose(self) -> None:
        """Composing overlays applies them in sequence to a world plan."""
        ...


class TestOverlayStubs:
    """Verify post-MVP overlay stub classes exist and have correct metadata."""

    def test_economics_overlay_stub(self) -> None:
        """EconomicsOverlay has the correct overlay_name."""
        ...

    def test_compliance_overlay_stub(self) -> None:
        """ComplianceOverlay has the correct overlay_name."""
        ...
