"""Comprehensive CLI test suite for Terrarium.

Tests all 20 CLI commands using Typer's CliRunner.
Commands that require the full app context are tested with mocked app_context.
Commands that are self-contained (help, deferred, check) are tested directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from terrarium.cli import app

runner = CliRunner()


# ===================================================================
# All CLI command names (20 total)
# ===================================================================

ALL_COMMANDS = [
    "create",
    "init",
    "plan",
    "run",
    "serve",
    "report",
    "diff",
    "inspect",
    "list",
    "show",
    "snapshot",
    "replay",
    "setup",
    "check",
    "ledger",
    "capture",
    "compile-pack",
    "verify-pack",
    "promote",
    "annotate",
]


# ===================================================================
# Help & Basic Tests
# ===================================================================


class TestHelpAndBasics:
    """Tests for --help output and basic CLI structure."""

    def test_help_shows_all_commands(self):
        """terrarium --help lists all 20 commands."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for cmd in ALL_COMMANDS:
            assert cmd in result.output, f"Command '{cmd}' missing from help output"

    @pytest.mark.parametrize("command", ALL_COMMANDS)
    def test_each_command_has_help(self, command: str):
        """Every command responds to --help without error."""
        result = runner.invoke(app, [command, "--help"])
        assert result.exit_code == 0
        # Every help output should show something descriptive
        assert len(result.output) > 20, f"Help for '{command}' is suspiciously short"

    def test_no_args_shows_help(self):
        """Running terrarium with no args shows help (no_args_is_help=True)."""
        result = runner.invoke(app, [])
        # Typer uses exit code 0 or 2 for no_args_is_help depending on version
        assert result.exit_code in (0, 2)
        assert "Programmable worlds" in result.output

    def test_invalid_command_fails(self):
        """An unknown command produces an error."""
        result = runner.invoke(app, ["nonexistent-command"])
        assert result.exit_code != 0


# ===================================================================
# Deferred Commands (5 tests)
# ===================================================================


class TestFeedbackCommands:
    """Tests for the 5 feedback/promotion commands (G4a)."""

    def test_verify_pack_email(self):
        """verify-pack on existing email pack succeeds."""
        result = runner.invoke(app, ["verify-pack", "email"])
        assert result.exit_code == 0
        assert "passed all checks" in result.output

    def test_verify_pack_missing(self):
        """verify-pack on non-existent pack fails."""
        result = runner.invoke(app, ["verify-pack", "nonexistent_pack_xyz"])
        assert result.exit_code == 1

    def test_annotate_requires_message(self):
        """annotate without --message exits with error."""
        result = runner.invoke(app, ["annotate", "stripe"])
        assert result.exit_code == 1
        assert "required" in result.output.lower()

    def test_compile_pack_missing_source(self):
        """compile-pack with nonexistent source exits with error."""
        result = runner.invoke(app, ["compile-pack", "test", "/tmp/nonexistent_xyz.yaml"])
        assert result.exit_code == 1

    def test_capture_help(self):
        """capture --help shows usage."""
        result = runner.invoke(app, ["capture", "--help"])
        assert result.exit_code == 0
        assert "capture" in result.output.lower()

    def test_promote_help(self):
        """promote --help shows usage."""
        result = runner.invoke(app, ["promote", "--help"])
        assert result.exit_code == 0

    def test_annotate_help(self):
        """annotate --help shows usage."""
        result = runner.invoke(app, ["annotate", "--help"])
        assert result.exit_code == 0

    def test_compile_pack_help(self):
        """compile-pack --help shows usage."""
        result = runner.invoke(app, ["compile-pack", "--help"])
        assert result.exit_code == 0


# ===================================================================
# Check Command (3 tests)
# ===================================================================


