"""Tests for ProfileInferrer -- draft profile generation for unknown services.

Covers:
- Infer with no external sources (LLM only)
- Infer with Context Hub docs
- Infer with kernel classification
- Output validation (result is valid ServiceProfileData)
- Confidence scoring based on sources
- YAML parsing robustness
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import yaml

from volnix.llm.types import LLMResponse
from volnix.packs.profile_infer import (
    _CONFIDENCE_HUB,
    _CONFIDENCE_KERNEL,
    _CONFIDENCE_LLM_ONLY,
    _CONFIDENCE_OPENAPI,
    ProfileInferrer,
)
from volnix.packs.profile_schema import ServiceProfileData

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_yaml_response(data: dict) -> str:
    """Convert a dict to YAML string as LLM would return."""
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


def _make_llm_response(content: str) -> LLMResponse:
    """Create a mock LLM response with the given content."""
    return LLMResponse(
        content=content,
        provider="mock",
        model="mock-model",
        latency_ms=50.0,
    )


def _make_mock_router(response_content: str) -> AsyncMock:
    """Create a mock LLM router that returns canned YAML content."""
    router = AsyncMock()
    router.route = AsyncMock(return_value=_make_llm_response(response_content))
    return router


def _minimal_profile_yaml(service_name: str = "acme") -> dict:
    """Return a minimal valid profile structure."""
    return {
        "profile_name": service_name,
        "service_name": service_name,
        "category": "testing",
        "operations": [
            {
                "name": f"{service_name}_create_widget",
                "service": service_name,
                "description": "Create a widget",
                "http_method": "POST",
                "http_path": "/api/widgets",
                "parameters": {"name": {"type": "string"}},
                "required_params": ["name"],
                "response_schema": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
                },
                "creates_entity": "widget",
            },
        ],
        "entities": [
            {
                "name": "widget",
                "identity_field": "id",
                "fields": {"id": {"type": "string"}, "name": {"type": "string"}},
                "required": ["id"],
            },
        ],
        "state_machines": [
            {
                "entity_type": "widget",
                "field": "status",
                "transitions": {"new": ["active"], "active": ["archived"]},
            },
        ],
        "error_modes": [
            {
                "code": "NOT_FOUND",
                "when": "Widget not found",
                "http_status": 404,
            },
        ],
        "behavioral_notes": ["Widgets are always round"],
        "responder_prompt": f"You are simulating the {service_name} API.",
    }


# ---------------------------------------------------------------------------
# Tests: Infer with no sources
# ---------------------------------------------------------------------------


async def test_infer_with_no_sources():
    """LLM-only inference produces a valid ServiceProfileData."""
    profile_data = _minimal_profile_yaml("unknown_svc")
    yaml_content = _make_yaml_response(profile_data)
    router = _make_mock_router(yaml_content)

    inferrer = ProfileInferrer(llm_router=router)

    result = await inferrer.infer("unknown_svc")

    assert isinstance(result, ServiceProfileData)
    assert result.service_name == "unknown_svc"
    assert result.fidelity_source == "bootstrapped"
    assert result.confidence == _CONFIDENCE_LLM_ONLY
    assert len(result.operations) == 1
    assert result.operations[0].name == "unknown_svc_create_widget"

    # Verify LLM was called
    router.route.assert_awaited_once()
    call_args = router.route.call_args
    assert call_args.kwargs["engine_name"] == "profile_infer"


async def test_infer_with_no_sources_source_chain():
    """LLM-only inference records source chain."""
    profile_data = _minimal_profile_yaml("mysvc")
    yaml_content = _make_yaml_response(profile_data)
    router = _make_mock_router(yaml_content)

    inferrer = ProfileInferrer(llm_router=router)

    result = await inferrer.infer("mysvc")

    assert "llm_inference" in result.source_chain


# ---------------------------------------------------------------------------
# Tests: Infer with Context Hub
# ---------------------------------------------------------------------------


async def test_infer_with_context_hub():
    """Context Hub docs are fed to the LLM and confidence is higher."""
    profile_data = _minimal_profile_yaml("stripe")
    yaml_content = _make_yaml_response(profile_data)
    router = _make_mock_router(yaml_content)

    # Mock Context Hub
    context_hub = AsyncMock()
    context_hub.supports = AsyncMock(return_value=True)
    context_hub.fetch = AsyncMock(
        return_value={
            "source": "context_hub",
            "service": "stripe",
            "raw_content": "Stripe API documentation: charges, refunds, customers...",
        }
    )

    inferrer = ProfileInferrer(llm_router=router, context_hub=context_hub)

    result = await inferrer.infer("stripe")

    assert isinstance(result, ServiceProfileData)
    assert result.fidelity_source == "bootstrapped"
    assert result.confidence == _CONFIDENCE_HUB

    # Verify Context Hub was queried
    context_hub.supports.assert_awaited_once_with("stripe")
    context_hub.fetch.assert_awaited_once_with("stripe")

    # Verify hub content was included in the LLM prompt
    call_args = router.route.call_args
    request = call_args.args[0]
    assert "Stripe API documentation" in request.user_content

    # Source chain should include context_hub
    assert "context_hub" in result.source_chain


async def test_infer_context_hub_unavailable():
    """When Context Hub doesn't support the service, proceed without it."""
    profile_data = _minimal_profile_yaml("custom_svc")
    yaml_content = _make_yaml_response(profile_data)
    router = _make_mock_router(yaml_content)

    context_hub = AsyncMock()
    context_hub.supports = AsyncMock(return_value=False)

    inferrer = ProfileInferrer(llm_router=router, context_hub=context_hub)

    result = await inferrer.infer("custom_svc")

    assert isinstance(result, ServiceProfileData)
    assert result.confidence == _CONFIDENCE_LLM_ONLY
    context_hub.fetch.assert_not_awaited()


