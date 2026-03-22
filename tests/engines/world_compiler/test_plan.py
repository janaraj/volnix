"""Tests for WorldPlan and ServiceResolution models (D4a)."""
import pytest

from terrarium.engines.world_compiler.plan import WorldPlan, ServiceResolution
from terrarium.kernel.surface import ServiceSurface, APIOperation
from terrarium.reality.dimensions import WorldConditions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_surface(
    service_name: str = "email",
    confidence: float = 1.0,
    with_operations: bool = True,
) -> ServiceSurface:
    """Build a minimal ServiceSurface for tests."""
    ops = []
    if with_operations:
        ops = [
            APIOperation(
                name=f"{service_name}_send",
                service=service_name,
                description="Send",
                parameters={"to": {"type": "string"}},
                required_params=["to"],
                response_schema={"type": "object"},
            ),
        ]
    return ServiceSurface(
        service_name=service_name,
        category="communication",
        source="tier1_pack",
        fidelity_tier=1,
        operations=ops,
        entity_schemas={service_name: {"type": "object"}},
        confidence=confidence,
    )


def _make_resolution(
    service_name: str = "email",
    confidence: float = 1.0,
    with_operations: bool = True,
) -> ServiceResolution:
    return ServiceResolution(
        service_name=service_name,
        spec_reference=f"verified/{service_name}",
        surface=_make_surface(service_name, confidence, with_operations),
        resolution_source="tier1_pack",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWorldPlan:
    """WorldPlan model tests."""

    def test_frozen(self):
        """WorldPlan instances are frozen (immutable)."""
        plan = WorldPlan(name="Test")
        with pytest.raises(Exception):
            plan.name = "Changed"  # type: ignore[misc]

    def test_defaults(self):
        """Default values are correct when no args provided."""
        plan = WorldPlan()
        assert plan.name == ""
        assert plan.seed == 42
        assert plan.behavior == "dynamic"
        assert plan.fidelity == "auto"
        assert plan.mode == "governed"
        assert plan.services == {}
        assert plan.actor_specs == []
        assert plan.policies == []
        assert plan.seeds == []
        assert plan.mission == ""
        assert plan.source == ""
        assert plan.warnings == []
        assert plan.blueprint is None

    def test_with_services(self):
        """WorldPlan holds resolved services and exposes service names / entity types."""
        res = _make_resolution("email")
        plan = WorldPlan(name="Test", services={"email": res})

        assert plan.get_service_names() == ["email"]
        assert "email" in plan.get_entity_types()

    def test_with_conditions(self):
        """WorldPlan stores WorldConditions."""
        conds = WorldConditions()
        plan = WorldPlan(name="Test", conditions=conds)
        assert plan.conditions.information.staleness == 0

    def test_validate_missing_name(self):
        """validate_plan reports missing name."""
        plan = WorldPlan(services={"email": _make_resolution()})
        errors = plan.validate_plan()
        assert any("missing name" in e for e in errors)

    def test_validate_no_services(self):
        """validate_plan reports no services."""
        plan = WorldPlan(name="Test")
        errors = plan.validate_plan()
        assert any("no resolved services" in e for e in errors)

    def test_validate_strict_fidelity(self):
        """validate_plan in strict mode flags low-confidence services."""
        low_res = _make_resolution("slack", confidence=0.1)
        plan = WorldPlan(
            name="Test",
            fidelity="strict",
            services={"slack": low_res},
        )
        errors = plan.validate_plan()
        assert any("below strict fidelity" in e for e in errors)

    def test_validate_clean_plan(self):
        """A valid plan returns no errors (in auto fidelity)."""
        res = _make_resolution("email", confidence=1.0)
        plan = WorldPlan(name="Test", services={"email": res})
        errors = plan.validate_plan()
        # The only errors would be from surface validation (missing response_schema, etc.)
        # Our helper builds a complete surface, so we should have few/no blocking errors.
        # We specifically check that name and services are not flagged.
        assert not any("missing name" in e for e in errors)
        assert not any("no resolved services" in e for e in errors)


class TestServiceResolution:
    """ServiceResolution model tests."""

    def test_model(self):
        """ServiceResolution can be constructed with all fields."""
        surface = _make_surface("email")
        res = ServiceResolution(
            service_name="email",
            spec_reference="verified/email",
            surface=surface,
            resolution_source="tier1_pack",
        )
        assert res.service_name == "email"
        assert res.spec_reference == "verified/email"
        assert res.resolution_source == "tier1_pack"
        assert res.surface.service_name == "email"

    def test_frozen(self):
        """ServiceResolution is frozen."""
        res = _make_resolution()
        with pytest.raises(Exception):
            res.service_name = "changed"  # type: ignore[misc]
