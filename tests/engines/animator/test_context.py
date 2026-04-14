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


async def test_for_organic_generation_returns_correct_keys():
    """for_organic_generation() returns dict with expected template variable keys."""
    ctx = AnimatorContext(_make_plan(_messy_conditions()))
    vars = await ctx.for_organic_generation()

    assert "reality_summary" in vars
    assert "reality_dimensions" in vars
    assert "behavior_mode" in vars
    assert "behavior_description" in vars
    assert "domain_description" in vars
    # P3: entity_snapshot is always present (placeholder when no reader)
    assert "entity_snapshot" in vars


async def test_for_organic_generation_behavior_dynamic():
    """Dynamic mode behavior is correctly reflected."""
    ctx = AnimatorContext(_make_plan(_messy_conditions(), behavior="dynamic"))
    vars = await ctx.for_organic_generation()
    assert vars["behavior_mode"] == "dynamic"
    assert "DYNAMIC" in vars["behavior_description"]


async def test_for_organic_generation_domain():
    """Domain description is taken from the plan."""
    ctx = AnimatorContext(_make_plan(_messy_conditions()))
    vars = await ctx.for_organic_generation()
    assert "customer support" in vars["domain_description"]


async def test_for_organic_generation_reality_summary_non_empty():
    """Reality summary is non-empty for messy conditions."""
    ctx = AnimatorContext(_make_plan(_messy_conditions()))
    vars = await ctx.for_organic_generation()
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


# ---------------------------------------------------------------------------
# P3 — State snapshot for organic animator
# ---------------------------------------------------------------------------


async def test_context_without_state_reader_is_backward_compat():
    """Without a state_reader, entity_snapshot is a placeholder string.

    This is the backward-compat path: existing blueprints that don't
    wire a state reader still get a valid (inert) snapshot variable in
    the template output. No crash, no hang, no missing key.
    """
    ctx = AnimatorContext(_make_plan(_messy_conditions()))
    vars = await ctx.for_organic_generation()

    assert "entity_snapshot" in vars
    assert "unavailable" in vars["entity_snapshot"].lower()


async def test_context_with_state_reader_includes_snapshot():
    """With a state_reader, entity_snapshot is a formatted text block."""

    async def fake_reader():
        return {
            "port": [
                {"id": "haiphong", "status": "open", "congestion_level": "low"},
                {"id": "manila", "status": "open", "congestion_level": "high"},
            ],
            "weather_alert": [
                {
                    "id": "td_18w",
                    "severity": "Tropical Depression",
                    "region": "South China Sea",
                },
            ],
        }

    ctx = AnimatorContext(
        _make_plan(_messy_conditions()),
        state_reader=fake_reader,
    )
    vars = await ctx.for_organic_generation()

    snapshot = vars["entity_snapshot"]
    # Contains entity type headers
    assert "port" in snapshot
    assert "weather_alert" in snapshot
    # Contains entity IDs
    assert "haiphong" in snapshot
    assert "td_18w" in snapshot
    # Contains selected fields
    assert "Tropical Depression" in snapshot
    # Contains the total count
    assert "(2 total)" in snapshot  # port
    assert "(1 total)" in snapshot  # weather_alert


async def test_state_snapshot_caps_sample_size():
    """Entity type with >3 samples is capped at 3 in the rendered snapshot."""

    async def fake_reader():
        return {
            "order": [{"id": f"order-{i}", "status": "pending"} for i in range(20)],
        }

    ctx = AnimatorContext(_make_plan(), state_reader=fake_reader)
    vars = await ctx.for_organic_generation()

    snapshot = vars["entity_snapshot"]
    # All 20 are counted in the total
    assert "(20 total)" in snapshot
    # Only first 3 samples are rendered
    assert "order-0" in snapshot
    assert "order-1" in snapshot
    assert "order-2" in snapshot
    assert "order-3" not in snapshot
    assert "order-19" not in snapshot


async def test_state_snapshot_excludes_game_internals_by_default():
    """Default exclude list hides game-internal entity types from the snapshot."""

    async def fake_reader():
        return {
            "port": [{"id": "haiphong", "status": "open"}],
            "negotiation_target": [
                {"id": "tgt-buyer", "game_owner_id": "buyer-1", "batna_score": 30}
            ],
            "negotiation_scorecard": [{"id": "sc-1", "total_points": 0}],
        }

    ctx = AnimatorContext(_make_plan(), state_reader=fake_reader)
    vars = await ctx.for_organic_generation()

    snapshot = vars["entity_snapshot"]
    # Public types appear
    assert "port" in snapshot
    assert "haiphong" in snapshot
    # Game internals are filtered out — the LLM must not learn them
    assert "negotiation_target" not in snapshot
    assert "negotiation_scorecard" not in snapshot
    assert "batna_score" not in snapshot


async def test_state_snapshot_exclude_override_from_blueprint():
    """Blueprint can extend the exclude list via constructor parameter."""

    async def fake_reader():
        return {
            "port": [{"id": "haiphong", "status": "open"}],
            "fuel_price": [{"id": "bunker_index", "value": 650}],
            "market_comp": [{"id": "comp-1", "value": 26}],
        }

    # Blueprint says "also hide market_comp from the animator"
    ctx = AnimatorContext(
        _make_plan(),
        state_reader=fake_reader,
        state_snapshot_exclude=["market_comp"],
    )
    vars = await ctx.for_organic_generation()

    snapshot = vars["entity_snapshot"]
    assert "port" in snapshot
    assert "fuel_price" in snapshot
    assert "market_comp" not in snapshot
    # Defaults are still in effect too
    assert "negotiation_target" not in snapshot


async def test_state_snapshot_reader_failure_returns_placeholder():
    """If the state_reader raises, the snapshot degrades gracefully.

    The animator must never crash because state is temporarily
    unavailable — organic generation should continue with a placeholder.
    """

    async def broken_reader():
        raise RuntimeError("state engine not yet started")

    ctx = AnimatorContext(_make_plan(), state_reader=broken_reader)
    vars = await ctx.for_organic_generation()

    snapshot = vars["entity_snapshot"]
    assert "unavailable" in snapshot.lower() or "raised" in snapshot.lower()


async def test_state_snapshot_entity_summary_picks_preferred_fields():
    """Entity summaries prefer id/status/severity/etc. over noisy fields."""

    async def fake_reader():
        return {
            "incident": [
                {
                    "id": "inc-42",
                    "status": "open",
                    "severity": "critical",
                    "created_at": "2026-04-11T00:00:00Z",
                    "noisy_internal_field_1": "x" * 500,
                    "noisy_internal_field_2": "y" * 500,
                    "tags": ["a", "b", "c"],  # list — should be skipped
                },
            ],
        }

    ctx = AnimatorContext(_make_plan(), state_reader=fake_reader)
    vars = await ctx.for_organic_generation()

    snapshot = vars["entity_snapshot"]
    # Head field present
    assert "inc-42" in snapshot
    # Preferred fields present
    assert "status=open" in snapshot
    assert "severity=critical" in snapshot
    # Noisy large string NOT included
    assert "noisy_internal_field_1" not in snapshot
    # List field NOT included (we skip list/dict values)
    assert "tags" not in snapshot