async def test_infer_context_hub_error_handled():
    """When Context Hub raises an error, continue gracefully."""
    profile_data = _minimal_profile_yaml("flaky_svc")
    yaml_content = _make_yaml_response(profile_data)
    router = _make_mock_router(yaml_content)

    context_hub = AsyncMock()
    context_hub.supports = AsyncMock(side_effect=RuntimeError("network error"))

    inferrer = ProfileInferrer(llm_router=router, context_hub=context_hub)

    result = await inferrer.infer("flaky_svc")

    assert isinstance(result, ServiceProfileData)
    assert result.confidence == _CONFIDENCE_LLM_ONLY


# ---------------------------------------------------------------------------
# Tests: Infer with OpenAPI
# ---------------------------------------------------------------------------


async def test_infer_with_openapi():
    """OpenAPI spec feeds operations into the LLM prompt."""
    profile_data = _minimal_profile_yaml("petstore")
    yaml_content = _make_yaml_response(profile_data)
    router = _make_mock_router(yaml_content)

    openapi = AsyncMock()
    openapi.supports = AsyncMock(return_value=True)
    openapi.fetch = AsyncMock(
        return_value={
            "source": "openapi",
            "service": "petstore",
            "operations": [
                {
                    "name": "listPets",
                    "http_method": "GET",
                    "http_path": "/pets",
                    "description": "List all pets",
                },
                {
                    "name": "createPet",
                    "http_method": "POST",
                    "http_path": "/pets",
                    "description": "Create a pet",
                },
            ],
        }
    )

    inferrer = ProfileInferrer(llm_router=router, openapi_provider=openapi)

    result = await inferrer.infer("petstore")

    assert isinstance(result, ServiceProfileData)
    assert result.confidence == _CONFIDENCE_OPENAPI

    # Verify OpenAPI operations were in the prompt
    call_args = router.route.call_args
    request = call_args.args[0]
    assert "listPets" in request.user_content
    assert "createPet" in request.user_content


# ---------------------------------------------------------------------------
# Tests: Infer with Kernel classification
# ---------------------------------------------------------------------------


async def test_infer_with_kernel():
    """Kernel classification provides category and primitives."""
    profile_data = _minimal_profile_yaml("custom_email")
    profile_data["category"] = "communication"
    yaml_content = _make_yaml_response(profile_data)
    router = _make_mock_router(yaml_content)

    kernel = MagicMock()
    kernel.get_category = MagicMock(return_value="communication")
    kernel.get_primitives = MagicMock(
        return_value=[
            {"name": "send_message", "description": "Send a message to a recipient"},
            {"name": "receive_message", "description": "Receive messages"},
        ]
    )

    inferrer = ProfileInferrer(llm_router=router, kernel=kernel)

    result = await inferrer.infer("custom_email")

    assert isinstance(result, ServiceProfileData)
    assert result.confidence == _CONFIDENCE_KERNEL

    # Verify kernel was queried
    kernel.get_category.assert_called_once_with("custom_email")
    kernel.get_primitives.assert_called_once_with("communication")

    # Verify primitives were in the prompt
    call_args = router.route.call_args
    request = call_args.args[0]
    assert "send_message" in request.user_content

    # Source chain should include kernel
    assert any("kernel:" in s for s in result.source_chain)


# ---------------------------------------------------------------------------
# Tests: Output validation
# ---------------------------------------------------------------------------