class TestCheckCommand:
    """Tests for the 'check' command (system requirements check)."""

    def test_check_basic(self):
        """check exits 0 and shows system check output."""
        result = runner.invoke(app, ["check"])
        assert result.exit_code == 0
        assert "Terrarium System Check" in result.output

    def test_check_output_contains_python(self):
        """check output includes Python version info."""
        result = runner.invoke(app, ["check"])
        assert result.exit_code == 0
        assert "Python" in result.output

    def test_check_output_contains_providers(self):
        """check output includes LLM Providers section."""
        result = runner.invoke(app, ["check"])
        assert result.exit_code == 0
        assert "LLM Providers" in result.output

    def test_check_output_contains_packages(self):
        """check output shows required package status."""
        result = runner.invoke(app, ["check"])
        assert result.exit_code == 0
        # At minimum, pydantic and typer should be reported
        assert "pydantic" in result.output
        assert "typer" in result.output

    def test_check_output_contains_configuration(self):
        """check output includes a Configuration section."""
        result = runner.invoke(app, ["check"])
        assert result.exit_code == 0
        assert "Configuration" in result.output

    def test_check_help_shows_test_flag(self):
        """check --help mentions the --test flag."""
        result = runner.invoke(app, ["check", "--help"])
        assert result.exit_code == 0
        assert "--test" in result.output


# ===================================================================
# Helper: mock app context
# ===================================================================


def _make_mock_terrarium():
    """Build a mock TerrariumApp with common sub-mocks."""
    terrarium = AsyncMock()

    # Run manager
    terrarium.run_manager = AsyncMock()
    terrarium.run_manager.list_runs = AsyncMock(return_value=[])
    terrarium.run_manager.get_run = AsyncMock(return_value=None)

    # Artifact store
    terrarium.artifact_store = AsyncMock()
    terrarium.artifact_store.load_artifact = AsyncMock(return_value=None)
    terrarium.artifact_store.list_artifacts = AsyncMock(return_value=[])

    # Registry
    registry_engines = {
        "world_compiler": AsyncMock(),
        "state": AsyncMock(),
        "policy": AsyncMock(),
        "permission": AsyncMock(),
        "budget": AsyncMock(),
        "responder": AsyncMock(),
        "animator": AsyncMock(),
        "adapter": AsyncMock(),
        "reporter": AsyncMock(),
        "feedback": AsyncMock(),
    }
    terrarium.registry = MagicMock()
    terrarium.registry.get = MagicMock(side_effect=lambda name: registry_engines.get(name))
    terrarium.registry.list_engines = MagicMock(return_value=list(registry_engines.keys()))

    # Gateway
    terrarium.gateway = AsyncMock()
    terrarium.gateway.get_tool_manifest = AsyncMock(return_value=[])

    # Ledger
    terrarium.ledger = AsyncMock()
    terrarium.ledger.query = AsyncMock(return_value=[])

    # Health (public property)
    health_mock = AsyncMock()
    health_mock.check_all = AsyncMock(return_value={})
    health_mock.is_healthy = MagicMock(return_value=True)
    terrarium.health = health_mock

    # Actor registry (public property)
    terrarium.actor_registry = None

    return terrarium, registry_engines


