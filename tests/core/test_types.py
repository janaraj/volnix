"""Tests for volnix.core.types — NewType aliases, enums, and frozen dataclasses."""

import pytest

from volnix.core.types import (
    ActionCost,
    BehaviorMode,
    BudgetState,
    EnforcementMode,
    EntityId,
    FidelityMetadata,
    FidelityMode,
    FidelitySource,
    FidelityTier,
    RealityPreset,
    SideEffect,
    StateDelta,
    StepVerdict,
)


class TestNewTypeAliases:
    """Verify NewType aliases are str-based."""

    def test_entity_id_is_str(self):
        eid = EntityId("ent_123")
        assert isinstance(eid, str)
        assert eid == "ent_123"


class TestEnums:
    """Verify enum members and ordering."""

    def test_fidelity_tier_ordering(self):
        assert FidelityTier.VERIFIED.value < FidelityTier.PROFILED.value

    def test_step_verdict_values(self):
        assert len(StepVerdict) == 5
        assert "ALLOW" in [v.name for v in StepVerdict]
        assert "DENY" in [v.name for v in StepVerdict]

    def test_enforcement_mode_values(self):
        assert len(EnforcementMode) == 4


class TestFrozenDataclasses:
    """Verify frozen (immutable) dataclass behaviour."""

    def test_fidelity_metadata_frozen(self):
        fm = FidelityMetadata(tier=FidelityTier.VERIFIED, source=FidelitySource.VERIFIED_PACK)
        with pytest.raises(Exception):
            fm.tier = FidelityTier.PROFILED

    def test_action_cost_defaults(self):
        cost = ActionCost()
        assert cost.api_calls == 0
        assert cost.llm_spend_usd == 0.0
        assert cost.world_actions == 0

    def test_budget_state_fields(self):
        bs = BudgetState(
            api_calls_remaining=100,
            api_calls_total=100,
            llm_spend_remaining_usd=50.0,
            llm_spend_total_usd=50.0,
            world_actions_remaining=10,
            world_actions_total=10,
        )
        assert bs.api_calls_remaining == 100
        assert bs.llm_spend_total_usd == 50.0
        assert bs.time_remaining_seconds is None

    def test_state_delta_frozen(self):
        sd = StateDelta(
            entity_type="charge",
            entity_id=EntityId("ch_1"),
            operation="create",
            fields={"status": "new"},
        )
        with pytest.raises(Exception):
            sd.entity_type = "other"

    def test_side_effect_frozen(self):
        se = SideEffect(effect_type="send_notification")
        with pytest.raises(Exception):
            se.effect_type = "other"


class TestFidelityAndRealityEnums:
    """Verify fidelity source, reality preset, and fidelity mode enums."""

    def test_fidelity_source_values(self):
        """FidelitySource has verified_pack, curated_profile, bootstrapped."""
        assert FidelitySource.VERIFIED_PACK == "verified_pack"
        assert FidelitySource.CURATED_PROFILE == "curated_profile"
        assert FidelitySource.BOOTSTRAPPED == "bootstrapped"
        assert len(FidelitySource) == 3

    def test_reality_preset_values(self):
        """RealityPreset has ideal, messy, hostile."""
        assert RealityPreset.IDEAL == "ideal"
        assert RealityPreset.MESSY == "messy"
        assert RealityPreset.HOSTILE == "hostile"
        assert len(RealityPreset) == 3

    def test_behavior_mode_values(self):
        """BehaviorMode has static, reactive, dynamic."""
        assert BehaviorMode.STATIC == "static"
        assert BehaviorMode.REACTIVE == "reactive"
        assert BehaviorMode.DYNAMIC == "dynamic"
        assert len(BehaviorMode) == 3

    def test_fidelity_mode_values(self):
        """FidelityMode has auto, strict, exploratory."""
        assert FidelityMode.AUTO == "auto"
        assert FidelityMode.STRICT == "strict"
        assert FidelityMode.EXPLORATORY == "exploratory"
        assert len(FidelityMode) == 3

    def test_fidelity_tier_no_inferred(self):
        """FidelityTier should only have VERIFIED and PROFILED, not INFERRED."""
        assert FidelityTier.VERIFIED == 1
        assert FidelityTier.PROFILED == 2
        assert len(FidelityTier) == 2
        assert not hasattr(FidelityTier, "INFERRED")
