"""Architectural validation tests -- enforce quality gates for service pack promotion.

These tests verify that the ServiceSurface model correctly validates
completeness, ensuring every promoted service has both MCP and HTTP
representations, response schemas, and entity definitions.
"""

import pytest
from volnix.kernel.surface import APIOperation, ServiceSurface


def _email_operations() -> list[APIOperation]:
    """Build APIOperations mirroring the EmailPack's tool surface."""
    return [
        APIOperation(
            name="email_send",
            service="email",
            description="Send an email message.",
            http_method="POST",
            http_path="/v1/emails/send",
            parameters={
                "from_addr": {"type": "string"},
                "to_addr": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            required_params=["from_addr", "to_addr", "subject", "body"],
            response_schema={
                "type": "object",
                "properties": {
                    "email_id": {"type": "string"},
                    "status": {"type": "string"},
                },
            },
            creates_entity="email",
        ),
        APIOperation(
            name="email_list",
            service="email",
            description="List emails in a mailbox.",
            http_method="GET",
            http_path="/v1/emails",
            parameters={
                "mailbox_owner": {"type": "string"},
                "status_filter": {"type": "string"},
                "limit": {"type": "integer"},
            },
            required_params=["mailbox_owner"],
            response_schema={
                "type": "array",
                "items": {"type": "object"},
            },
            is_read_only=True,
        ),
        APIOperation(
            name="email_read",
            service="email",
            description="Read a specific email by ID.",
            http_method="GET",
            http_path="/v1/emails/{email_id}",
            parameters={"email_id": {"type": "string"}},
            required_params=["email_id"],
            response_schema={
                "type": "object",
                "properties": {
                    "email_id": {"type": "string"},
                    "from_addr": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
            is_read_only=True,
        ),
        APIOperation(
            name="email_search",
            service="email",
            description="Search emails by query, sender, or subject.",
            http_method="GET",
            http_path="/v1/emails/search",
            parameters={
                "query": {"type": "string"},
                "sender": {"type": "string"},
                "subject": {"type": "string"},
            },
            required_params=[],
            response_schema={
                "type": "array",
                "items": {"type": "object"},
            },
            is_read_only=True,
        ),
        APIOperation(
            name="email_reply",
            service="email",
            description="Reply to an existing email.",
            http_method="POST",
            http_path="/v1/emails/{email_id}/reply",
            parameters={
                "email_id": {"type": "string"},
                "from_addr": {"type": "string"},
                "body": {"type": "string"},
            },
            required_params=["email_id", "from_addr", "body"],
            response_schema={
                "type": "object",
                "properties": {
                    "email_id": {"type": "string"},
                    "status": {"type": "string"},
                },
            },
            creates_entity="email",
        ),
        APIOperation(
            name="email_mark_read",
            service="email",
            description="Mark one or more emails as read.",
            http_method="PATCH",
            http_path="/v1/emails/mark-read",
            parameters={
                "email_ids": {"type": "array", "items": {"type": "string"}},
            },
            required_params=["email_ids"],
            response_schema={
                "type": "object",
                "properties": {"updated_count": {"type": "integer"}},
            },
            mutates_entity="email",
        ),
    ]


def _email_surface() -> ServiceSurface:
    """A complete email ServiceSurface suitable for promotion."""
    return ServiceSurface(
        service_name="email",
        category="communication",
        source="tier1_pack",
        fidelity_tier=1,
        operations=_email_operations(),
        entity_schemas={
            "email": {
                "type": "object",
                "properties": {
                    "email_id": {"type": "string"},
                    "from_addr": {"type": "string"},
                    "to_addr": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "status": {"type": "string"},
                },
            },
            "mailbox": {
                "type": "object",
                "properties": {
                    "mailbox_id": {"type": "string"},
                    "owner": {"type": "string"},
                },
            },
            "thread": {
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string"},
                    "subject": {"type": "string"},
                },
            },
        },
        state_machines={
            "email": {
                "transitions": {
                    "draft": ["sent"],
                    "sent": ["delivered"],
                    "delivered": ["read", "archived"],
                    "read": ["archived", "trashed"],
                },
            },
        },
        confidence=1.0,
    )


def test_validate_catches_incomplete():
    """An empty surface is flagged with validation errors."""
    surface = ServiceSurface(
        service_name="empty",
        category="communication",
        source="test",
        fidelity_tier=1,
        operations=[],
        entity_schemas={},
    )
    errors = surface.validate_surface()
    assert len(errors) >= 2
    assert any("no operations" in e for e in errors)
    assert any("no entity_schemas" in e for e in errors)


def test_email_pack_valid_surface():
    """A fully-specified email surface passes validation with no errors."""
    surface = _email_surface()
    errors = surface.validate_surface()
    assert errors == [], f"Validation errors: {errors}"


def test_operations_have_both_protocols():
    """Every operation in the email surface produces both MCP and HTTP views."""
    surface = _email_surface()
    for op in surface.operations:
        mcp = op.to_mcp_tool()
        http = op.to_http_route()
        assert mcp["name"] == op.name, f"{op.name}: MCP name mismatch"
        assert "inputSchema" in mcp, f"{op.name}: MCP missing inputSchema"
        assert http["method"] in ("GET", "POST", "PUT", "PATCH", "DELETE"), (
            f"{op.name}: unexpected HTTP method {http['method']}"
        )
        assert http["path"], f"{op.name}: HTTP path is empty"


def test_operations_have_response_schemas():
    """All operations have a non-empty response_schema."""
    surface = _email_surface()
    for op in surface.operations:
        assert op.response_schema, f"{op.name}: missing response_schema"
        assert "type" in op.response_schema, f"{op.name}: response_schema has no 'type'"


def test_entity_schemas_present():
    """Surface has entity schemas and they are non-empty dicts."""
    surface = _email_surface()
    assert len(surface.entity_schemas) >= 1, "No entity schemas"
    for name, schema in surface.entity_schemas.items():
        assert isinstance(schema, dict), f"entity {name}: schema is not a dict"
        assert "type" in schema, f"entity {name}: schema missing 'type'"