def _patch_app_context(terrarium_mock):
    """Return a patch for cli_helpers.app_context that yields the mock."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _mock_app_context():
        yield terrarium_mock

    return patch("terrarium.cli.app_context", _mock_app_context)


# ===================================================================
# Create Command (3 tests)
# ===================================================================


class TestCreateCommand:
    """Tests for the 'create' command."""

    def test_create_generates_yaml(self, tmp_path: Path):
        """create writes a YAML file from a description."""
        terrarium, engines = _make_mock_terrarium()
        mock_plan = MagicMock()
        mock_plan.warnings = []
        mock_plan.model_dump = MagicMock(return_value={"world": "test"})
        engines["world_compiler"].compile_from_nl = AsyncMock(return_value=mock_plan)

        # PlanReviewer is imported inside the async function, so patch at source
        with _patch_app_context(terrarium), patch(
            "terrarium.engines.world_compiler.plan_reviewer.PlanReviewer"
        ) as MockReviewer:
            reviewer_instance = MagicMock()
            reviewer_instance.to_yaml = MagicMock(return_value="world:\n  name: test\n")
            reviewer_instance.format_plan = MagicMock(return_value="Test Plan")
            MockReviewer.return_value = reviewer_instance

            output_path = tmp_path / "world.yaml"
            result = runner.invoke(
                app,
                ["create", "A customer support world", "--output", str(output_path)],
            )
            assert result.exit_code == 0
            assert output_path.exists()
            assert "world" in output_path.read_text()

    def test_create_with_reality_option(self, tmp_path: Path):
        """create respects the --reality option."""
        terrarium, engines = _make_mock_terrarium()
        mock_plan = MagicMock()
        mock_plan.warnings = []
        engines["world_compiler"].compile_from_nl = AsyncMock(return_value=mock_plan)

        with _patch_app_context(terrarium), patch(
            "terrarium.engines.world_compiler.plan_reviewer.PlanReviewer"
        ) as MockReviewer:
            reviewer_instance = MagicMock()
            reviewer_instance.to_yaml = MagicMock(return_value="reality: hostile\n")
            reviewer_instance.format_plan = MagicMock(return_value="Hostile Plan")
            MockReviewer.return_value = reviewer_instance

            output_path = tmp_path / "hostile.yaml"
            result = runner.invoke(
                app,
                [
                    "create",
                    "A hostile world",
                    "--reality",
                    "hostile",
                    "--output",
                    str(output_path),
                ],
            )
            assert result.exit_code == 0
            # Verify compile_from_nl was called with reality=hostile
            call_kwargs = engines["world_compiler"].compile_from_nl.call_args
            assert call_kwargs.kwargs.get("reality") == "hostile" or (
                len(call_kwargs.args) > 1 and call_kwargs.args[1] == "hostile"
            )

    def test_create_output_path(self, tmp_path: Path):
        """create respects a custom --output path."""
        terrarium, engines = _make_mock_terrarium()
        mock_plan = MagicMock()
        mock_plan.warnings = []
        engines["world_compiler"].compile_from_nl = AsyncMock(return_value=mock_plan)

        with _patch_app_context(terrarium), patch(
            "terrarium.engines.world_compiler.plan_reviewer.PlanReviewer"
        ) as MockReviewer:
            reviewer_instance = MagicMock()
            reviewer_instance.to_yaml = MagicMock(return_value="custom: true\n")
            reviewer_instance.format_plan = MagicMock(return_value="Custom Plan")
            MockReviewer.return_value = reviewer_instance

            custom_dir = tmp_path / "subdir"
            custom_dir.mkdir()
            custom_path = custom_dir / "custom_world.yaml"
            result = runner.invoke(
                app,
                ["create", "My world", "--output", str(custom_path)],
            )
            assert result.exit_code == 0
            assert custom_path.exists()
            assert "custom" in custom_path.read_text()

    def test_create_handles_compiler_error(self):
        """create exits 1 when the compiler raises TerrariumError."""
        from terrarium.core.errors import TerrariumError

        terrarium, engines = _make_mock_terrarium()
        engines["world_compiler"].compile_from_nl = AsyncMock(
            side_effect=TerrariumError("Compilation failed")
        )

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["create", "broken world"])
            assert result.exit_code == 1
            assert "Error" in result.output


# ===================================================================
# List Command (4 tests)
# ===================================================================


class TestListCommand:
    """Tests for the 'list' command."""

    def test_list_runs_empty(self):
        """list runs shows empty table when no runs exist."""
        terrarium, _ = _make_mock_terrarium()
        terrarium.run_manager.list_runs = AsyncMock(return_value=[])

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["list", "runs"])
            assert result.exit_code == 0
            assert "Runs" in result.output

    def test_list_runs_with_data(self):
        """list runs shows run data when runs exist."""
        terrarium, _ = _make_mock_terrarium()
        terrarium.run_manager.list_runs = AsyncMock(
            return_value=[
                {
                    "run_id": "run-001",
                    "tag": "test",
                    "mode": "governed",
                    "status": "completed",
                    "created_at": "2026-01-01T00:00:00",
                },
            ]
        )

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["list", "runs"])
            assert result.exit_code == 0
            assert "run-001" in result.output

    def test_list_tools(self):
        """list tools shows tools table."""
        terrarium, engines = _make_mock_terrarium()
        mock_pack_registry = MagicMock()
        mock_pack_registry.list_tools = MagicMock(
            return_value=[
                {"name": f"tool_{i}", "pack_name": "email", "description": f"Tool {i}"}
                for i in range(95)
            ]
        )
        engines["responder"].pack_registry = mock_pack_registry

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["list", "tools"])
            assert result.exit_code == 0
            assert "Tools" in result.output
            assert "95" in result.output  # Shows count in title

    def test_list_services(self):
        """list services shows services table."""
        terrarium, engines = _make_mock_terrarium()
        mock_pack_registry = MagicMock()
        mock_pack_registry.list_packs = MagicMock(
            return_value=[
                {"pack_name": "email", "tool_count": 5, "tier": "1"},
                {"pack_name": "slack", "tool_count": 10, "tier": "2"},
            ]
        )
        engines["responder"].pack_registry = mock_pack_registry

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["list", "services"])
            assert result.exit_code == 0
            assert "Services" in result.output

    def test_list_engines(self):
        """list engines shows all registered engines."""
        terrarium, _ = _make_mock_terrarium()

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["list", "engines"])
            assert result.exit_code == 0
            assert "Engines" in result.output

    def test_list_invalid_resource(self):
        """list with unknown resource type exits with error."""
        terrarium, _ = _make_mock_terrarium()

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["list", "unicorns"])
            assert result.exit_code == 1
            assert "Unknown resource" in result.output

    def test_list_artifacts_requires_run_id(self):
        """list artifacts without --run exits with error."""
        terrarium, _ = _make_mock_terrarium()

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["list", "artifacts"])
            assert result.exit_code == 1
            assert "--run" in result.output

    def test_list_runs_json_format(self):
        """list runs --format json produces JSON output."""
        terrarium, _ = _make_mock_terrarium()
        terrarium.run_manager.list_runs = AsyncMock(return_value=[])

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["list", "runs", "--format", "json"])
            assert result.exit_code == 0


# ===================================================================
# Report/Diff Commands (3 tests)
# ===================================================================


class TestReportDiffCommands:
    """Tests for the 'report' and 'diff' commands."""

    def test_report_no_run(self):
        """report exits with error when the run doesn't exist."""
        terrarium, _ = _make_mock_terrarium()
        terrarium.run_manager.get_run = AsyncMock(return_value=None)

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["report", "nonexistent-run"])
            assert result.exit_code == 1
            assert "not found" in result.output.lower() or "Error" in result.output

    def test_report_with_existing_run(self):
        """report shows report data when run exists."""
        terrarium, engines = _make_mock_terrarium()
        terrarium.run_manager.get_run = AsyncMock(
            return_value={"run_id": "run-001", "tag": "test"}
        )
        terrarium.artifact_store.load_artifact = AsyncMock(
            side_effect=lambda rid, atype: (
                {"summary": "All clear"} if atype == "report" else {"score": 95}
            )
        )

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["report", "run-001"])
            assert result.exit_code == 0

    def test_diff_insufficient_runs(self):
        """diff exits with error when fewer than 2 runs given."""
        # diff requires at least 2 positional arguments
        # Typer will parse single arg as a list of 1
        terrarium, _ = _make_mock_terrarium()

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["diff", "only-one-run"])
            assert result.exit_code == 1
            assert "2" in result.output or "error" in result.output.lower()

    def test_diff_help(self):
        """diff --help shows options."""
        result = runner.invoke(app, ["diff", "--help"])
        assert result.exit_code == 0
        assert "--format" in result.output
        assert "--gov-vs-ungov" in result.output

    def test_diff_with_two_runs(self):
        """diff with two run IDs calls diff_runs."""
        terrarium, _ = _make_mock_terrarium()
        terrarium.diff_runs = AsyncMock(
            return_value={"differences": [], "summary": "No differences"}
        )

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["diff", "run-001", "run-002"])
            assert result.exit_code == 0


