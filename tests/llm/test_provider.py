"""Tests for terrarium.llm.provider -- abstract LLM provider interface."""

import pytest

from terrarium.llm.provider import LLMProvider
from terrarium.llm.types import LLMRequest, LLMResponse, LLMUsage, ProviderInfo


def test_llm_provider_abc():
    """LLMProvider cannot be instantiated directly (it is abstract)."""
    with pytest.raises(TypeError):
        LLMProvider()


def test_provider_generate_signature():
    """LLMProvider.generate is abstract and requires a request parameter."""
    assert hasattr(LLMProvider, "generate")
    # Verify generate is abstract
    assert getattr(LLMProvider.generate, "__isabstractmethod__", False)


async def test_provider_validate_connection_default():
    """Default validate_connection returns True."""

    class MinimalProvider(LLMProvider):
        async def generate(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse()

    provider = MinimalProvider()
    assert await provider.validate_connection() is True


def test_provider_class_var_and_info():
    """LLMProvider has a class-level provider_name and get_info returns ProviderInfo."""

    class TestProvider(LLMProvider):
        provider_name = "test_prov"

        async def generate(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse()

    p = TestProvider()
    assert p.provider_name == "test_prov"
    info = p.get_info()
    assert isinstance(info, ProviderInfo)
    assert info.name == "test_prov"
    assert info.type == "test_prov"
