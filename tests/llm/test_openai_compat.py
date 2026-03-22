"""Tests for terrarium.llm.providers.openai_compat -- OpenAI-compatible provider."""

import os

import pytest

from terrarium.llm.providers.openai_compat import OpenAICompatibleProvider
from terrarium.llm.types import LLMRequest

OPENAI_KEY = os.environ.get("OPENAI_API_KEY")
skipif_no_openai = pytest.mark.skipif(
    not OPENAI_KEY, reason="OPENAI_API_KEY not set"
)

# Toggle: TERRARIUM_RUN_REAL_API_TESTS=1 to enable expensive real API tests
RUN_REAL = os.environ.get("TERRARIUM_RUN_REAL_API_TESTS", "").lower() in ("1", "true", "yes")
skipif_no_real = pytest.mark.skipif(not RUN_REAL, reason="TERRARIUM_RUN_REAL_API_TESTS not enabled")


def test_openai_compat_init():
    """OpenAICompatibleProvider initialises with key, base_url, model."""
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        default_model="gpt-5.4-mini",
    )
    assert provider._default_model == "gpt-5.4-mini"
    assert provider._base_url == "https://api.openai.com/v1"
    assert provider.provider_name == "openai_compatible"


def test_openai_compat_custom_base_url():
    """Provider accepts a custom base_url for Ollama / vLLM / etc."""
    provider = OpenAICompatibleProvider(
        api_key=None,
        base_url="http://localhost:11434/v1",
        default_model="llama3.2",
    )
    assert provider._base_url == "http://localhost:11434/v1"
    info = provider.get_info()
    assert info.base_url == "http://localhost:11434/v1"
    assert info.type == "openai_compatible"


def test_openai_compat_no_api_key_for_ollama():
    """Provider works without an API key (e.g. local Ollama)."""
    provider = OpenAICompatibleProvider(
        api_key=None,
        base_url="http://localhost:11434/v1",
    )
    # Should not raise -- "local-no-auth-needed" is used as placeholder
    assert provider is not None


@skipif_no_openai
@pytest.mark.asyncio
async def test_openai_compat_generate_real():
    """Integration: send a real request to OpenAI (skipped without key)."""
    provider = OpenAICompatibleProvider(
        api_key=OPENAI_KEY,
        base_url="https://api.openai.com/v1",
    )
    req = LLMRequest(user_content="Say 'pong'", max_tokens=16)
    resp = await provider.generate(req)
    assert resp.content
    assert resp.provider == "openai_compatible"


@pytest.mark.asyncio
async def test_openai_compat_error_handling():
    """Provider returns an error response on connection failure."""
    provider = OpenAICompatibleProvider(
        api_key="bad-key",
        base_url="http://127.0.0.1:1/v1",
    )
    req = LLMRequest(user_content="test")
    resp = await provider.generate(req)
    assert resp.error is not None
    assert resp.content == ""
    assert resp.provider == "openai_compatible"
    assert resp.latency_ms >= 0


@skipif_no_openai
@skipif_no_real
@pytest.mark.asyncio
async def test_openai_real_generate():
    """Real OpenAI API call -- enable with TERRARIUM_RUN_REAL_API_TESTS=1."""
    provider = OpenAICompatibleProvider(
        api_key=OPENAI_KEY,
        base_url="https://api.openai.com/v1",
    )
    resp = await provider.generate(
        LLMRequest(
            system_prompt="Reply with exactly the word 'terrarium'",
            user_content="What word?",
            max_tokens=50,
        )
    )
    assert resp.error is None
    assert "terrarium" in resp.content.lower()