# ===================================================================
# Inspect Command (3 tests)
# ===================================================================


class TestInspectCommand:
    """Tests for the 'inspect' command."""

    def test_inspect_entities_without_type(self):
        """inspect entities without --type shows guidance."""
        terrarium, _ = _make_mock_terrarium()

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["inspect", "entities"])
            assert result.exit_code == 0
            assert "type" in result.output.lower()

    def test_inspect_help(self):
        """inspect --help shows all flags."""
        result = runner.invoke(app, ["inspect", "--help"])
        assert result.exit_code == 0
        assert "--type" in result.output
        assert "--actor" in result.output
        assert "--format" in result.output

    def test_inspect_unknown_resource(self):
        """inspect with unknown resource exits with error."""
        terrarium, _ = _make_mock_terrarium()

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["inspect", "galaxies"])
            assert result.exit_code == 1
            assert "Unknown resource" in result.output

    def test_inspect_entities_with_type(self):
        """inspect entities --type email returns entity table."""
        terrarium, engines = _make_mock_terrarium()
        state_engine = engines["state"]
        state_engine.query_entities = AsyncMock(
            return_value=[
                {"id": "e1", "type": "email", "subject": "Hello"},
            ]
        )

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["inspect", "entities", "--type", "email"])
            assert result.exit_code == 0

    def test_inspect_policies(self):
        """inspect policies shows policy list."""
        terrarium, engines = _make_mock_terrarium()
        from terrarium.core.types import PolicyId
        engines["policy"].get_active_policies = AsyncMock(
            return_value=[PolicyId("budget_check"), PolicyId("rate_limit")]
        )

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["inspect", "policies"])
            assert result.exit_code == 0

    def test_inspect_services(self):
        """inspect services shows service packs."""
        terrarium, engines = _make_mock_terrarium()
        # Use a plain MagicMock for responder to avoid AsyncMock coroutine issues
        responder = MagicMock()
        mock_pack_registry = MagicMock()
        mock_pack_registry.list_packs = MagicMock(
            return_value=[{"pack_name": "email", "tool_count": 5}]
        )
        responder.pack_registry = mock_pack_registry
        engines["responder"] = responder
        # Update registry.get to return the plain MagicMock for responder
        original_get = terrarium.registry.get.side_effect

        def patched_get(name):
            if name == "responder":
                return responder
            return original_get(name)

        terrarium.registry.get = MagicMock(side_effect=patched_get)

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["inspect", "services"])
            assert result.exit_code == 0
            assert "Services" in result.output


