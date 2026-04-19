"""Tests for :class:`CohortConfig` Pydantic validators (review fixes N3, N6).

These validators catch authoring mistakes at YAML-load time rather
than letting them fall through to silent truncation in
:class:`CohortManager`.
"""

from __future__ import annotations

import pytest

from volnix.engines.agency.config import CohortConfig


class TestPolicyStringValidation:
    """N3: every policy string must be one of the three allowed values."""

    def test_unknown_policy_string_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown policy"):
            CohortConfig(
                max_active=10,
                inactive_event_policies={
                    "default": "defer",
                    "npc.exposure": "DEFURR",  # typo
                },
            )

    def test_uppercase_variant_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown policy"):
            CohortConfig(
                max_active=10,
                inactive_event_policies={"default": "PROMOTE"},
            )

    def test_missing_default_rejected(self) -> None:
        with pytest.raises(ValueError, match="must include a 'default' key"):
            CohortConfig(
                max_active=10,
                inactive_event_policies={"npc.exposure": "defer"},
            )

    def test_all_three_valid_policies_accepted(self) -> None:
        cfg = CohortConfig(
            max_active=10,
            inactive_event_policies={
                "default": "defer",
                "npc.exposure": "record_only",
                "npc.interview_probe": "promote",
            },
        )
        assert cfg.inactive_event_policies["default"] == "defer"


class TestCrossFieldValidation:
    """N6: nonsensical sizes must fail fast."""

    def test_rotation_batch_size_exceeds_max_active_rejected(self) -> None:
        with pytest.raises(ValueError, match="rotation_batch_size.*must not exceed max_active"):
            CohortConfig(max_active=5, rotation_batch_size=10)

    def test_promote_budget_exceeds_max_active_rejected(self) -> None:
        with pytest.raises(ValueError, match="promote_budget_per_tick.*must not exceed max_active"):
            CohortConfig(max_active=5, promote_budget_per_tick=100)

    def test_batch_equal_to_max_is_allowed(self) -> None:
        # Must also drop promote_budget to <= max_active because it
        # defaults to 10 and the validator also caps it.
        cfg = CohortConfig(max_active=5, rotation_batch_size=5, promote_budget_per_tick=5)
        assert cfg.rotation_batch_size == 5

    def test_when_disabled_cross_field_checks_skipped(self) -> None:
        """max_active=None means cohort is disabled; batch/budget values
        are ignored so any value passes."""
        cfg = CohortConfig(max_active=None, rotation_batch_size=9999, promote_budget_per_tick=9999)
        assert cfg.max_active is None


class TestDefaultsRemainValid:
    """The defaults must themselves pass the validators (regression guard)."""

    def test_default_construction_does_not_raise(self) -> None:
        # All defaults off → trivially passes.
        cfg = CohortConfig()
        assert cfg.max_active is None
        assert cfg.rotation_batch_size == 5
        assert cfg.promote_budget_per_tick == 10

    def test_typical_enabled_config_ok(self) -> None:
        cfg = CohortConfig(
            max_active=50,
            rotation_batch_size=5,
            promote_budget_per_tick=10,
        )
        assert cfg.max_active == 50
