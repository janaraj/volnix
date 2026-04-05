"""Tests for ExternalSyncChecker -- orchestrated drift + proposals."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from volnix.engines.feedback.drift import DriftReport
from volnix.engines.feedback.proposer import ProfileUpdateProposer
from volnix.engines.feedback.sync import ExternalSyncChecker


async def test_check_drift_single(make_profile):
    """Check drift for a single service."""
    profile = make_profile()
    registry = MagicMock()
    registry.get_profile = MagicMock(return_value=profile)

    drift_report = DriftReport(
        service_name="twilio",
        checked_at="2026-03-25T00:00:00Z",
        source="openapi",
        has_drift=True,
        profile_version="0.1.0",
        operations_added=["twilio_new_op"],
    )

    detector = AsyncMock()
    detector.check = AsyncMock(return_value=[drift_report])

    checker = ExternalSyncChecker(
        drift_detector=detector,
        proposer=ProfileUpdateProposer(),
        profile_registry=registry,
        profile_loader=None,
    )

    reports = await checker.check_drift("twilio")
    assert len(reports) == 1
    assert reports[0].has_drift is True


async def test_check_all(make_profile):
    """Check all profiled services concurrently."""
    profiles = [
        make_profile(service_name="twilio"),
        make_profile(service_name="jira"),
    ]
    registry = MagicMock()
    registry.list_profiles = MagicMock(return_value=profiles)

    # Only twilio has drift
    async def mock_check(profile):
        if profile.service_name == "twilio":
            return [DriftReport(
                service_name="twilio",
                checked_at="now",
                source="openapi",
                has_drift=True,
                profile_version="0.1.0",
                operations_added=["new_op"],
            )]
        return []

    detector = AsyncMock()
    detector.check = mock_check

    checker = ExternalSyncChecker(
        drift_detector=detector,
        proposer=ProfileUpdateProposer(),
        profile_registry=registry,
        profile_loader=None,
    )

    reports = await checker.check_all(max_concurrent=2)
    assert len(reports) == 1
    assert reports[0].service_name == "twilio"


async def test_propose_update(make_profile):
    """Propose update creates a proposal from drift."""
    profile = make_profile()
    registry = MagicMock()
    registry.get_profile = MagicMock(return_value=profile)

    drift_report = DriftReport(
        service_name="twilio",
        checked_at="now",
        source="openapi",
        has_drift=True,
        profile_version="0.1.0",
        operations_added=["twilio_new_op"],
    )
    detector = AsyncMock()
    detector.check = AsyncMock(return_value=[drift_report])

    checker = ExternalSyncChecker(
        drift_detector=detector,
        proposer=ProfileUpdateProposer(),
        profile_registry=registry,
        profile_loader=None,
    )

    proposal = await checker.propose_update("twilio")
    assert proposal is not None
    assert len(proposal.proposed_changes) == 1
    assert proposal.proposed_changes[0].change_type == "add_operation"


async def test_apply_update(make_profile, tmp_path):
    """M7: apply_update saves to disk and registers updated profile."""
    from volnix.packs.profile_loader import ProfileLoader

    profile = make_profile()
    loader = ProfileLoader(tmp_path / "profiles")
    registry = MagicMock()
    registry.get_profile = MagicMock(return_value=profile)

    from volnix.engines.feedback.proposer import (
        ProfileUpdateProposal,
        ProposedChange,
    )

    proposal = ProfileUpdateProposal(
        service_name="twilio",
        drift_source="openapi",
        proposed_changes=[
            ProposedChange(
                change_type="remove_operation",
                target="twilio_send_message",
                description="Remove deprecated op",
            ),
        ],
        auto_applicable=True,
        requires_review=False,
    )

    # Need a real detector (not used in apply)
    detector = AsyncMock()
    proposer = ProfileUpdateProposer()

    checker = ExternalSyncChecker(
        drift_detector=detector,
        proposer=proposer,
        profile_registry=registry,
        profile_loader=loader,
    )

    updated = await checker.apply_update("twilio", proposal)
    op_names = [op.name for op in updated.operations]
    assert "twilio_send_message" not in op_names
    assert "sync:openapi" in updated.source_chain


async def test_no_drift_returns_none(make_profile):
    """No drift returns None for proposal."""
    profile = make_profile()
    registry = MagicMock()
    registry.get_profile = MagicMock(return_value=profile)

    detector = AsyncMock()
    detector.check = AsyncMock(return_value=[])

    checker = ExternalSyncChecker(
        drift_detector=detector,
        proposer=ProfileUpdateProposer(),
        profile_registry=registry,
        profile_loader=None,
    )

    proposal = await checker.propose_update("twilio")
    assert proposal is None
