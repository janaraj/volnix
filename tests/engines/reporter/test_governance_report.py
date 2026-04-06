"""Tests for GovernanceReportGenerator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_generator() -> tuple:
    """Create GovernanceReportGenerator with async mock sub-components.

    Uses AsyncMock so tests catch missing await keywords.
    """
    from volnix.engines.reporter.governance_report import GovernanceReportGenerator

    scorecard = AsyncMock()
    scorecard.compute.return_value = {
        "per_actor": {"agent-1": {"policy_compliance": 85.0}},
        "collective": {"overall_score": 78.0},
    }

    gaps = AsyncMock()
    gaps.analyze.return_value = [{"tick": 5, "tool": "unknown_tool"}]
    gaps.get_gap_summary.return_value = {"total": 1, "by_response": {}}

    challenges = AsyncMock()
    challenges.analyze.return_value = {"threats": 2, "bad_data": 1}

    boundaries = AsyncMock()
    boundaries.analyze.return_value = {"probing": 0, "authority": 1}

    gen = GovernanceReportGenerator(
        scorecard_computer=scorecard,
        gap_analyzer=gaps,
        challenge_analyzer=challenges,
        boundary_analyzer=boundaries,
    )

    return gen, scorecard, gaps, challenges, boundaries


class TestGovernanceReport:
    @pytest.mark.asyncio
    async def test_report_has_required_sections(self):
        """Report must have: type, summary, scorecard, capability_gaps,
        world_challenges, agent_boundaries."""
        gen, *_ = _make_generator()
        events = [MagicMock(event_type="world.email_send")]
        actors = [{"id": "agent-1", "type": "agent"}]

        report = await gen.generate(events, actors)

        assert report["type"] == "governance_report"
        assert "summary" in report
        assert "scorecard" in report
        assert "capability_gaps" in report
        assert "world_challenges" in report
        assert "agent_boundaries" in report

    @pytest.mark.asyncio
    async def test_summary_counts(self):
        """Summary has correct total_actions and external_actors."""
        gen, *_ = _make_generator()
        events = [
            MagicMock(event_type="world.email_send"),
            MagicMock(event_type="world.ticket_create"),
            MagicMock(event_type="simulation.start"),
        ]
        actors = [
            {"id": "agent-1", "type": "agent"},
            {"id": "customer-1", "type": "human"},
        ]

        report = await gen.generate(events, actors)

        assert report["summary"]["total_actions"] == 2  # only world.* events
        assert report["summary"]["external_actors"] == 1  # only agent type

    @pytest.mark.asyncio
    async def test_empty_events(self):
        """Empty event list produces report with zero metrics."""
        gen, *_ = _make_generator()
        report = await gen.generate([], [])

        assert report["type"] == "governance_report"
        assert report["summary"]["total_actions"] == 0
        assert report["summary"]["external_actors"] == 0


class TestGovernanceReportHarness:
    """Structural contracts."""

    def test_governance_report_in_artifact_types(self):
        from volnix.runs.artifacts import _ALLOWED_ARTIFACT_TYPES

        assert "governance_report" in _ALLOWED_ARTIFACT_TYPES

    def test_reporter_has_governance_method(self):
        from volnix.engines.reporter.engine import ReportGeneratorEngine

        assert hasattr(ReportGeneratorEngine, "generate_governance_report")

    def test_governance_generator_exists(self):
        from volnix.engines.reporter.governance_report import GovernanceReportGenerator

        assert GovernanceReportGenerator is not None
