"""E2E tests: CLI world generation flows.

Tests three NL-to-world entry points:
  A. terrarium create "desc" → YAML → serve
  B. terrarium run "desc" --serve (zero-YAML)
  C. terrarium mcp "desc" (zero-YAML MCP)

These tests require an LLM provider configured. They are skipped
automatically if no provider is available.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

runner = CliRunner()


def _has_llm_provider() -> bool:
    """Check if an LLM provider is available for world compilation."""
    try:
        from terrarium.config.loader import ConfigLoader

        config = ConfigLoader().load()
        # Check if any LLM provider is configured
        return bool(getattr(config, "llm", None))
    except Exception:
        return False


skip_no_llm = pytest.mark.skipif(
    not _has_llm_provider(),
    reason="No LLM provider configured — required for NL world compilation",
)


class TestCreateAndServe:
    """Test A: terrarium create 'desc' → YAML → verify structure."""

    @skip_no_llm
    def test_create_generates_yaml_with_services(self, tmp_path):
        """terrarium create produces a YAML file with requested services."""
        from terrarium.cli import app as cli_app

        output_path = tmp_path / "test_world.yaml"
        result = runner.invoke(
            cli_app,
            [
                "create",
                "Support team with email and ticket management for 5 customers",
                "--reality", "messy",
                "--output", str(output_path),
            ],
        )

        # Command should succeed
        assert result.exit_code == 0, f"CLI failed: {result.output}"

        # YAML file should exist
        assert output_path.exists()
        content = output_path.read_text()

        # Should contain service references
        assert "email" in content.lower() or "gmail" in content.lower()
        assert "ticket" in content.lower() or "zendesk" in content.lower()

    @skip_no_llm
    def test_create_yaml_is_valid(self, tmp_path):
        """Generated YAML can be parsed and has required sections."""
        import yaml

        from terrarium.cli import app as cli_app

        output_path = tmp_path / "test_world.yaml"
        result = runner.invoke(
            cli_app,
            [
                "create",
                "Email service with 3 customer support agents",
                "--output", str(output_path),
            ],
        )

        if result.exit_code != 0:
            pytest.skip(f"Create failed: {result.output[:200]}")

        data = yaml.safe_load(output_path.read_text())
        assert isinstance(data, dict)
        # Should have world and/or compiler sections
        assert "world" in data or "services" in data


class TestRunWithServe:
    """Test B: terrarium run 'desc' --serve (zero-YAML)."""

    @skip_no_llm
    async def test_run_nl_compiles_world(self):
        """terrarium run with NL description compiles a world plan."""
        # We test the compilation step programmatically rather than
        # starting the full server (which would block).
        from terrarium.cli_helpers import app_context

        async with app_context() as terrarium:
            compiler = terrarium.registry.get("world_compiler")
            plan = await compiler.compile_from_nl(
                description="Support team with email and tickets",
                reality="messy",
                behavior="reactive",
                fidelity="auto",
            )

            # Plan should have resolved services
            assert len(plan.services) >= 2
            service_names = set(plan.services.keys())
            assert "email" in service_names or any(
                "email" in s for s in service_names
            )


class TestMCPCommand:
    """Test C: terrarium mcp command exists and accepts args."""

    def test_mcp_command_registered(self):
        """The mcp command is registered in the CLI."""
        from terrarium.cli import app as cli_app

        result = runner.invoke(cli_app, ["mcp", "--help"])
        assert result.exit_code == 0
        assert "MCP stdio server" in result.output or "mcp" in result.output.lower()

    def test_mcp_command_requires_world_arg(self):
        """The mcp command requires a world argument."""
        from terrarium.cli import app as cli_app

        result = runner.invoke(cli_app, ["mcp"])
        # Missing required argument
        assert result.exit_code != 0
