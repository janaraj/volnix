"""Tests for config export templates."""
from __future__ import annotations

import json

from volnix.cli_exports.templates import (
    EXPORT_REGISTRY,
    claude_desktop,
    cursor,
    env_vars,
    mcp_raw,
    openai_tools,
    python_sdk,
    windsurf,
)


def test_registry_has_all_targets():
    """Export registry has 13 targets."""
    assert len(EXPORT_REGISTRY) == 13


def test_claude_desktop_valid_json():
    """claude-desktop export produces valid JSON with mcpServers."""
    output = claude_desktop(url="http://localhost:8080", tools=[])
    config = json.loads(output)
    assert "mcpServers" in config
    assert "volnix" in config["mcpServers"]
    assert "/mcp" in config["mcpServers"]["volnix"]["url"]


def test_cursor_valid_json():
    """cursor export produces valid JSON."""
    output = cursor(url="http://localhost:8080", tools=[])
    config = json.loads(output)
    assert "mcpServers" in config


def test_windsurf_valid_json():
    """windsurf export produces valid JSON."""
    output = windsurf(url="http://localhost:8080", tools=[])
    config = json.loads(output)
    assert "mcpServers" in config


def test_openai_tools_format():
    """openai-tools export returns tool list as JSON."""
    tools = [{"type": "function", "function": {"name": "test"}}]
    output = openai_tools(url="http://localhost:8080", tools=tools)
    parsed = json.loads(output)
    assert len(parsed) == 1
    assert parsed[0]["type"] == "function"


def test_env_vars_format():
    """env-vars export produces shell export statements."""
    tools = [{"name": "email_send"}, {"name": "tickets.update"}]
    output = env_vars(url="http://localhost:8080", tools=tools)
    assert "export VOLNIX_URL=http://localhost:8080" in output
    assert "export VOLNIX_MCP_URL=" in output


def test_python_sdk_snippet():
    """python-sdk export contains VolnixClient usage."""
    output = python_sdk(url="http://localhost:8080", tools=[])
    assert "VolnixClient" in output
    assert "localhost:8080" in output


def test_anthropic_tools_format():
    """anthropic-tools export returns tool list as JSON."""
    from volnix.cli_exports.templates import anthropic_tools

    tools = [{"name": "test", "input_schema": {}}]
    output = anthropic_tools(url="http://localhost:8080", tools=tools)
    parsed = json.loads(output)
    assert len(parsed) == 1


def test_docker_compose_uses_port():
    """M3: docker-compose uses the port from url."""
    from volnix.cli_exports.templates import docker_compose

    output = docker_compose(url="http://localhost:9090", tools=[])
    assert "9090" in output


def test_empty_tools_list():
    """Export with empty tool list doesn't crash."""
    output = openai_tools(url="http://localhost:8080", tools=[])
    assert json.loads(output) == []


def test_mcp_raw_has_url():
    """mcp-raw export has connection URL."""
    output = mcp_raw(url="http://localhost:8080", tools=[])
    config = json.loads(output)
    assert "/mcp" in config["url"]
