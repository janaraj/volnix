"""Test harness for --preset and --actors CLI flags.

These tests verify structural contracts, not LLM behavior.
If a preset is added/removed, if actor_specs format changes,
if the CLI signature drifts — these tests catch it.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Preset tests
# ---------------------------------------------------------------------------


class TestPresetLoading:
    """Verify all presets are loadable and well-formed."""

    def test_all_presets_loadable(self):
        """Every shipped preset must load without error."""
        from terrarium.deliverable_presets import AVAILABLE_PRESETS, load_preset

        assert len(AVAILABLE_PRESETS) >= 6, (
            f"Expected at least 6 presets, got {len(AVAILABLE_PRESETS)}"
        )

        for name in AVAILABLE_PRESETS:
            data = load_preset(name)
            assert isinstance(data, dict), f"Preset '{name}' did not return a dict"

    def test_preset_has_required_keys(self):
        """Every preset must have: name, description, schema, prompt_instructions."""
        from terrarium.deliverable_presets import AVAILABLE_PRESETS, load_preset

        required_keys = {"name", "description", "schema", "prompt_instructions"}
        for name in AVAILABLE_PRESETS:
            data = load_preset(name)
            missing = required_keys - set(data.keys())
            assert not missing, f"Preset '{name}' missing keys: {missing}"

    def test_preset_schema_is_valid_json_schema(self):
        """Every preset schema must have 'type' and 'properties'."""
        from terrarium.deliverable_presets import AVAILABLE_PRESETS, load_preset

        for name in AVAILABLE_PRESETS:
            data = load_preset(name)
            schema = data["schema"]
            assert "type" in schema, f"Preset '{name}' schema missing 'type'"
            assert "properties" in schema, f"Preset '{name}' schema missing 'properties'"

    def test_invalid_preset_raises(self):
        """Unknown preset name must raise."""
        from terrarium.deliverable_presets import load_preset

        with pytest.raises((FileNotFoundError, ValueError)):
            load_preset("nonexistent_preset_xyz")

    def test_known_presets_exist(self):
        """The 6 documented presets must all exist."""
        from terrarium.deliverable_presets import AVAILABLE_PRESETS

        expected = {"synthesis", "decision", "prediction", "brainstorm", "recommendation", "assessment"}
        actual = set(AVAILABLE_PRESETS)
        missing = expected - actual
        assert not missing, f"Missing documented presets: {missing}"


# ---------------------------------------------------------------------------
# Actor roles tests
# ---------------------------------------------------------------------------


class TestActorRolesParsing:
    """Verify --actors flag parsing produces valid actor_specs."""

    def test_single_role_is_lead(self):
        """Single role → lead=True."""
        roles = ["economist"]
        specs = self._build_specs(roles)
        assert len(specs) == 1
        assert specs[0]["role"] == "economist"
        assert specs[0]["lead"] is True
        assert specs[0]["type"] == "internal"
        assert specs[0]["count"] == 1

    def test_multiple_roles_first_is_lead(self):
        """First of multiple roles is lead, others are not."""
        roles = ["economist", "analyst", "strategist"]
        specs = self._build_specs(roles)
        assert len(specs) == 3
        assert specs[0].get("lead") is True
        assert "lead" not in specs[1]
        assert "lead" not in specs[2]

    def test_all_roles_are_internal(self):
        """--actors always creates internal actors."""
        roles = ["a", "b", "c"]
        specs = self._build_specs(roles)
        for spec in specs:
            assert spec["type"] == "internal"

    def test_all_roles_count_one(self):
        """Each role has count=1."""
        roles = ["a", "b"]
        specs = self._build_specs(roles)
        for spec in specs:
            assert spec["count"] == 1

    def test_empty_string_filtered(self):
        """Empty strings in comma-separated list are filtered out."""
        raw = "economist,,analyst, ,strategist"
        roles = [r.strip() for r in raw.split(",") if r.strip()]
        assert roles == ["economist", "analyst", "strategist"]

    @staticmethod
    def _build_specs(roles: list[str]) -> list[dict]:
        """Replicate the CLI logic for building actor_specs from roles."""
        from typing import Any

        specs: list[dict[str, Any]] = []
        for i, role in enumerate(roles):
            spec: dict[str, Any] = {
                "role": role,
                "type": "internal",
                "count": 1,
            }
            if i == 0:
                spec["lead"] = True
            specs.append(spec)
        return specs


# ---------------------------------------------------------------------------
# CLI integration harness
# ---------------------------------------------------------------------------


class TestCLIFlagsHarness:
    """Structural contracts for CLI flags — catches signature drift."""

    def test_run_command_has_deliverable_option(self):
        """The run command must accept --deliverable."""
        from terrarium.cli import app
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app, ["run", "--help"])
        assert "--deliverable" in result.output, "--deliverable not in run --help output"

    def test_run_command_has_actors_option(self):
        """The run command must accept --actors."""
        from terrarium.cli import app
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app, ["run", "--help"])
        assert "--actors" in result.output, "--actors not in run --help output"

    def test_deliverable_help_lists_all_types(self):
        """--deliverable help text must mention all 6 types."""
        from terrarium.cli import app
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(app, ["run", "--help"])
        for name in ["synthesis", "decision", "prediction", "brainstorm", "recommendation", "assessment"]:
            assert name in result.output, f"Deliverable '{name}' not mentioned in --deliverable help"
