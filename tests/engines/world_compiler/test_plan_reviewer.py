"""Tests for PlanReviewer — D4b plan formatting, export, and reporting."""

from __future__ import annotations

from volnix.engines.world_compiler.plan import ServiceResolution, WorldPlan
from volnix.engines.world_compiler.plan_reviewer import PlanReviewer
from volnix.kernel.surface import ServiceSurface
from volnix.packs.verified.gmail.pack import EmailPack
from volnix.reality.presets import load_preset

# ── Helpers ──────────────────────────────────────────────────────


def _make_plan() -> WorldPlan:
    surface = ServiceSurface.from_pack(EmailPack())
    return WorldPlan(
        name="Acme Support",
        description="Support team world",
        seed=42,
        behavior="dynamic",
        mode="governed",
        services={
            "gmail": ServiceResolution(
                service_name="gmail",
                spec_reference="verified/gmail",
                surface=surface,
                resolution_source="tier1_pack",
            )
        },
        actor_specs=[{"role": "agent", "type": "external", "count": 2}],
        conditions=load_preset("messy"),
        seeds=["VIP customer scenario"],
        policies=[{"name": "refund_approval"}],
        mission="Resolve tickets efficiently",
        source="yaml",
    )


# ── Format ───────────────────────────────────────────────────────


class TestFormatPlan:
    def test_format_contains_name(self) -> None:
        reviewer = PlanReviewer()
        text = reviewer.format_plan(_make_plan())
        assert "Acme Support" in text

    def test_format_contains_services(self) -> None:
        reviewer = PlanReviewer()
        text = reviewer.format_plan(_make_plan())
        assert "email" in text
        assert "tier1_pack" in text

    def test_format_contains_reality(self) -> None:
        reviewer = PlanReviewer()
        text = reviewer.format_plan(_make_plan())
        assert "staleness=" in text

    def test_format_contains_actors(self) -> None:
        reviewer = PlanReviewer()
        text = reviewer.format_plan(_make_plan())
        assert "agent x2" in text

    def test_format_contains_mission(self) -> None:
        reviewer = PlanReviewer()
        text = reviewer.format_plan(_make_plan())
        assert "Resolve tickets" in text

    def test_format_contains_validation(self) -> None:
        reviewer = PlanReviewer()
        text = reviewer.format_plan(_make_plan())
        assert "Validation" in text


# ── YAML round-trip ──────────────────────────────────────────────


class TestYAMLRoundTrip:
    def test_to_yaml_returns_string(self) -> None:
        reviewer = PlanReviewer()
        yaml_str = reviewer.to_yaml(_make_plan())
        assert isinstance(yaml_str, str)
        assert "Acme Support" in yaml_str

    def test_yaml_roundtrip(self) -> None:
        reviewer = PlanReviewer()
        plan = _make_plan()
        yaml_str = reviewer.to_yaml(plan)
        loaded = reviewer.from_yaml(yaml_str)
        assert loaded["name"] == "Acme Support"
        assert loaded["seed"] == 42


# ── Report generation ────────────────────────────────────────────


class TestGenerateReport:
    def test_report_contains_sections(self) -> None:
        reviewer = PlanReviewer()
        plan = _make_plan()
        result = {
            "entities": {
                "email": [{"id": "e1"}],
                "customer": [{"id": "c1"}, {"id": "c2"}],
            },
            "actors": [],
            "warnings": ["minor issue"],
            "seeds_processed": 1,
            "snapshot_id": "snap_123",
        }
        report = reviewer.generate_report(plan, result)
        assert "VOLNIX WORLD GENERATION REPORT" in report
        assert "email: 1 entities" in report
        assert "customer: 2 entities" in report
        assert "TOTAL: 3 entities" in report
        assert "minor issue" in report
        assert "snap_123" in report
        assert "STATUS:" in report

    def test_report_success_status_no_warnings(self) -> None:
        reviewer = PlanReviewer()
        plan = _make_plan()
        result = {
            "entities": {"email": [{"id": "e1"}]},
            "actors": [],
            "warnings": [],
            "seeds_processed": 0,
        }
        report = reviewer.generate_report(plan, result)
        assert "STATUS: SUCCESS" in report

    def test_report_success_with_warnings(self) -> None:
        reviewer = PlanReviewer()
        plan = _make_plan()
        result = {
            "entities": {},
            "actors": [],
            "warnings": ["w1", "w2"],
            "seeds_processed": 0,
        }
        report = reviewer.generate_report(plan, result)
        assert "SUCCESS with 2 warnings" in report


# ── Validate ─────────────────────────────────────────────────────


class TestValidatePlan:
    def test_valid_plan_returns_surface_notes(self) -> None:
        """A plan with real EmailPack may have surface-level notes
        (e.g. no response_schema) but no structural errors."""
        reviewer = PlanReviewer()
        errors = reviewer.validate_plan(_make_plan())
        # EmailPack operations lack response_schema — these are surface notes
        # There should be no structural errors (missing name, no services)
        structural = [e for e in errors if "no operations" in e or "missing" in e.lower()]
        assert structural == []

    def test_invalid_plan_returns_errors(self) -> None:
        reviewer = PlanReviewer()
        plan = WorldPlan()  # missing name, no services
        errors = reviewer.validate_plan(plan)
        assert len(errors) >= 1
