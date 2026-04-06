"""Shared fixtures for world compiler D4a tests."""

import json
from unittest.mock import AsyncMock

import pytest

from volnix.kernel.registry import SemanticRegistry
from volnix.kernel.surface import ServiceSurface
from volnix.llm.types import LLMResponse
from volnix.packs.registry import PackRegistry
from volnix.packs.verified.gmail.pack import EmailPack
from volnix.reality.expander import ConditionExpander


@pytest.fixture
async def kernel():
    """Initialized SemanticRegistry."""
    reg = SemanticRegistry()
    await reg.initialize()
    return reg


@pytest.fixture
def pack_registry():
    """PackRegistry with email pack registered."""
    reg = PackRegistry()
    reg.register(EmailPack())
    return reg


@pytest.fixture
def mock_llm_router():
    """AsyncMock LLM router that returns valid world definition JSON."""
    router = AsyncMock()
    router.route = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(
                {
                    "world": {
                        "name": "Test",
                        "description": "test world",
                        "services": {"gmail": "verified/gmail"},
                        "actors": [{"role": "agent", "type": "external", "count": 1}],
                        "policies": [],
                        "seeds": [],
                        "mission": "",
                    }
                }
            ),
            provider="mock",
            model="mock",
            latency_ms=0,
        )
    )
    return router


@pytest.fixture
def condition_expander():
    """Fresh ConditionExpander."""
    return ConditionExpander()


@pytest.fixture
def sample_world_def():
    """Minimal world definition dict."""
    return {
        "world": {
            "name": "Test World",
            "description": "A test",
            "services": {"gmail": "verified/gmail"},
            "actors": [{"role": "agent", "type": "external", "count": 1}],
        }
    }


@pytest.fixture
def sample_compiler_settings():
    """Compiler settings dict with messy preset."""
    return {
        "compiler": {
            "seed": 42,
            "behavior": "dynamic",
            "fidelity": "auto",
            "mode": "governed",
            "reality": {"preset": "messy"},
        }
    }


@pytest.fixture
def email_surface():
    """ServiceSurface built from EmailPack."""
    return ServiceSurface.from_pack(EmailPack())
