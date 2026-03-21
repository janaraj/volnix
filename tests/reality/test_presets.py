"""Tests for terrarium.reality.presets -- preset loading and enum values."""

import pytest

from terrarium.reality.presets import RealityPreset, load_preset, load_preset_from_yaml
from terrarium.reality.dimensions import WorldConditions


class TestRealityPresetEnum:
    """Verify RealityPreset enum members and values."""

    def test_reality_preset_enum_values(self) -> None:
        """All three presets exist with expected string values."""
        ...


class TestLoadPreset:
    """Verify loading built-in presets produces correct WorldConditions."""

    def test_pristine_all_zeros(self) -> None:
        """Pristine preset has all dimension values at zero / low."""
        ...

    def test_realistic_values_match_doc(self) -> None:
        """Realistic preset values match the documented defaults."""
        ...

    def test_harsh_values_match_doc(self) -> None:
        """Harsh preset values match the documented defaults."""
        ...


class TestLoadPresetFromYaml:
    """Verify loading presets from custom YAML files."""

    def test_load_preset_from_yaml(self, tmp_path) -> None:
        """A valid YAML file is parsed into WorldConditions."""
        ...
