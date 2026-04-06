"""Tests for volnix.reality.labels -- label system.

Tests the two-level config system that maps human-readable labels (e.g.
"somewhat_neglected") to concrete dimension attribute values (0-100).
Each of the 5 dimensions has exactly 5 labels ordered by intensity.
"""

from __future__ import annotations

import pytest

from volnix.core.errors import InvalidLabelError
from volnix.reality.dimensions import (
    BoundaryDimension,
    ComplexityDimension,
    InformationQualityDimension,
    ReliabilityDimension,
    SocialFrictionDimension,
)
from volnix.reality.labels import (
    LABEL_SCALES,
    is_valid_label,
    label_to_intensity,
    resolve_dimension,
    resolve_label,
)


class TestAllLabelsValid:
    """Every one of the 25 labels (5 per dimension) should be recognized."""

    def test_all_25_labels_valid(self) -> None:
        all_labels = {
            "information": [
                "pristine",
                "mostly_clean",
                "somewhat_neglected",
                "poorly_maintained",
                "chaotic",
            ],
            "reliability": [
                "rock_solid",
                "mostly_reliable",
                "occasionally_flaky",
                "frequently_broken",
                "barely_functional",
            ],
            "friction": [
                "everyone_helpful",
                "mostly_cooperative",
                "some_difficult_people",
                "many_difficult_people",
                "actively_hostile",
            ],
            "complexity": [
                "straightforward",
                "mostly_clear",
                "moderately_challenging",
                "frequently_confusing",
                "overwhelmingly_complex",
            ],
            "boundaries": [
                "locked_down",
                "well_controlled",
                "a_few_gaps",
                "many_gaps",
                "wide_open",
            ],
        }
        for dim_name, labels in all_labels.items():
            for label in labels:
                assert is_valid_label(label, dim_name), f"{label} should be valid for {dim_name}"


class TestResolveLabelInformation:
    """resolve_label for information dimension returns InformationQualityDimension."""

    def test_resolve_label_information(self) -> None:
        dim = resolve_label("information", "somewhat_neglected")
        assert isinstance(dim, InformationQualityDimension)
        assert dim.staleness == 30
        assert dim.incompleteness == 35
        assert dim.inconsistency == 20
        assert dim.noise == 30


class TestResolveLabelFriction:
    """resolve_label for friction dimension returns SocialFrictionDimension."""

    def test_resolve_label_friction(self) -> None:
        dim = resolve_label("friction", "some_difficult_people")
        assert isinstance(dim, SocialFrictionDimension)
        assert dim.uncooperative == 30
        assert dim.deceptive == 15
        assert dim.hostile == 8
        assert dim.sophistication == "medium"


class TestResolveDimensionWithLabel:
    """resolve_dimension with a string label resolves to the correct dimension."""

    def test_resolve_dimension_with_label(self) -> None:
        dim = resolve_dimension("reliability", "occasionally_flaky")
        assert isinstance(dim, ReliabilityDimension)
        assert dim.failures == 20
        assert dim.timeouts == 15
        assert dim.degradation == 10


class TestResolveDimensionWithDict:
    """resolve_dimension with a dict creates the dimension from explicit values."""

    def test_resolve_dimension_with_dict(self) -> None:
        dim = resolve_dimension(
            "complexity",
            {
                "ambiguity": 50,
                "edge_cases": 40,
                "contradictions": 10,
                "urgency": 25,
                "volatility": 20,
            },
        )
        assert isinstance(dim, ComplexityDimension)
        assert dim.ambiguity == 50
        assert dim.edge_cases == 40
        assert dim.contradictions == 10
        assert dim.urgency == 25
        assert dim.volatility == 20


class TestInvalidLabelRaises:
    """An unrecognized label raises InvalidLabelError."""

    def test_invalid_label_raises(self) -> None:
        with pytest.raises(InvalidLabelError):
            resolve_label("information", "totally_fake_label")

        with pytest.raises(InvalidLabelError):
            resolve_label("nonexistent_dimension", "pristine")


class TestLabelIntensityOrdering:
    """Labels within each dimension are ordered from low to high intensity."""

    def test_label_intensity_ordering(self) -> None:
        # Information: pristine < mostly_clean < somewhat_neglected < poorly_maintained < chaotic
        intensities = [
            label_to_intensity("pristine", "information"),
            label_to_intensity("mostly_clean", "information"),
            label_to_intensity("somewhat_neglected", "information"),
            label_to_intensity("poorly_maintained", "information"),
            label_to_intensity("chaotic", "information"),
        ]
        assert intensities == sorted(intensities)
        assert intensities[0] < intensities[-1]

        # Reliability
        rel_intensities = [
            label_to_intensity("rock_solid", "reliability"),
            label_to_intensity("mostly_reliable", "reliability"),
            label_to_intensity("occasionally_flaky", "reliability"),
            label_to_intensity("frequently_broken", "reliability"),
            label_to_intensity("barely_functional", "reliability"),
        ]
        assert rel_intensities == sorted(rel_intensities)

        # Friction
        fri_intensities = [
            label_to_intensity("everyone_helpful", "friction"),
            label_to_intensity("mostly_cooperative", "friction"),
            label_to_intensity("some_difficult_people", "friction"),
            label_to_intensity("many_difficult_people", "friction"),
            label_to_intensity("actively_hostile", "friction"),
        ]
        assert fri_intensities == sorted(fri_intensities)

        # Complexity
        comp_intensities = [
            label_to_intensity("straightforward", "complexity"),
            label_to_intensity("mostly_clear", "complexity"),
            label_to_intensity("moderately_challenging", "complexity"),
            label_to_intensity("frequently_confusing", "complexity"),
            label_to_intensity("overwhelmingly_complex", "complexity"),
        ]
        assert comp_intensities == sorted(comp_intensities)

        # Boundaries
        bound_intensities = [
            label_to_intensity("locked_down", "boundaries"),
            label_to_intensity("well_controlled", "boundaries"),
            label_to_intensity("a_few_gaps", "boundaries"),
            label_to_intensity("many_gaps", "boundaries"),
            label_to_intensity("wide_open", "boundaries"),
        ]
        assert bound_intensities == sorted(bound_intensities)


class TestMixedConfig:
    """A mix of label strings and dicts should all resolve correctly."""

    def test_mixed_config(self) -> None:
        # Label-based resolution
        info = resolve_dimension("information", "pristine")
        assert isinstance(info, InformationQualityDimension)
        assert info.staleness == 0

        # Dict-based resolution
        bound = resolve_dimension(
            "boundaries", {"access_limits": 50, "rule_clarity": 40, "boundary_gaps": 20}
        )
        assert isinstance(bound, BoundaryDimension)
        assert bound.access_limits == 50


class TestSophisticationPreserved:
    """Friction labels should preserve the sophistication field."""

    def test_sophistication_preserved(self) -> None:
        low = resolve_label("friction", "everyone_helpful")
        assert low.sophistication == "low"

        medium = resolve_label("friction", "some_difficult_people")
        assert medium.sophistication == "medium"

        high = resolve_label("friction", "actively_hostile")
        assert high.sophistication == "high"


class TestLabelScalesComplete:
    """Every dimension has exactly 5 labels in LABEL_SCALES."""

    def test_label_scales_complete(self) -> None:
        expected_dimensions = {"information", "reliability", "friction", "complexity", "boundaries"}
        assert set(LABEL_SCALES.keys()) == expected_dimensions
        for dim_name, labels in LABEL_SCALES.items():
            assert len(labels) == 5, f"{dim_name} should have exactly 5 labels, got {len(labels)}"
