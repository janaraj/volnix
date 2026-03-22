"""Tests for terrarium.reality.dimensions -- dimension models and WorldConditions.

Tests the 5 dimension models (InformationQualityDimension, ReliabilityDimension,
SocialFrictionDimension, ComplexityDimension, BoundaryDimension) and the
WorldConditions aggregate. All models are frozen Pydantic BaseModels with
numeric fields validated in the 0-100 range.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from terrarium.reality.dimensions import (
    BoundaryDimension,
    ComplexityDimension,
    InformationQualityDimension,
    ReliabilityDimension,
    SocialFrictionDimension,
    WorldConditions,
)


class TestInformationQualityDefaults:
    """Verify InformationQualityDimension defaults to all zeros."""

    def test_information_defaults(self) -> None:
        dim = InformationQualityDimension()
        assert dim.staleness == 0
        assert dim.incompleteness == 0
        assert dim.inconsistency == 0
        assert dim.noise == 0


class TestReliabilityDefaults:
    """Verify ReliabilityDimension defaults to all zeros."""

    def test_reliability_defaults(self) -> None:
        dim = ReliabilityDimension()
        assert dim.failures == 0
        assert dim.timeouts == 0
        assert dim.degradation == 0


class TestFrictionDefaults:
    """Verify SocialFrictionDimension defaults including sophistication."""

    def test_friction_defaults(self) -> None:
        dim = SocialFrictionDimension()
        assert dim.uncooperative == 0
        assert dim.deceptive == 0
        assert dim.hostile == 0
        assert dim.sophistication == "low"


class TestComplexityDefaults:
    """Verify ComplexityDimension defaults to all zeros."""

    def test_complexity_defaults(self) -> None:
        dim = ComplexityDimension()
        assert dim.ambiguity == 0
        assert dim.edge_cases == 0
        assert dim.contradictions == 0
        assert dim.urgency == 0
        assert dim.volatility == 0


class TestBoundaryDefaults:
    """Verify BoundaryDimension defaults to all zeros."""

    def test_boundary_defaults(self) -> None:
        dim = BoundaryDimension()
        assert dim.access_limits == 0
        assert dim.rule_clarity == 0
        assert dim.boundary_gaps == 0


class TestFrozenImmutability:
    """All dimension models and WorldConditions are frozen (immutable)."""

    def test_frozen_immutability(self) -> None:
        dim = InformationQualityDimension()
        with pytest.raises(Exception):
            dim.staleness = 50  # type: ignore[misc]

        rel = ReliabilityDimension()
        with pytest.raises(Exception):
            rel.failures = 10  # type: ignore[misc]

        fric = SocialFrictionDimension()
        with pytest.raises(Exception):
            fric.hostile = 20  # type: ignore[misc]

        comp = ComplexityDimension()
        with pytest.raises(Exception):
            comp.ambiguity = 30  # type: ignore[misc]

        bound = BoundaryDimension()
        with pytest.raises(Exception):
            bound.access_limits = 5  # type: ignore[misc]

        wc = WorldConditions()
        with pytest.raises(Exception):
            wc.information = InformationQualityDimension()  # type: ignore[misc]


class TestWorldConditionsAggregate:
    """Verify WorldConditions aggregates all 5 dimensions."""

    def test_world_conditions_aggregate(self) -> None:
        wc = WorldConditions()
        assert isinstance(wc.information, InformationQualityDimension)
        assert isinstance(wc.reliability, ReliabilityDimension)
        assert isinstance(wc.friction, SocialFrictionDimension)
        assert isinstance(wc.complexity, ComplexityDimension)
        assert isinstance(wc.boundaries, BoundaryDimension)


class TestValidationRange:
    """Numeric fields must be in the 0-100 range; violations raise ValidationError."""

    def test_validation_range(self) -> None:
        # Over 100 should fail
        with pytest.raises(ValidationError):
            InformationQualityDimension(staleness=101)

        # Negative should fail
        with pytest.raises(ValidationError):
            ReliabilityDimension(failures=-1)

        # Boundary values should work
        dim_low = ComplexityDimension(ambiguity=0)
        assert dim_low.ambiguity == 0

        dim_high = BoundaryDimension(access_limits=100)
        assert dim_high.access_limits == 100

        # Just over should fail
        with pytest.raises(ValidationError):
            SocialFrictionDimension(uncooperative=101)

        # Negative on boundary dimension
        with pytest.raises(ValidationError):
            BoundaryDimension(boundary_gaps=-5)


class TestFieldNamesHelper:
    """field_names() class method returns the list of numeric attribute names."""

    def test_field_names_helper(self) -> None:
        info_fields = InformationQualityDimension.field_names()
        assert "staleness" in info_fields
        assert "incompleteness" in info_fields
        assert "inconsistency" in info_fields
        assert "noise" in info_fields

        rel_fields = ReliabilityDimension.field_names()
        assert "failures" in rel_fields
        assert "timeouts" in rel_fields
        assert "degradation" in rel_fields

        bound_fields = BoundaryDimension.field_names()
        assert "access_limits" in bound_fields
        assert "rule_clarity" in bound_fields
        assert "boundary_gaps" in bound_fields


class TestToDict:
    """to_dict() serializes dimension to a plain dict."""

    def test_to_dict(self) -> None:
        dim = InformationQualityDimension(staleness=10, incompleteness=20, inconsistency=5, noise=15)
        d = dim.to_dict()
        assert isinstance(d, dict)
        assert d["staleness"] == 10
        assert d["incompleteness"] == 20
        assert d["inconsistency"] == 5
        assert d["noise"] == 15

        # Friction should include sophistication
        fric = SocialFrictionDimension(uncooperative=30, deceptive=15, hostile=8, sophistication="medium")
        fd = fric.to_dict()
        assert fd["sophistication"] == "medium"
        assert fd["uncooperative"] == 30
