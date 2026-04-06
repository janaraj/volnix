"""Tests for volnix.llm.providers.mock -- deterministic mock LLM provider."""

import pytest

from volnix.llm.providers.mock import MockLLMProvider
from volnix.llm.types import LLMRequest


@pytest.mark.asyncio
async def test_mock_provider_deterministic():
    """Same input yields the same output across calls."""
    provider = MockLLMProvider(seed=42)
    req = LLMRequest(user_content="hello world")
    r1 = await provider.generate(req)
    r2 = await provider.generate(req)
    assert r1.content == r2.content
    assert r1.content != ""


@pytest.mark.asyncio
async def test_mock_provider_seed_changes_output():
    """Different seeds produce different responses."""
    req = LLMRequest(user_content="hello world")
    r1 = await MockLLMProvider(seed=1).generate(req)
    r2 = await MockLLMProvider(seed=2).generate(req)
    assert r1.content != r2.content


@pytest.mark.asyncio
async def test_mock_provider_custom_responses():
    """Custom response mapping returns the configured value."""
    provider = MockLLMProvider(responses={"greet": "Hi there!"})
    req = LLMRequest(user_content="greet")
    resp = await provider.generate(req)
    assert resp.content == "Hi there!"


@pytest.mark.asyncio
async def test_mock_provider_validate_connection():
    """Mock provider always validates successfully."""
    provider = MockLLMProvider()
    assert await provider.validate_connection() is True


@pytest.mark.asyncio
async def test_mock_provider_list_models():
    """Mock provider lists two mock models."""
    provider = MockLLMProvider()
    models = await provider.list_models()
    assert "mock-model-1" in models
    assert "mock-model-2" in models


@pytest.mark.asyncio
async def test_mock_provider_usage_tracking():
    """Mock provider returns realistic usage estimates based on content length."""
    provider = MockLLMProvider()
    req = LLMRequest(system_prompt="Be concise.", user_content="Explain AI")
    resp = await provider.generate(req)
    assert resp.usage.prompt_tokens > 0
    assert resp.usage.completion_tokens > 0
    assert resp.usage.total_tokens == resp.usage.prompt_tokens + resp.usage.completion_tokens
    assert resp.provider == "mock"
    assert resp.model == "mock-model-1"
