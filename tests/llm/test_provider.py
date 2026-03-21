"""Tests for terrarium.llm.provider — abstract LLM provider interface."""
import pytest
import pytest_asyncio
from terrarium.llm.provider import LLMProvider


def test_llm_provider_abc():
    ...


def test_provider_generate_signature():
    ...


@pytest.mark.asyncio
async def test_provider_validate_connection():
    ...
