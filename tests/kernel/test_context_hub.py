"""Tests for volnix.kernel.context_hub -- Context Hub via npx integration."""

import asyncio
from unittest.mock import AsyncMock, patch

from volnix.kernel.context_hub import ContextHubProvider
from volnix.kernel.external_spec import ExternalSpecProvider

# Real output captured from ``npx @aisuite/chub search twilio``
_TWILIO_SEARCH_OUTPUT = """\
3 results for "twilio":

  twilio/package  [doc]  py  [maintainer]
       Twilio Python helper library for REST API access, messagi...
  twilio/messaging  [doc]  py, ts  [maintainer]
       Cloud communications platform for SMS, voice, video, and ...
  sendgrid/package  [doc]  py  [maintainer]
       Twilio SendGrid Python SDK for sending email and calling ...
"""

_STRIPE_SEARCH_OUTPUT = """\
2 results for "stripe":

  stripe/api  [doc]  js  [maintainer]
       Payment processing platform with comprehensive payment an...
  stripe/payments  [doc]  js  [maintainer]
       Payment processing platform with comprehensive payment an...
"""

_EMPTY_SEARCH_OUTPUT = """\
0 results for "totally_unknown_xyz":
"""

_TWILIO_DOC_CONTENT = """\
---
name: messaging
description: "Cloud communications platform"
---
# Twilio Python Library

## Send SMS
client.messages.create(to="+1...", from_="+1...", body="Hello")
"""


def _mock_subprocess(stdout: str, returncode: int = 0):
    """Create a mock for asyncio.create_subprocess_exec."""
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), b""))
    proc.returncode = returncode
    return proc


# -- is_available() -----------------------------------------------------------


async def test_is_available_npx_missing():
    provider = ContextHubProvider()
    with patch("volnix.kernel.context_hub.shutil.which", return_value=None):
        assert await provider.is_available() is False


async def test_is_available_npx_found():
    provider = ContextHubProvider()
    with patch("volnix.kernel.context_hub.shutil.which", return_value="/usr/local/bin/npx"):
        assert await provider.is_available() is True


# -- supports() ---------------------------------------------------------------


async def test_supports_found():
    provider = ContextHubProvider()
    proc = _mock_subprocess(_TWILIO_SEARCH_OUTPUT)
    with patch("volnix.kernel.context_hub.shutil.which", return_value="/usr/local/bin/npx"):
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            assert await provider.supports("twilio") is True


async def test_supports_not_found():
    provider = ContextHubProvider()
    proc = _mock_subprocess(_EMPTY_SEARCH_OUTPUT, returncode=0)
    with patch("volnix.kernel.context_hub.shutil.which", return_value="/usr/local/bin/npx"):
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            assert await provider.supports("totally_unknown_xyz") is False


async def test_supports_npx_missing():
    provider = ContextHubProvider()
    with patch("volnix.kernel.context_hub.shutil.which", return_value=None):
        assert await provider.supports("twilio") is False


# -- fetch() ------------------------------------------------------------------


async def test_fetch_success():
    """Two-step: search finds twilio/messaging, get returns docs."""
    provider = ContextHubProvider()
    search_proc = _mock_subprocess(_TWILIO_SEARCH_OUTPUT)
    get_proc = _mock_subprocess(_TWILIO_DOC_CONTENT)

    call_count = 0

    async def mock_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # First call is search, second is get
        if call_count == 1:
            return search_proc
        return get_proc

    with patch("volnix.kernel.context_hub.shutil.which", return_value="/usr/local/bin/npx"):
        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            result = await provider.fetch("twilio")

    assert result is not None
    assert result["source"] == "context_hub"
    assert result["service"] == "twilio"
    assert result["content_id"] == "twilio/package"  # /package preferred over /messaging
    assert result["lang"] == "py"
    assert "Twilio Python Library" in result["raw_content"]
    assert result["content_type"] == "markdown"


async def test_fetch_not_found():
    provider = ContextHubProvider()
    proc = _mock_subprocess(_EMPTY_SEARCH_OUTPUT)
    with patch("volnix.kernel.context_hub.shutil.which", return_value="/usr/local/bin/npx"):
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            result = await provider.fetch("totally_unknown_xyz")
    assert result is None


async def test_fetch_npx_missing():
    provider = ContextHubProvider()
    with patch("volnix.kernel.context_hub.shutil.which", return_value=None):
        result = await provider.fetch("twilio")
    assert result is None


async def test_fetch_timeout():
    provider = ContextHubProvider(timeout=0.001)
    with patch("volnix.kernel.context_hub.shutil.which", return_value="/usr/local/bin/npx"):
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=asyncio.TimeoutError,
        ):
            result = await provider.fetch("twilio")
    assert result is None


# -- _parse_search_results() --------------------------------------------------


def test_parse_search_results_twilio():
    results = ContextHubProvider._parse_search_results(_TWILIO_SEARCH_OUTPUT)
    assert len(results) == 3
    assert results[0] == ("twilio/package", ["py"])
    assert results[1] == ("twilio/messaging", ["py", "ts"])
    assert results[2] == ("sendgrid/package", ["py"])


def test_parse_search_results_stripe():
    results = ContextHubProvider._parse_search_results(_STRIPE_SEARCH_OUTPUT)
    assert len(results) == 2
    assert results[0] == ("stripe/api", ["js"])
    assert results[1] == ("stripe/payments", ["js"])


def test_parse_search_results_empty():
    results = ContextHubProvider._parse_search_results(_EMPTY_SEARCH_OUTPUT)
    assert results == []


# -- _pick_best_match() -------------------------------------------------------


def test_pick_best_match_prefers_api():
    results = [
        ("stripe/payments", ["js"]),
        ("stripe/api", ["js"]),
    ]
    match = ContextHubProvider._pick_best_match(results, "stripe")
    assert match == ("stripe/api", "js")


def test_pick_best_match_prefers_package():
    results = [
        ("twilio/messaging", ["py", "ts"]),
        ("twilio/package", ["py"]),
    ]
    match = ContextHubProvider._pick_best_match(results, "twilio")
    assert match == ("twilio/package", "py")


def test_pick_best_match_prefers_py():
    results = [("notion/workspace-api", ["js", "py"])]
    match = ContextHubProvider._pick_best_match(results, "notion")
    assert match is not None
    assert match[1] == "py"


def test_pick_best_match_falls_back_to_first_lang():
    results = [("stripe/api", ["js"])]
    match = ContextHubProvider._pick_best_match(results, "stripe")
    assert match == ("stripe/api", "js")


def test_pick_best_match_no_match():
    results = [("sendgrid/package", ["py"])]
    match = ContextHubProvider._pick_best_match(results, "twilio")
    assert match is None


# -- search cache --------------------------------------------------------------


async def test_search_cache():
    """Second supports() call uses cache, no new subprocess."""
    provider = ContextHubProvider()
    proc = _mock_subprocess(_TWILIO_SEARCH_OUTPUT)
    call_count = 0

    async def mock_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return proc

    with patch("volnix.kernel.context_hub.shutil.which", return_value="/usr/local/bin/npx"):
        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            await provider.supports("twilio")
            await provider.supports("twilio")

    assert call_count == 1  # Only one subprocess call despite two supports() calls


# -- protocol compliance -------------------------------------------------------


async def test_protocol_compliance():
    """ContextHubProvider satisfies the ExternalSpecProvider protocol."""
    provider = ContextHubProvider()
    assert isinstance(provider, ExternalSpecProvider)
    assert provider.provider_name == "context_hub"