# ===================================================================
# Setup Command (2 tests)
# ===================================================================


class TestSetupCommand:
    """Tests for the 'setup' command."""

    def test_setup_help(self):
        """setup --help shows provider list."""
        result = runner.invoke(app, ["setup", "--help"])
        assert result.exit_code == 0
        assert "anthropic" in result.output
        assert "openai" in result.output
        assert "google" in result.output

    def test_setup_invalid_provider(self):
        """setup with unknown provider exits with error."""
        result = runner.invoke(app, ["setup", "nonexistent-provider"])
        assert result.exit_code == 1
        assert "Unknown provider" in result.output

    def test_setup_all_providers(self):
        """setup 'all' exits 0 and shows Setup complete."""
        result = runner.invoke(app, ["setup", "all"])
        assert result.exit_code == 0
        assert "Setup complete" in result.output

    def test_setup_single_provider(self):
        """setup with a valid provider name exits 0."""
        result = runner.invoke(app, ["setup", "google"])
        assert result.exit_code == 0
        assert "GOOGLE" in result.output


# ===================================================================
# Show Command (3 tests)
# ===================================================================


class TestShowCommand:
    """Tests for the 'show' command."""

    def test_show_unknown_resource_type(self):
        """show with unknown resource type exits with error."""
        terrarium, _ = _make_mock_terrarium()

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["show", "unknown_thing", "some-id"])
            assert result.exit_code == 1
            assert "Unknown resource" in result.output

    def test_show_run_not_found(self):
        """show run with nonexistent ID exits with error."""
        terrarium, _ = _make_mock_terrarium()
        terrarium.run_manager.get_run = AsyncMock(return_value=None)

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["show", "run", "nonexistent"])
            assert result.exit_code == 1
            assert "not found" in result.output.lower()

    def test_show_run_found(self):
        """show run with existing ID displays details."""
        terrarium, _ = _make_mock_terrarium()
        terrarium.run_manager.get_run = AsyncMock(
            return_value={
                "run_id": "run-001",
                "tag": "test",
                "mode": "governed",
                "status": "completed",
            }
        )

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["show", "run", "run-001"])
            assert result.exit_code == 0
            assert "run-001" in result.output

    def test_show_help(self):
        """show --help shows resource options."""
        result = runner.invoke(app, ["show", "--help"])
        assert result.exit_code == 0
        assert "run" in result.output
        assert "tool" in result.output
        assert "service" in result.output


