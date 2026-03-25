"""Tests for terrarium.kernel.context_hub -- Context Hub CLI integration."""

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from terrarium.kernel.context_hub import ContextHubProvider
from terrarium.kernel.external_spec import ExternalSpecProvider


async def test_is_available_missing():
    """When chub CLI is not installed, is_available returns False."""
    provider = ContextHubProvider()
    with patch("terrarium.kernel.context_hub.shutil.which", return_value=None):
        result = await provider.is_available()
    assert result is False


async def test_is_available_installed():
    """When chub CLI is installed, is_available returns True."""
    provider = ContextHubProvider()
    with patch("terrarium.kernel.context_hub.shutil.which", return_value="/usr/local/bin/chub"):
        result = await provider.is_available()
    assert result is True


async def test_fetch_unavailable():
    """fetch returns None when chub is not installed."""
    provider = ContextHubProvider()
    with patch("terrarium.kernel.context_hub.shutil.which", return_value=None):
        result = await provider.fetch("stripe")
    assert result is None


async def test_supports_with_chub_installed():
    """supports() uses chub search to check availability."""
    provider = ContextHubProvider()

    proc_mock = AsyncMock()
    proc_mock.communicate = AsyncMock(return_value=(b"stripe/api\nstripe/webhooks\n", b""))
    proc_mock.returncode = 0

    with patch("terrarium.kernel.context_hub.shutil.which", return_value="/usr/local/bin/chub"):
        with patch(
            "terrarium.kernel.context_hub.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=proc_mock,
        ):
            with patch(
                "terrarium.kernel.context_hub.asyncio.wait_for",
                new_callable=AsyncMock,
                return_value=(b"stripe/api\nstripe/webhooks\n", b""),
            ):
                result = await provider.supports("stripe")
    assert result is True


async def test_supports_not_found():
    """supports() returns False when chub search finds nothing."""
    provider = ContextHubProvider()

    proc_mock = AsyncMock()
    proc_mock.communicate = AsyncMock(return_value=(b"", b""))
    proc_mock.returncode = 1

    with patch("terrarium.kernel.context_hub.shutil.which", return_value="/usr/local/bin/chub"):
        with patch(
            "terrarium.kernel.context_hub.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=proc_mock,
        ):
            with patch(
                "terrarium.kernel.context_hub.asyncio.wait_for",
                new_callable=AsyncMock,
                return_value=(b"", b""),
            ):
                result = await provider.supports("totally_unknown_xyz")
    assert result is False


async def test_supports_chub_not_installed():
    """supports() returns False when chub is not installed."""
    provider = ContextHubProvider()
    with patch("terrarium.kernel.context_hub.shutil.which", return_value=None):
        result = await provider.supports("stripe")
    assert result is False


async def test_fetch_success():
    """fetch() returns structured dict when chub get succeeds."""
    provider = ContextHubProvider()
    doc_content = "# Stripe API\n\n## Endpoints\n- POST /v1/charges\n"

    proc_mock = AsyncMock()
    proc_mock.communicate = AsyncMock(return_value=(doc_content.encode(), b""))
    proc_mock.returncode = 0

    with patch("terrarium.kernel.context_hub.shutil.which", return_value="/usr/local/bin/chub"):
        with patch(
            "terrarium.kernel.context_hub.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=proc_mock,
        ):
            with patch(
                "terrarium.kernel.context_hub.asyncio.wait_for",
                new_callable=AsyncMock,
                return_value=(doc_content.encode(), b""),
            ):
                result = await provider.fetch("stripe")

    assert result is not None
    assert result["source"] == "context_hub"
    assert result["service"] == "stripe"
    assert result["raw_content"] == doc_content
    assert result["content_type"] == "markdown"


async def test_fetch_not_found():
    """fetch() returns None when chub get fails (rc != 0)."""
    provider = ContextHubProvider()

    proc_mock = AsyncMock()
    proc_mock.communicate = AsyncMock(return_value=(b"", b"Not found"))
    proc_mock.returncode = 1

    with patch("terrarium.kernel.context_hub.shutil.which", return_value="/usr/local/bin/chub"):
        with patch(
            "terrarium.kernel.context_hub.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            return_value=proc_mock,
        ):
            with patch(
                "terrarium.kernel.context_hub.asyncio.wait_for",
                new_callable=AsyncMock,
                return_value=(b"", b"Not found"),
            ):
                result = await provider.fetch("nonexistent_service")

    assert result is None


async def test_protocol_compliance():
    """ContextHubProvider satisfies the ExternalSpecProvider protocol."""
    provider = ContextHubProvider()
    assert isinstance(provider, ExternalSpecProvider)
    assert hasattr(provider, "provider_name")
    assert provider.provider_name == "context_hub"
    assert hasattr(provider, "is_available")
    assert hasattr(provider, "fetch")
    assert hasattr(provider, "supports")


async def test_timeout_handling():
    """Timeout during fetch returns None gracefully."""
    provider = ContextHubProvider(timeout=0.001)
    with patch("terrarium.kernel.context_hub.shutil.which", return_value="/usr/local/bin/chub"):
        with patch(
            "terrarium.kernel.context_hub.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
        ) as mock_exec:
            proc_mock = AsyncMock()
            proc_mock.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
            mock_exec.return_value = proc_mock

            with patch(
                "terrarium.kernel.context_hub.asyncio.wait_for",
                side_effect=asyncio.TimeoutError,
            ):
                result = await provider.fetch("stripe")

    assert result is None
