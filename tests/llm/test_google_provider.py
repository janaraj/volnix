"""Tests for terrarium.llm.providers.google -- Google Gemini provider."""

import os

import pytest

from terrarium.llm.providers.google import GoogleNativeProvider
from terrarium.llm.types import LLMRequest

GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY")
skipif_no_google = pytest.mark.skipif(
    not GOOGLE_KEY, reason="GOOGLE_API_KEY not set"
)

# Toggle: TERRARIUM_RUN_REAL_API_TESTS=1 to enable expensive real API tests
RUN_REAL = os.environ.get("TERRARIUM_RUN_REAL_API_TESTS", "").lower() in ("1", "true", "yes")
skipif_no_real = pytest.mark.skipif(not RUN_REAL, reason="TERRARIUM_RUN_REAL_API_TESTS not enabled")


def test_google_provider_init():
    """GoogleNativeProvider initialises with api_key and default_model."""
    provider = GoogleNativeProvider(api_key="test-key", default_model="gemini-3-flash-preview")
    assert provider._default_model == "gemini-3-flash-preview"
    assert provider.provider_name == "google"


def test_google_provider_get_info():
    """get_info returns correct Google metadata."""
    provider = GoogleNativeProvider(api_key="test-key")
    info = provider.get_info()
    assert info.type == "google"
    assert info.name == "google"
    assert info.base_url == "https://generativelanguage.googleapis.com"
    assert "gemini-3-flash-preview" in info.available_models


def test_google_provider_list_models():
    """list_models returns the expected static model list."""
    import asyncio

    provider = GoogleNativeProvider(api_key="test-key")
    models = asyncio.get_event_loop().run_until_complete(provider.list_models())
    assert "gemini-3-flash-preview" in models
    assert len(models) >= 3


@pytest.mark.asyncio
async def test_google_provider_error_handling():
    """Provider returns an error response on invalid key."""
    provider = GoogleNativeProvider(api_key="bad-key")
    req = LLMRequest(user_content="test")
    resp = await provider.generate(req)
    assert resp.error is not None
    assert resp.content == ""
    assert resp.provider == "google"
    assert resp.latency_ms >= 0


@skipif_no_google
@skipif_no_real
@pytest.mark.asyncio
async def test_google_real_generate():
    """Real Google API call -- enable with TERRARIUM_RUN_REAL_API_TESTS=1."""
    provider = GoogleNativeProvider(api_key=GOOGLE_KEY)
    resp = await provider.generate(
        LLMRequest(
            system_prompt="Reply with exactly the word 'terrarium'",
            user_content="What word?",
            max_tokens=50,
        )
    )
    assert resp.error is None
    assert "terrarium" in resp.content.lower()