# ===================================================================
# Snapshot/Replay (2 tests)
# ===================================================================


class TestSnapshotReplayCommands:
    """Tests for the 'snapshot' and 'replay' commands."""

    def test_snapshot_help(self):
        """snapshot --help shows options."""
        result = runner.invoke(app, ["snapshot", "--help"])
        assert result.exit_code == 0
        assert "label" in result.output.lower()

    def test_replay_help(self):
        """replay --help shows options."""
        result = runner.invoke(app, ["replay", "--help"])
        assert result.exit_code == 0
        assert "--tag" in result.output

    def test_snapshot_creates(self):
        """snapshot with a label creates a snapshot."""
        terrarium, engines = _make_mock_terrarium()
        engines["state"].snapshot = AsyncMock(return_value="snap-abc123")

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["snapshot", "my-snapshot"])
            assert result.exit_code == 0
            assert "snap-abc123" in result.output

    def test_replay_nonexistent_run(self):
        """replay with a nonexistent run ID exits with error."""
        terrarium, _ = _make_mock_terrarium()
        terrarium.run_manager.get_run = AsyncMock(return_value=None)

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["replay", "nonexistent-run"])
            assert result.exit_code == 1
            assert "not found" in result.output.lower()


# ===================================================================
# Ledger (2 tests)
# ===================================================================


class TestLedgerCommand:
    """Tests for the 'ledger' command."""

    def test_ledger_help(self):
        """ledger --help shows filter options."""
        result = runner.invoke(app, ["ledger", "--help"])
        assert result.exit_code == 0
        assert "--type" in result.output
        assert "--actor" in result.output
        assert "--engine" in result.output
        assert "--tail" in result.output

    def test_ledger_basic(self):
        """ledger runs without crash and shows table."""
        terrarium, _ = _make_mock_terrarium()
        terrarium.ledger.query = AsyncMock(return_value=[])

        with _patch_app_context(terrarium), patch(
            "terrarium.ledger.query.LedgerQueryBuilder"
        ) as MockBuilder:
            builder_instance = MagicMock()
            builder_instance.limit = MagicMock(return_value=builder_instance)
            builder_instance.filter_type = MagicMock(return_value=builder_instance)
            builder_instance.filter_actor = MagicMock(return_value=builder_instance)
            builder_instance.filter_engine = MagicMock(return_value=builder_instance)
            builder_instance.build = MagicMock(return_value="mock_query")
            MockBuilder.return_value = builder_instance

            result = runner.invoke(app, ["ledger"])
            assert result.exit_code == 0
            assert "Ledger" in result.output

    def test_ledger_with_entries(self):
        """ledger shows formatted entries when data exists."""
        terrarium, _ = _make_mock_terrarium()
        mock_entries = [
            {
                "entry_id": "entry-001",
                "entry_type": "pipeline_step",
                "timestamp": "2026-01-01T00:00:00",
                "actor_id": "actor-test",
                "details": "Permission check passed",
            }
        ]
        terrarium.ledger.query = AsyncMock(return_value=mock_entries)

        with _patch_app_context(terrarium), patch(
            "terrarium.ledger.query.LedgerQueryBuilder"
        ) as MockBuilder:
            builder_instance = MagicMock()
            builder_instance.limit = MagicMock(return_value=builder_instance)
            builder_instance.build = MagicMock(return_value="mock_query")
            MockBuilder.return_value = builder_instance

            result = runner.invoke(app, ["ledger"])
            assert result.exit_code == 0


