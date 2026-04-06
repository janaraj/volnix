"""Tests for volnix.engines.animator.context -- AnimatorContext.

Covers: get_probability, for_organic_generation, WorldGenerationContext reuse.
"""

from __future__ import annotations

import pytest

from volnix.engines.animator.context import AnimatorContext
from volnix.engines.world_compiler.plan import WorldPlan
from volnix.reality.dimensions import (
    BoundaryDimension,
    ComplexityDimension,
    InformationQualityDimension,
    ReliabilityDimension,
    SocialFrictionDimension,
    WorldConditions,
)


def _messy_conditions() -> WorldConditions:
    """Create 'messy' preset-like conditions for testing."""
    return WorldConditions(
        information=InformationQualityDimension(
            staleness=30, incompleteness=35, inconsistency=20, noise=30
        ),
        reliability=ReliabilityDimension(failures=20, timeouts=15, degradation=10),
        friction=SocialFrictionDimension(
            uncooperative=30, deceptive=15, hostile=8, sophistication="medium"
        ),
        complexity=ComplexityDimension(
            ambiguity=35, edge_cases=25, contradictions=15, urgency=20, volatility=15
        ),
        boundaries=BoundaryDimension(access_limits=25, rule_clarity=30, boundary_gaps=12),
    )


def _make_plan(conditions: WorldConditions | None = None, behavior: str = "dynamic") -> WorldPlan:
    return WorldPlan(
        name="test-world",
        description="A test domain for customer support",
        behavior=behavior,
        conditions=conditions or WorldConditions(),
    )


# ---------------------------------------------------------------------------
# get_probability
# ---------------------------------------------------------------------------


def test_get_probability_reliability_failures_messy():
    """reliability.failures=20 -> 0.20 for messy preset."""
    ctx = AnimatorContext(_make_plan(_messy_conditions()))
    assert ctx.get_probability("reliability", "failures") == pytest.approx(0.20)


def test_get_probability_friction_deceptive_messy():
    """friction.deceptive=15 -> 0.15 for messy preset."""
    ctx = AnimatorContext(_make_plan(_messy_conditions()))
    assert ctx.get_probability("friction", "deceptive") == pytest.approx(0.15)


def test_get_probability_complexity_volatility():
    """complexity.volatility=15 -> 0.15."""
    ctx = AnimatorContext(_make_plan(_messy_conditions()))
    assert ctx.get_probability("complexity", "volatility") == pytest.approx(0.15)


def test_get_probability_boundaries_gaps():
    """boundaries.boundary_gaps=12 -> 0.12."""
    ctx = AnimatorContext(_make_plan(_messy_conditions()))
    assert ctx.get_probability("boundaries", "boundary_gaps") == pytest.approx(0.12)


def test_get_probability_zero_default():
    """Default conditions (all zero) -> 0.0 probability."""
    ctx = AnimatorContext(_make_plan())
    assert ctx.get_probability("reliability", "failures") == 0.0


def test_get_probability_string_attribute():
    """String attributes (sophistication) return 0.0."""
    ctx = AnimatorContext(_make_plan(_messy_conditions()))
    assert ctx.get_probability("friction", "sophistication") == 0.0


def test_get_probability_unknown_dimension():
    """Unknown dimension returns 0.0."""
    ctx = AnimatorContext(_make_plan())
    assert ctx.get_probability("nonexistent", "field") == 0.0


# ---------------------------------------------------------------------------
# for_organic_generation
# ---------------------------------------------------------------------------


def test_for_organic_generation_returns_correct_keys():
    """for_organic_generation() returns dict with expected template variable keys."""
    ctx = AnimatorContext(_make_plan(_messy_conditions()))
    vars = ctx.for_organic_generation()

    assert "reality_summary" in vars
    assert "reality_dimensions" in vars
    assert "behavior_mode" in vars
    assert "behavior_description" in vars
    assert "domain_description" in vars


def test_for_organic_generation_behavior_dynamic():
    """Dynamic mode behavior is correctly reflected."""
    ctx = AnimatorContext(_make_plan(_messy_conditions(), behavior="dynamic"))
    vars = ctx.for_organic_generation()
    assert vars["behavior_mode"] == "dynamic"
    assert "DYNAMIC" in vars["behavior_description"]


def test_for_organic_generation_domain():
    """Domain description is taken from the plan."""
    ctx = AnimatorContext(_make_plan(_messy_conditions()))
    vars = ctx.for_organic_generation()
    assert "customer support" in vars["domain_description"]


def test_for_organic_generation_reality_summary_non_empty():
    """Reality summary is non-empty for messy conditions."""
    ctx = AnimatorContext(_make_plan(_messy_conditions()))
    vars = ctx.for_organic_generation()
    assert len(vars["reality_summary"]) > 0


# ---------------------------------------------------------------------------
# Reuses WorldGenerationContext
# ---------------------------------------------------------------------------


def test_reuses_world_generation_context():
    """AnimatorContext internally creates a WorldGenerationContext."""
    ctx = AnimatorContext(_make_plan(_messy_conditions()))
    # _base should be a WorldGenerationContext
    from volnix.engines.world_compiler.generation_context import WorldGenerationContext

    assert isinstance(ctx._base, WorldGenerationContext)


def test_dimension_values_populated():
    """dimension_values dict is populated from WorldConditions."""
    ctx = AnimatorContext(_make_plan(_messy_conditions()))
    assert "reliability" in ctx.dimension_values
    assert ctx.dimension_values["reliability"]["failures"] == 20
    assert "information" in ctx.dimension_values
    assert ctx.dimension_values["information"]["staleness"] == 30