async def test_infer_returns_valid_profile():
    """Inferred profile is a valid ServiceProfileData with all expected fields."""
    profile_data = _minimal_profile_yaml("validated_svc")
    yaml_content = _make_yaml_response(profile_data)
    router = _make_mock_router(yaml_content)

    inferrer = ProfileInferrer(llm_router=router)

    result = await inferrer.infer("validated_svc")

    # Type check
    assert isinstance(result, ServiceProfileData)

    # Required fields
    assert result.profile_name == "validated_svc"
    assert result.service_name == "validated_svc"
    assert result.category == "testing"
    assert result.fidelity_source == "bootstrapped"
    assert result.version == "0.1.0"  # default for inferred

    # Operations
    assert len(result.operations) >= 1
    for op in result.operations:
        assert op.name
        assert op.service

    # Entities
    assert len(result.entities) >= 1
    for ent in result.entities:
        assert ent.name

    # State machines
    assert len(result.state_machines) >= 1

    # Error modes
    assert len(result.error_modes) >= 1

    # Behavioral notes
    assert len(result.behavioral_notes) >= 1

    # Responder prompt
    assert result.responder_prompt


async def test_infer_malformed_yaml_fallback():
    """When LLM returns unparseable content, raise ValueError."""
    router = _make_mock_router("This is not YAML at all, just random text!!!")

    inferrer = ProfileInferrer(llm_router=router)

    import pytest

    with pytest.raises(ValueError, match="Could not parse valid YAML"):
        await inferrer.infer("broken_svc")


async def test_infer_yaml_with_markdown_wrapper():
    """LLM output wrapped in markdown code blocks is handled."""
    profile_data = _minimal_profile_yaml("markdown_svc")
    yaml_str = yaml.dump(profile_data, default_flow_style=False)
    wrapped = f"```yaml\n{yaml_str}\n```"
    router = _make_mock_router(wrapped)

    inferrer = ProfileInferrer(llm_router=router)

    result = await inferrer.infer("markdown_svc")

    assert isinstance(result, ServiceProfileData)
    assert result.service_name == "markdown_svc"
    assert len(result.operations) >= 1


# ---------------------------------------------------------------------------
# Tests: Confidence scoring
# ---------------------------------------------------------------------------


async def test_confidence_ordering():
    """Confidence scores follow expected ordering: hub > openapi > kernel > llm_only."""
    assert _CONFIDENCE_HUB > _CONFIDENCE_OPENAPI
    assert _CONFIDENCE_OPENAPI > _CONFIDENCE_KERNEL
    assert _CONFIDENCE_KERNEL > _CONFIDENCE_LLM_ONLY


async def test_infer_confidence_with_multiple_sources():
    """With multiple sources, highest-confidence source wins."""
    profile_data = _minimal_profile_yaml("multi_svc")
    yaml_content = _make_yaml_response(profile_data)
    router = _make_mock_router(yaml_content)

    # Both Context Hub and Kernel available
    context_hub = AsyncMock()
    context_hub.supports = AsyncMock(return_value=True)
    context_hub.fetch = AsyncMock(return_value={"source": "context_hub", "raw_content": "API docs"})

    kernel = MagicMock()
    kernel.get_category = MagicMock(return_value="testing")
    kernel.get_primitives = MagicMock(return_value=[])

    inferrer = ProfileInferrer(llm_router=router, context_hub=context_hub, kernel=kernel)

    result = await inferrer.infer("multi_svc")

    # Context Hub confidence wins (highest)
    assert result.confidence == _CONFIDENCE_HUB


# ---------------------------------------------------------------------------
# Tests: Partial/malformed LLM output
# ---------------------------------------------------------------------------


async def test_infer_partial_operations():
    """Malformed operations in LLM output are skipped, valid ones kept."""
    profile_data = {
        "profile_name": "partial",
        "service_name": "partial",
        "category": "testing",
        "operations": [
            {  # Valid
                "name": "partial_valid_op",
                "service": "partial",
                "description": "A valid operation",
            },
            "not_a_dict",  # Invalid -- should be skipped
        ],
        "entities": [
            {
                "name": "widget",
                "identity_field": "id",
                "fields": {"id": {"type": "string"}},
            },
        ],
        "responder_prompt": "You simulate partial.",
    }
    yaml_content = _make_yaml_response(profile_data)
    router = _make_mock_router(yaml_content)

    inferrer = ProfileInferrer(llm_router=router)

    result = await inferrer.infer("partial")

    assert isinstance(result, ServiceProfileData)
    assert len(result.operations) == 1
    assert result.operations[0].name == "partial_valid_op"
