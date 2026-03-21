"""Tests for terrarium.core.types — NewType aliases, enums, and frozen dataclasses."""
import pytest
from terrarium.core.types import (
    EntityId, ActorId, ServiceId, EventId, ToolName, RunId,
    FidelityTier, StepVerdict, EnforcementMode,
    FidelityMetadata, ActionCost, BudgetState, StateDelta, SideEffect,
)


class TestNewTypeAliases:
    """Verify NewType aliases are str-based."""

    def test_entity_id_is_str(self):
        ...


class TestEnums:
    """Verify enum members and ordering."""

    def test_fidelity_tier_ordering(self):
        ...

    def test_step_verdict_values(self):
        ...

    def test_enforcement_mode_values(self):
        ...


class TestFrozenDataclasses:
    """Verify frozen (immutable) dataclass behaviour."""

    def test_fidelity_metadata_frozen(self):
        ...

    def test_action_cost_defaults(self):
        ...

    def test_budget_state_fields(self):
        ...

    def test_state_delta_frozen(self):
        ...

    def test_side_effect_frozen(self):
        ...


class TestFidelityAndRealityEnums:
    """Verify fidelity source, reality preset, and fidelity mode enums."""

    def test_fidelity_source_values():
        """FidelitySource has verified_pack, curated_profile, bootstrapped."""
        ...

    def test_reality_preset_values():
        """RealityPreset has pristine, realistic, harsh."""
        ...

    def test_fidelity_mode_values():
        """FidelityMode has auto, strict, exploratory."""
        ...

    def test_fidelity_tier_no_inferred():
        """FidelityTier should only have VERIFIED and PROFILED, not INFERRED."""
        ...
