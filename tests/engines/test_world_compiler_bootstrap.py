"""Tests for world compiler service bootstrapper."""

import pytest


@pytest.mark.asyncio
async def test_bootstrap_unknown_service():
    """Test bootstrapping an unknown service into a ServiceSurface."""
    ...


@pytest.mark.asyncio
async def test_bootstrap_from_external_spec():
    """Test bootstrapping from an external specification."""
    ...


@pytest.mark.asyncio
async def test_capture_surface():
    """Test capturing a bootstrapped surface from a completed run."""
    ...


@pytest.mark.asyncio
async def test_compile_to_pack():
    """Test compiling a ServiceSurface into a Tier 1 pack."""
    ...


@pytest.mark.asyncio
async def test_bootstrapped_surface_is_tier2():
    """Test that a bootstrapped surface is treated as Tier 2 at runtime."""
    ...
