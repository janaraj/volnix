"""Tests for ProfileUpdateProposer -- generate update proposals from drift."""
from __future__ import annotations

from volnix.engines.feedback.drift import DriftReport
from volnix.engines.feedback.proposer import ProfileUpdateProposer


async def test_propose_added_operation(make_profile):
    """Proposes adding operations found in external source."""
    profile = make_profile()
    drift = DriftReport(
        service_name="twilio",
        checked_at="2026-03-25T00:00:00Z",
        source="openapi",
        has_drift=True,
        profile_version="0.1.0",
        operations_added=["twilio_delete_message"],
    )

    proposer = ProfileUpdateProposer()
    proposal = await proposer.propose(profile, drift)

    assert len(proposal.proposed_changes) == 1
    assert proposal.proposed_changes[0].change_type == "add_operation"
    assert proposal.proposed_changes[0].target == "twilio_delete_message"
    assert proposal.requires_review is True


async def test_propose_removed_operation(make_profile):
    """Proposes removing operations no longer in external source."""
    profile = make_profile()
    drift = DriftReport(
        service_name="twilio",
        checked_at="2026-03-25T00:00:00Z",
        source="openapi",
        has_drift=True,
        profile_version="0.1.0",
        operations_removed=["twilio_send_message"],
    )

    proposer = ProfileUpdateProposer()
    proposal = await proposer.propose(profile, drift)

    assert len(proposal.proposed_changes) == 1
    assert proposal.proposed_changes[0].change_type == "remove_operation"
    assert proposal.auto_applicable is True


async def test_apply_proposal(make_profile):
    """Apply a proposal creates updated profile."""
    profile = make_profile(version="1.0.0")
    drift = DriftReport(
        service_name="twilio",
        checked_at="2026-03-25T00:00:00Z",
        source="openapi",
        has_drift=True,
        profile_version="1.0.0",
        external_version="2.0.0",
        operations_removed=["twilio_send_message"],
    )

    proposer = ProfileUpdateProposer()
    proposal = await proposer.propose(profile, drift)
    updated = await proposer.apply(profile, proposal)

    assert updated.version == "2.0.0"
    # twilio_send_message should be removed
    op_names = [op.name for op in updated.operations]
    assert "twilio_send_message" not in op_names
    # Source chain should include sync marker
    assert "sync:openapi" in updated.source_chain


async def test_propose_no_drift(make_profile):
    """No changes proposed when drift has no differences."""
    profile = make_profile()
    drift = DriftReport(
        service_name="twilio",
        checked_at="2026-03-25T00:00:00Z",
        source="openapi",
        has_drift=False,
        profile_version="0.1.0",
    )

    proposer = ProfileUpdateProposer()
    proposal = await proposer.propose(profile, drift)

    assert len(proposal.proposed_changes) == 0
    assert proposal.auto_applicable is False
