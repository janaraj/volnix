"""Tests for volnix.reality.expander -- ConditionExpander logic.

Tests the expander's ability to expand presets with overrides, build
LLM prompt context, produce summaries, and merge overrides. Also verifies
that old entity-mutation methods have been removed.
"""

from __future__ import annotations

import pytest

from volnix.reality.dimensions import WorldConditions
from volnix.reality.expander import ConditionExpander


class TestExpandMessy:
    """Expanding the messy preset returns WorldConditions with moderate values."""

    def test_expand_messy(self) -> None:
        expander = ConditionExpander()
        wc = expander.expand("messy")
        assert isinstance(wc, WorldConditions)
        # messy preset uses "somewhat_neglected" information → staleness=30
        assert wc.information.staleness == 30
        assert wc.information.incompleteness == 35
        # messy uses "occasionally_flaky" reliability → failures=20
        assert wc.reliability.failures == 20


class TestExpandWithLabelOverride:
    """Preset + single label override merges correctly."""

    def test_expand_with_label_override(self) -> None:
        expander = ConditionExpander()
        wc = expander.expand("messy", overrides={"friction": "many_difficult_people"})
        assert isinstance(wc, WorldConditions)
        # friction upgraded from "some_difficult_people" to "many_difficult_people"
        assert wc.friction.uncooperative == 55
        assert wc.friction.deceptive == 30
        assert wc.friction.hostile == 20
        # other dimensions unchanged from messy
        assert wc.information.staleness == 30


class TestExpandWithDictOverride:
    """Preset + dict override with specific attribute values."""

    def test_expand_with_dict_override(self) -> None:
        expander = ConditionExpander()
        wc = expander.expand(
            "ideal",
            overrides={
                "information": {
                    "staleness": 50,
                    "incompleteness": 40,
                    "inconsistency": 30,
                    "noise": 25,
                }
            },
        )
        assert isinstance(wc, WorldConditions)
        assert wc.information.staleness == 50
        assert wc.information.incompleteness == 40
        assert wc.information.inconsistency == 30
        assert wc.information.noise == 25
        # reliability stays ideal (rock_solid)
        assert wc.reliability.failures == 0


class TestExpandMixedOverrides:
    """Mixed overrides: some dimensions as labels, some as dicts."""

    def test_expand_mixed_overrides(self) -> None:
        expander = ConditionExpander()
        wc = expander.expand(
            "ideal",
            overrides={
                "friction": "actively_hostile",
                "boundaries": {"access_limits": 60, "rule_clarity": 70, "boundary_gaps": 40},
            },
        )
        assert isinstance(wc, WorldConditions)
        # friction overridden to "actively_hostile"
        assert wc.friction.uncooperative == 75
        assert wc.friction.hostile == 40
        assert wc.friction.sophistication == "high"
        # boundaries overridden with dict
        assert wc.boundaries.access_limits == 60
        assert wc.boundaries.rule_clarity == 70
        assert wc.boundaries.boundary_gaps == 40
        # information stays ideal
        assert wc.information.staleness == 0


class TestBuildPromptContext:
    """build_prompt_context returns a dict with reality_summary and dimensions."""

    def test_build_prompt_context(self) -> None:
        expander = ConditionExpander()
        wc = expander.expand("messy")
        ctx = expander.build_prompt_context(wc)
        assert isinstance(ctx, dict)
        assert "reality_summary" in ctx
        assert "dimensions" in ctx
        assert isinstance(ctx["reality_summary"], str)
        assert len(ctx["reality_summary"]) > 0


class TestPromptContextHasAll5:
    """All 5 dimensions present in prompt context."""

    def test_prompt_context_has_all_5(self) -> None:
        expander = ConditionExpander()
        wc = expander.expand("messy")
        ctx = expander.build_prompt_context(wc)
        dims = ctx["dimensions"]
        expected = {"information", "reliability", "friction", "complexity", "boundaries"}
        assert set(dims.keys()) == expected


class TestPromptContextHasAttributes:
    """Each dimension in the context has level, attributes, and description."""

    def test_prompt_context_has_attributes(self) -> None:
        expander = ConditionExpander()
        wc = expander.expand("messy")
        ctx = expander.build_prompt_context(wc)
        for dim_name, dim_data in ctx["dimensions"].items():
            assert "level" in dim_data, f"{dim_name} missing 'level'"
            assert "attributes" in dim_data, f"{dim_name} missing 'attributes'"
            assert "description" in dim_data, f"{dim_name} missing 'description'"
            assert isinstance(dim_data["level"], str)
            assert isinstance(dim_data["attributes"], dict)
            assert isinstance(dim_data["description"], str)


class TestGetSummary:
    """get_summary returns a non-empty human-readable string."""

    def test_get_summary(self) -> None:
        expander = ConditionExpander()
        wc = expander.expand("messy")
        summary = expander.get_summary(wc)
        assert isinstance(summary, str)
        assert len(summary) > 10  # should be a meaningful paragraph


class TestMergeOverrides:
    """merge_overrides applies per-dimension overrides onto a base WorldConditions."""

    def test_merge_overrides(self) -> None:
        expander = ConditionExpander()
        base = expander.expand("ideal")
        merged = expander.merge_overrides(base, {"reliability": "frequently_broken"})
        assert isinstance(merged, WorldConditions)
        # reliability changed
        assert merged.reliability.failures == 50
        assert merged.reliability.timeouts == 35
        # information stays ideal
        assert merged.information.staleness == 0


class TestInvalidDimensionName:
    """An unknown dimension name in overrides should raise an error."""

    def test_invalid_dimension_name(self) -> None:
        expander = ConditionExpander()
        with pytest.raises(Exception):
            expander.expand("messy", overrides={"nonexistent_dimension": "some_label"})


class TestNoApplyToEntities:
    """ConditionExpander must NOT have apply_to_entities method (removed in D1)."""

    def test_no_apply_to_entities(self) -> None:
        expander = ConditionExpander()
        assert not hasattr(expander, "apply_to_entities"), (
            "apply_to_entities should have been removed"
        )


class TestNoEntityMutationMethods:
    """Verify ALL old mutation methods are removed from ConditionExpander."""

    def test_no_entity_mutation_methods(self) -> None:
        expander = ConditionExpander()
        removed_methods = [
            "apply_to_entities",
            "apply_to_actors",
            "apply_to_services",
            "apply_to_boundaries",
        ]
        for method_name in removed_methods:
            assert not hasattr(expander, method_name), (
                f"{method_name} should have been removed from ConditionExpander"
            )


class TestAllDescriptionsCovered:
    """Verify all 25 dimension+label combinations have non-fallback descriptions."""

    def test_all_25_descriptions_non_fallback(self) -> None:
        from volnix.reality.labels import LABEL_SCALES, resolve_label

        expander = ConditionExpander()
        for dim_name, labels in LABEL_SCALES.items():
            for label in labels:
                dim = resolve_label(dim_name, label)
                desc = expander._describe_dimension(dim_name, label, dim.to_dict())
                # Should NOT be the fallback format "dimension_name: label"
                assert desc != f"{dim_name}: {label}", (
                    f"Missing description for ({dim_name}, {label})"
                )
                assert len(desc) > 20, f"Description too short for ({dim_name}, {label}): {desc}"