# ===================================================================
# Init Command (2 tests)
# ===================================================================


class TestInitCommand:
    """Tests for the 'init' command."""

    def test_init_help(self):
        """init --help shows options."""
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0
        assert "--settings" in result.output
        assert "--output" in result.output

    def test_init_with_yaml(self, tmp_path: Path):
        """init compiles a YAML file successfully."""
        terrarium, engines = _make_mock_terrarium()
        mock_plan = MagicMock()
        engines["world_compiler"].compile_from_yaml = AsyncMock(return_value=mock_plan)

        with _patch_app_context(terrarium), patch(
            "terrarium.engines.world_compiler.plan_reviewer.PlanReviewer"
        ) as MockReviewer:
            reviewer_instance = MagicMock()
            reviewer_instance.validate_plan = MagicMock(return_value=[])
            reviewer_instance.format_plan = MagicMock(return_value="Compiled Plan")
            MockReviewer.return_value = reviewer_instance

            result = runner.invoke(app, ["init", "world.yaml"])
            assert result.exit_code == 0
            assert "Compiling" in result.output


# ===================================================================
# Plan Command (2 tests)
# ===================================================================


class TestPlanCommand:
    """Tests for the 'plan' command."""

    def test_plan_help(self):
        """plan --help shows options."""
        result = runner.invoke(app, ["plan", "--help"])
        assert result.exit_code == 0
        assert "--output" in result.output
        assert "--format" in result.output

    def test_plan_from_description(self):
        """plan generates a plan from a description."""
        terrarium, engines = _make_mock_terrarium()
        mock_plan = MagicMock()
        mock_plan.model_dump = MagicMock(return_value={"world": "test"})
        engines["world_compiler"].compile_from_nl = AsyncMock(return_value=mock_plan)

        with _patch_app_context(terrarium), patch(
            "terrarium.engines.world_compiler.plan_reviewer.PlanReviewer"
        ) as MockReviewer:
            reviewer_instance = MagicMock()
            reviewer_instance.format_plan = MagicMock(return_value="World Plan Output")
            MockReviewer.return_value = reviewer_instance

            result = runner.invoke(app, ["plan", "A world with email and slack"])
            assert result.exit_code == 0


# ===================================================================
# Run Command (2 tests)
# ===================================================================


class TestRunCommand:
    """Tests for the 'run' command."""

    def test_run_help(self):
        """run --help shows all options."""
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--agent" in result.output
        assert "--actor" in result.output
        assert "--mode" in result.output
        assert "--tag" in result.output
        assert "--serve" in result.output
        assert "--behavior" in result.output

    def test_run_nonexistent_world(self):
        """run exits with error for a missing world file (non-YAML string)."""
        terrarium, engines = _make_mock_terrarium()
        from terrarium.core.errors import TerrariumError

        engines["world_compiler"].compile_from_nl = AsyncMock(
            side_effect=TerrariumError("Cannot compile: invalid description")
        )

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["run", "nonexistent_world.txt"])
            assert result.exit_code == 1


# ===================================================================
# Serve Command (2 tests)
# ===================================================================


class TestServeCommand:
    """Tests for the 'serve' command."""

    def test_serve_help(self):
        """serve --help shows options."""
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--host" in result.output
        assert "--port" in result.output
        assert "--settings" in result.output

    def test_serve_compilation_error(self):
        """serve exits with error when compilation fails."""
        from terrarium.core.errors import TerrariumError

        terrarium, engines = _make_mock_terrarium()
        engines["world_compiler"].compile_from_yaml = AsyncMock(
            side_effect=TerrariumError("Invalid world YAML")
        )

        with _patch_app_context(terrarium):
            result = runner.invoke(app, ["serve", "bad_world.yaml"])
            assert result.exit_code == 1


