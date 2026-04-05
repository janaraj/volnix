"""Tests for volnix.reality.presets -- preset loading and enum values.

Tests loading the 3 built-in presets (ideal, messy, hostile) from YAML,
custom YAML file loading, invalid preset handling, and frozen results.
"""

from __future__ import annotations

import pytest
import yaml

from volnix.core.errors import InvalidPresetError
from volnix.core.types import RealityPreset
from volnix.reality.dimensions import WorldConditions
from volnix.reality.presets import load_from_yaml, load_preset


class TestLoadIdeal:
    """Loading the ideal preset returns all-zero / lowest intensity conditions."""

    def test_load_ideal(self) -> None:
        wc = load_preset("ideal")
        assert isinstance(wc, WorldConditions)
        # Information: all zeros (pristine)
        assert wc.information.staleness == 0
        assert wc.information.incompleteness == 0
        assert wc.information.inconsistency == 0
        assert wc.information.noise == 0
        # Reliability: all zeros (rock_solid)
        assert wc.reliability.failures == 0
        assert wc.reliability.timeouts == 0
        assert wc.reliability.degradation == 0
        # Friction: all zeros (everyone_helpful)
        assert wc.friction.uncooperative == 0
        assert wc.friction.deceptive == 0
        assert wc.friction.hostile == 0
        # Complexity: all zeros (straightforward)
        assert wc.complexity.ambiguity == 0
        # Boundaries: all zeros (locked_down)
        assert wc.boundaries.access_limits == 0


class TestLoadMessy:
    """Loading the messy preset returns moderate intensity conditions."""

    def test_load_messy(self) -> None:
        wc = load_preset("messy")
        assert isinstance(wc, WorldConditions)
        # somewhat_neglected information
        assert wc.information.staleness == 30
        assert wc.information.incompleteness == 35
        # occasionally_flaky reliability
        assert wc.reliability.failures == 20
        assert wc.reliability.timeouts == 15
        # some_difficult_people friction
        assert wc.friction.uncooperative == 30
        assert wc.friction.deceptive == 15
        # moderately_challenging complexity
        assert wc.complexity.ambiguity == 35
        assert wc.complexity.edge_cases == 25
        # a_few_gaps boundaries
        assert wc.boundaries.access_limits == 25


class TestLoadHostile:
    """Loading the hostile preset returns high intensity conditions."""

    def test_load_hostile(self) -> None:
        wc = load_preset("hostile")
        assert isinstance(wc, WorldConditions)
        # poorly_maintained information
        assert wc.information.staleness == 55
        assert wc.information.incompleteness == 60
        # frequently_broken reliability
        assert wc.reliability.failures == 50
        assert wc.reliability.timeouts == 35
        # many_difficult_people friction
        assert wc.friction.uncooperative == 55
        assert wc.friction.deceptive == 30
        assert wc.friction.sophistication == "medium"
        # frequently_confusing complexity
        assert wc.complexity.ambiguity == 60
        # many_gaps boundaries
        assert wc.boundaries.access_limits == 50


class TestYamlParseable:
    """All 3 YAML preset files load without error."""

    def test_yaml_parseable(self) -> None:
        for preset_name in ["ideal", "messy", "hostile"]:
            wc = load_preset(preset_name)
            assert isinstance(wc, WorldConditions)


class TestInvalidPresetRaises:
    """An unknown preset name raises InvalidPresetError."""

    def test_invalid_preset_raises(self) -> None:
        with pytest.raises(InvalidPresetError):
            load_preset("fantasy")

        with pytest.raises(InvalidPresetError):
            load_preset("nonexistent")


class TestCustomYamlPath:
    """load_from_yaml can load conditions from a custom YAML file."""

    def test_custom_yaml_path(self, tmp_path) -> None:
        custom_yaml = tmp_path / "custom.yaml"
        custom_yaml.write_text(
            yaml.dump({
                "information": "mostly_clean",
                "reliability": "rock_solid",
                "friction": "everyone_helpful",
                "complexity": "mostly_clear",
                "boundaries": "well_controlled",
            })
        )
        wc = load_from_yaml(str(custom_yaml))
        assert isinstance(wc, WorldConditions)
        # mostly_clean information
        assert wc.information.staleness == 10
        assert wc.information.incompleteness == 12


class TestPresetReturnsFrozen:
    """The result of load_preset is a frozen WorldConditions."""

    def test_preset_returns_frozen(self) -> None:
        wc = load_preset("messy")
        with pytest.raises(Exception):
            wc.information = wc.information  # type: ignore[misc]


class TestEnumValues:
    """RealityPreset enum values match expected strings."""

    def test_enum_values(self) -> None:
        assert RealityPreset.IDEAL == "ideal"
        assert RealityPreset.MESSY == "messy"
        assert RealityPreset.HOSTILE == "hostile"
        assert len(RealityPreset) == 3
