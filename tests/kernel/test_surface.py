"""Tests for volnix.kernel.surface -- APIOperation + ServiceSurface models."""

import pytest
from volnix.kernel.surface import APIOperation, ServiceSurface


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _stripe_refund_op() -> APIOperation:
    """A realistic Stripe refund operation for reuse across tests."""
    return APIOperation(
        name="stripe_refunds_create",
        service="stripe",
        description="Create a refund for a charge",
        http_method="POST",
        http_path="/v1/refunds",
        parameters={
            "charge": {"type": "string", "description": "Charge ID to refund"},
            "amount": {"type": "integer", "description": "Amount in cents"},
        },
        required_params=["charge"],
        content_type="application/json",
        response_schema={
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "status": {"type": "string"},
                "amount": {"type": "integer"},
            },
        },
        creates_entity="refund",
        mutates_entity="charge",
        side_effects=["webhook:refund.created"],
    )


def _stripe_balance_op() -> APIOperation:
    """A Stripe balance retrieval (read-only) operation."""
    return APIOperation(
        name="stripe_balance_retrieve",
        service="stripe",
        description="Retrieve the current balance",
        http_method="GET",
        http_path="/v1/balance",
        parameters={},
        required_params=[],
        response_schema={
            "type": "object",
            "properties": {"available": {"type": "array"}},
        },
        is_read_only=True,
    )


def _full_surface() -> ServiceSurface:
    """A complete, valid ServiceSurface with two operations."""
    return ServiceSurface(
        service_name="stripe",
        category="money_transactions",
        source="tier1_pack",
        fidelity_tier=1,
        operations=[_stripe_refund_op(), _stripe_balance_op()],
        entity_schemas={
            "refund": {"type": "object", "properties": {"id": {"type": "string"}}},
            "charge": {"type": "object", "properties": {"id": {"type": "string"}}},
        },
        state_machines={"refund": {"pending": ["succeeded", "failed"]}},
        confidence=1.0,
        auth_pattern="bearer",
        base_url="https://api.stripe.com",
    )


# ---------------------------------------------------------------------------
# APIOperation tests
# ---------------------------------------------------------------------------

def test_api_operation_creation():
    """APIOperation stores all fields correctly."""
    op = _stripe_refund_op()
    assert op.name == "stripe_refunds_create"
    assert op.service == "stripe"
    assert op.http_method == "POST"
    assert op.http_path == "/v1/refunds"
    assert "charge" in op.parameters
    assert op.required_params == ["charge"]
    assert op.creates_entity == "refund"
    assert op.mutates_entity == "charge"
    assert op.side_effects == ["webhook:refund.created"]
    assert op.is_read_only is False


def test_to_mcp_tool():
    """to_mcp_tool produces {name, description, inputSchema}."""
    mcp = _stripe_refund_op().to_mcp_tool()
    assert mcp["name"] == "stripe_refunds_create"
    assert mcp["description"] == "Create a refund for a charge"
    assert mcp["inputSchema"]["type"] == "object"
    assert "charge" in mcp["inputSchema"]["properties"]
    assert mcp["inputSchema"]["required"] == ["charge"]


def test_to_http_route():
    """to_http_route produces {method, path, content_type}."""
    route = _stripe_refund_op().to_http_route()
    assert route["method"] == "POST"
    assert route["path"] == "/v1/refunds"
    assert route["content_type"] == "application/json"


def test_to_openai_function():
    """to_openai_function produces OpenAI function format with type:function wrapper."""
    result = _stripe_refund_op().to_openai_function()
    # FIX-20: Verify protocol compliance -- must have type:"function" wrapper
    assert result["type"] == "function"
    assert "function" in result
    fn = result["function"]
    assert fn["name"] == "stripe_refunds_create"
    assert fn["description"] == "Create a refund for a charge"
    assert fn["parameters"]["type"] == "object"
    assert "charge" in fn["parameters"]["properties"]
    assert fn["parameters"]["required"] == ["charge"]


def test_to_anthropic_tool():
    """to_anthropic_tool produces Anthropic tool use format."""
    tool = _stripe_refund_op().to_anthropic_tool()
    assert tool["name"] == "stripe_refunds_create"
    assert tool["description"] == "Create a refund for a charge"
    assert tool["input_schema"]["type"] == "object"
    assert "charge" in tool["input_schema"]["properties"]
    assert tool["input_schema"]["required"] == ["charge"]


# ---------------------------------------------------------------------------
# ServiceSurface tests
# ---------------------------------------------------------------------------

def test_service_surface_get_mcp_tools():
    """get_mcp_tools returns a list of MCP tool dicts for all operations."""
    surface = _full_surface()
    tools = surface.get_mcp_tools()
    assert len(tools) == 2
    names = {t["name"] for t in tools}
    assert names == {"stripe_refunds_create", "stripe_balance_retrieve"}
    for tool in tools:
        assert "inputSchema" in tool


def test_service_surface_get_http_routes():
    """get_http_routes returns HTTP route dicts for ops with http_path."""
    surface = _full_surface()
    routes = surface.get_http_routes()
    assert len(routes) == 2
    methods = {r["method"] for r in routes}
    assert "POST" in methods
    assert "GET" in methods


def test_get_operation_by_name():
    """get_operation retrieves an operation by name, None for missing."""
    surface = _full_surface()
    op = surface.get_operation("stripe_refunds_create")
    assert op is not None
    assert op.name == "stripe_refunds_create"

    missing = surface.get_operation("nonexistent")
    assert missing is None


def test_validate_surface_complete():
    """A complete surface produces no validation errors."""
    surface = _full_surface()
    errors = surface.validate_surface()
    assert errors == []


def test_validate_surface_missing_ops():
    """An empty-operations surface reports an error."""
    surface = ServiceSurface(
        service_name="empty",
        category="communication",
        source="test",
        fidelity_tier=1,
        operations=[],
        entity_schemas={"msg": {"type": "object"}},
    )
    errors = surface.validate_surface()
    assert any("no operations" in e for e in errors)


def test_validate_surface_missing_response():
    """An operation without response_schema is flagged."""
    op = APIOperation(
        name="test_op",
        service="test",
        description="A test",
        parameters={"x": {"type": "string"}},
        required_params=["x"],
        response_schema={},  # empty -- should be flagged
    )
    surface = ServiceSurface(
        service_name="test",
        category="communication",
        source="test",
        fidelity_tier=1,
        operations=[op],
        entity_schemas={"entity": {"type": "object"}},
    )
    errors = surface.validate_surface()
    assert any("response_schema" in e for e in errors)


def test_stripe_refund_e2e():
    """Full Stripe refund: one operation produces both MCP and HTTP views."""
    op = _stripe_refund_op()

    # MCP representation
    mcp = op.to_mcp_tool()
    assert mcp["name"] == "stripe_refunds_create"
    assert mcp["inputSchema"]["required"] == ["charge"]

    # HTTP representation
    http = op.to_http_route()
    assert http["method"] == "POST"
    assert http["path"] == "/v1/refunds"

    # Both come from the same operation
    assert mcp["name"] == op.name
    assert http["path"] == op.http_path