# ===================================================================
# Error Handling (3 tests)
# ===================================================================


class TestErrorHandling:
    """Tests for error handling edge cases."""

    def test_create_empty_description(self):
        """create handles empty description gracefully (Typer validates)."""
        # Typer requires the argument, so calling without it should fail
        result = runner.invoke(app, ["create"])
        assert result.exit_code != 0

    def test_diff_no_args(self):
        """diff with no arguments shows error or help."""
        result = runner.invoke(app, ["diff"])
        # Typer should complain about missing required argument
        assert result.exit_code != 0

    def test_show_missing_name_arg(self):
        """show without the name argument fails."""
        result = runner.invoke(app, ["show", "run"])
        # Missing required argument 'name'
        assert result.exit_code != 0


# ===================================================================
# CLI Helper Formatting Tests
# ===================================================================


class TestCLIHelpers:
    """Tests for cli_helpers.py formatting functions."""

    def test_format_run_table_empty(self):
        from terrarium.cli_helpers import format_run_table

        table = format_run_table([])
        assert table.title == "Runs"
        assert table.row_count == 0

    def test_format_run_table_with_data(self):
        from terrarium.cli_helpers import format_run_table

        runs = [
            {
                "run_id": "r1",
                "tag": "t1",
                "mode": "governed",
                "status": "completed",
                "created_at": "2026-01-01",
            }
        ]
        table = format_run_table(runs)
        assert table.row_count == 1

    def test_format_entity_table(self):
        from terrarium.cli_helpers import format_entity_table

        entities = [{"id": "e1", "name": "Test Entity"}]
        table = format_entity_table(entities, "test")
        assert table.title == "Entities: test"
        assert table.row_count == 1

    def test_format_ledger_table_empty(self):
        from terrarium.cli_helpers import format_ledger_table

        table = format_ledger_table([])
        assert table.title == "Ledger Entries"
        assert table.row_count == 0

    def test_format_scorecard(self):
        from terrarium.cli_helpers import format_scorecard

        scorecard = {
            "governance": {"compliance": 0.95, "total_actions": 42},
            "warnings": ["Low budget remaining"],
        }
        panel = format_scorecard(scorecard)
        assert panel.title == "Scorecard"

    def test_format_health_table(self):
        from terrarium.cli_helpers import format_health_table

        results = {
            "state": {"started": True, "healthy": True, "error": ""},
            "policy": {"started": True, "healthy": False, "error": "timeout"},
        }
        table = format_health_table(results)
        assert table.row_count == 2

    def test_format_event_line(self):
        from terrarium.cli_helpers import format_event_line

        event = {
            "timestamp": "2026-01-01T00:00:00.000Z",
            "event_type": "world.email_send",
            "actor_id": "actor-1",
            "action": "send_email",
        }
        line = format_event_line(event)
        assert "world.email_send" in line
        assert "actor-1" in line

    def test_format_diff_fallback(self):
        from terrarium.cli_helpers import format_diff

        comparison = {"changes": ["a", "b"]}
        output = format_diff(comparison)
        # format_diff delegates to RunComparator.format_comparison or JSON fallback
        # Either way it should return a non-empty string
        assert isinstance(output, str)
        assert len(output) > 0

    def test_write_output_to_file(self, tmp_path: Path):
        from terrarium.cli_helpers import write_output

        outfile = tmp_path / "output.txt"
        write_output("hello world", outfile)
        assert outfile.read_text() == "hello world"

    def test_write_output_to_stdout(self, capsys):
        from terrarium.cli_helpers import write_output

        # When output_path is None, prints to console
        write_output("hello stdout", None)
        # Rich console output goes through its own stream, but
        # the function should not raise
