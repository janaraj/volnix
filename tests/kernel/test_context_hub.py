"""Tests for terrarium.kernel.context_hub -- Context Hub CLI integration."""

import asyncio
from unittest.mock import patch, AsyncMock

import pytest

from terrarium.kernel.context_hub import ContextHubProvider
from terrarium.kernel.external_spec import ExternalSpecProvider


async def test_is_available_missing():
    """When chub CLI is not installed, is_available returns False."""
    provider = ContextHubProvider()
    with patch("terrarium.kernel.context_hub.shutil.which", return_value=None):
        result = await provider.is_available()
    assert result is False


async def test_fetch_unavailable():
    """fetch returns None when chub is not installed."""
    provider = ContextHubProvider()
    with patch("terrarium.kernel.context_hub.shutil.which", return_value=None):
        result = await provider.fetch("stripe")
    assert result is None


async def test_supports_known():
    """Known services like 'stripe' return True from supports."""
    provider = ContextHubProvider()
    assert await provider.supports("stripe") is True
    assert await provider.supports("github") is True
    assert await provider.supports("totally_unknown_xyz") is False


async def test_protocol_compliance():
    """ContextHubProvider satisfies the ExternalSpecProvider protocol."""
    provider = ContextHubProvider()
    assert isinstance(provider, ExternalSpecProvider)
    # Verify required attributes
    assert hasattr(provider, "provider_name")
    assert provider.provider_name == "context_hub"
    assert hasattr(provider, "is_available")
    assert hasattr(provider, "fetch")
    assert hasattr(provider, "supports")


async def test_timeout_handling():
    """Timeout during fetch returns None gracefully."""
    provider = ContextHubProvider(timeout=0.001)  # extremely short timeout
    # Simulate chub being installed but timing out
    with patch("terrarium.kernel.context_hub.shutil.which", return_value="/usr/local/bin/chub"):
        with patch(
            "terrarium.kernel.context_hub.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
        ) as mock_exec:
            # Make communicate() hang so wait_for times out
            proc_mock = AsyncMock()
            proc_mock.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
            mock_exec.return_value = proc_mock

            with patch(
                "terrarium.kernel.context_hub.asyncio.wait_for",
                side_effect=asyncio.TimeoutError,
            ):
                result = await provider.fetch("stripe")

    assert result is None
