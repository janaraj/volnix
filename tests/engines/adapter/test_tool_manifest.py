"""Tests for volnix.engines.adapter.tool_manifest -- manifest generation."""
import pytest
from unittest.mock import MagicMock

from volnix.engines.adapter.tool_manifest import ToolManifestGenerator


def _make_pack_registry():
    """Create a mock PackRegistry with email pack."""
    registry = MagicMock()

    mock_pack = MagicMock()
    mock_pack.pack_name = "gmail"
    mock_pack.category = "communication"
    mock_pack.fidelity_tier = 1
    mock_pack.get_tools.return_value = [
        {"name": "email_send", "description": "Send an email",
         "http_path": "/email/v1/messages/send", "http_method": "POST",
         "parameters": {"type": "object", "properties": {
             "to": {"type": "string"}}, "required": ["to"]}},
        {"name": "email_read", "description": "Read an email",
         "http_path": "/email/v1/messages/{id}", "http_method": "GET",
         "parameters": {"type": "object", "properties": {
             "email_id": {"type": "string"}}, "required": ["email_id"]}},
    ]
    mock_pack.get_entity_schemas.return_value = {}
    mock_pack.get_state_machines.return_value = {}

    registry.list_packs.return_value = [
        {"pack_name": "email"},
    ]
    registry.get_pack.return_value = mock_pack

    return registry


def test_generate_mcp_manifest():
    """Generate MCP tool manifest from PackRegistry."""
    registry = _make_pack_registry()
    gen = ToolManifestGenerator(registry)

    tools = gen.generate(protocol="mcp")

    assert len(tools) == 2
    names = [t["name"] for t in tools]
    assert "email_send" in names
    assert "email_read" in names
    for t in tools:
        assert "inputSchema" in t
        assert "description" in t


def test_generate_http_manifest():
    """Generate HTTP route manifest from PackRegistry."""
    registry = _make_pack_registry()
    gen = ToolManifestGenerator(registry)

    routes = gen.generate(protocol="http")

    assert len(routes) == 2
    paths = [r["path"] for r in routes]
    assert "/email/v1/messages/send" in paths


def test_generate_openai_manifest():
    """Generate OpenAI function manifest from PackRegistry."""
    registry = _make_pack_registry()
    gen = ToolManifestGenerator(registry)

    tools = gen.generate(protocol="openai")

    assert len(tools) == 2
    for t in tools:
        assert t["type"] == "function"
        assert "function" in t
        assert "name" in t["function"]


def test_generate_anthropic_manifest():
    """Generate Anthropic tool manifest from PackRegistry."""
    registry = _make_pack_registry()
    gen = ToolManifestGenerator(registry)

    tools = gen.generate(protocol="anthropic")

    assert len(tools) == 2
    for t in tools:
        assert "name" in t
        assert "input_schema" in t


@pytest.mark.asyncio
async def test_filter_by_permissions_passthrough():
    """Phase E1: filter_by_permissions returns all tools unfiltered."""
    registry = _make_pack_registry()
    gen = ToolManifestGenerator(registry)

    tools = [{"name": "t1"}, {"name": "t2"}]
    filtered = await gen.filter_by_permissions("actor-1", tools)
    assert filtered == tools


def test_generate_empty_registry():
    """Empty registry returns empty list."""
    registry = MagicMock()
    registry.list_packs.return_value = []
    gen = ToolManifestGenerator(registry)

    assert gen.generate(protocol="mcp") == []
