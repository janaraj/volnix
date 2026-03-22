"""Tests for terrarium.kernel.resolver -- ServiceResolver resolution chain."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from terrarium.kernel.registry import SemanticRegistry
from terrarium.kernel.resolver import ServiceResolver
from terrarium.kernel.surface import APIOperation, ServiceSurface


@pytest.fixture
async def kernel():
    """Create and initialize a SemanticRegistry."""
    reg = SemanticRegistry()
    await reg.initialize()
    return reg


def _make_mock_provider(
    name: str = "mock_provider",
    available: bool = True,
    supports_service: bool = True,
    spec: dict | None = None,
):
    """Build a mock ExternalSpecProvider."""
    provider = MagicMock()
    provider.provider_name = name
    provider.is_available = AsyncMock(return_value=available)
    provider.supports = AsyncMock(return_value=supports_service)
    provider.fetch = AsyncMock(return_value=spec)
    return provider


def _sample_spec() -> dict:
    """A sample parsed spec dict (like what OpenAPIProvider.fetch returns)."""
    return {
        "source": "openapi",
        "service": "stripe",
        "title": "Stripe API",
        "version": "1.0",
        "operations": [
            {
                "name": "stripe_charges_create",
                "description": "Create a charge",
                "http_method": "POST",
                "http_path": "/v1/charges",
                "parameters": {"amount": {"type": "integer"}, "currency": {"type": "string"}},
                "response_schema": {"type": "object", "properties": {"id": {"type": "string"}}},
            },
        ],
        "raw_content": "/specs/stripe.yaml",
    }


async def test_resolve_via_provider(kernel):
    """When a provider returns a spec, resolve returns a ServiceSurface."""
    provider = _make_mock_provider(spec=_sample_spec())
    resolver = ServiceResolver(kernel, providers=[provider])

    surface = await resolver.resolve("stripe")

    assert surface is not None
    assert isinstance(surface, ServiceSurface)
    assert surface.service_name == "stripe"
    assert len(surface.operations) == 1
    assert surface.operations[0].name == "stripe_charges_create"
    provider.fetch.assert_awaited_once()


async def test_resolve_falls_to_kernel(kernel):
    """When all providers fail, resolver falls back to kernel classification."""
    provider = _make_mock_provider(supports_service=False)
    resolver = ServiceResolver(kernel, providers=[provider])

    surface = await resolver.resolve("stripe")

    assert surface is not None
    assert surface.source == "kernel_inference"
    assert surface.category == "money_transactions"
    assert surface.confidence == pytest.approx(0.1)


async def test_resolve_unknown(kernel):
    """Completely unknown service with no providers returns None."""
    resolver = ServiceResolver(kernel, providers=[])

    surface = await resolver.resolve("totally_unknown_service_xyz")

    assert surface is None


async def test_resolution_order(kernel):
    """First provider in the list is tried first; second is not called if first succeeds."""
    first = _make_mock_provider(name="first", spec=_sample_spec())
    second = _make_mock_provider(name="second", spec=_sample_spec())
    resolver = ServiceResolver(kernel, providers=[first, second])

    surface = await resolver.resolve("stripe")

    assert surface is not None
    first.fetch.assert_awaited_once()
    second.fetch.assert_not_awaited()


async def test_confidence_levels(kernel):
    """Source determines confidence: context_hub=0.7, openapi=0.5, kernel=0.1."""
    # context_hub provider
    chub_spec = _sample_spec()
    chub_spec["source"] = "context_hub"
    chub_provider = _make_mock_provider(name="context_hub", spec=chub_spec)
    resolver_chub = ServiceResolver(kernel, providers=[chub_provider])
    surface_chub = await resolver_chub.resolve("stripe")
    assert surface_chub.confidence == pytest.approx(0.7)

    # openapi provider
    oapi_spec = _sample_spec()
    oapi_spec["source"] = "openapi"
    oapi_provider = _make_mock_provider(name="openapi", spec=oapi_spec)
    resolver_oapi = ServiceResolver(kernel, providers=[oapi_provider])
    surface_oapi = await resolver_oapi.resolve("stripe")
    assert surface_oapi.confidence == pytest.approx(0.5)

    # kernel fallback (no providers)
    resolver_kernel = ServiceResolver(kernel, providers=[])
    surface_kernel = await resolver_kernel.resolve("stripe")
    assert surface_kernel.confidence == pytest.approx(0.1)


async def test_surface_from_spec(kernel):
    """Parsed operations in spec are converted to APIOperation objects."""
    provider = _make_mock_provider(spec=_sample_spec())
    resolver = ServiceResolver(kernel, providers=[provider])

    surface = await resolver.resolve("stripe")

    assert len(surface.operations) == 1
    op = surface.operations[0]
    assert isinstance(op, APIOperation)
    assert op.http_method == "POST"
    assert op.http_path == "/v1/charges"
    assert "amount" in op.parameters


async def test_no_providers(kernel):
    """With no providers, resolver falls to kernel for known services."""
    resolver = ServiceResolver(kernel, providers=[])

    surface = await resolver.resolve("slack")

    assert surface is not None
    assert surface.source == "kernel_inference"
    assert surface.category == "communication"
    assert surface.confidence == pytest.approx(0.1)


async def test_llm_callback(kernel):
    """LLM callback is invoked when all providers fail (for known services)."""
    # Provider that doesn't support the service
    provider = _make_mock_provider(supports_service=False)

    # LLM callback that returns a surface
    llm_surface = ServiceSurface(
        service_name="stripe",
        category="money_transactions",
        source="llm_inference",
        fidelity_tier=2,
        operations=[],
        confidence=0.4,
    )
    llm_callback = AsyncMock(return_value=llm_surface)

    resolver = ServiceResolver(kernel, providers=[provider], llm_infer=llm_callback)
    surface = await resolver.resolve("stripe")

    assert surface is not None
    assert surface.source == "llm_inference"
    llm_callback.assert_awaited_once()
    # Verify callback received service name, category, primitives
    call_args = llm_callback.call_args
    assert call_args[0][0] == "stripe"
    assert call_args[0][1] == "money_transactions"
    assert isinstance(call_args[0][2], list)
