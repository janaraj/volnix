"""Profile update proposer -- generates concrete changes from drift reports.

Given a DriftReport, produces a ProfileUpdateProposal with specific
changes that can be reviewed and applied to update the profile.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from terrarium.engines.feedback.drift import DriftReport
from terrarium.packs.profile_schema import (
    ProfileOperation,
    ServiceProfileData,
)

logger = logging.getLogger(__name__)


# ── Models ────────────────────────────────────────────────────────────


class ProposedChange(BaseModel, frozen=True):
    """A single proposed change to a profile."""

    change_type: str  # add_operation | remove_operation | update_version
    target: str  # operation name or field path
    description: str  # human-readable
    new_value: dict[str, Any] | None = None


class ProfileUpdateProposal(BaseModel, frozen=True):
    """A proposed update to a service profile based on drift detection."""

    service_name: str
    drift_source: str
    proposed_changes: list[ProposedChange] = Field(default_factory=list)
    auto_applicable: bool = False
    requires_review: bool = True


# ── Proposer ──────────────────────────────────────────────────────────


class ProfileUpdateProposer:
    """Generates profile update proposals from drift reports."""

    async def propose(
        self,
        profile: ServiceProfileData,
        drift: DriftReport,
    ) -> ProfileUpdateProposal:
        """Generate a proposal from a drift report.

        Structural changes (added/removed ops) are deterministic.
        The proposal describes what should change — the caller decides
        whether to apply it.
        """
        changes: list[ProposedChange] = []

        # Version change
        if drift.external_version and drift.external_version != profile.version:
            changes.append(
                ProposedChange(
                    change_type="update_version",
                    target="version",
                    description=(
                        f"Update version from {profile.version} "
                        f"to {drift.external_version}"
                    ),
                    new_value={"version": drift.external_version},
                )
            )

        # New operations in external source
        for op_name in drift.operations_added:
            changes.append(
                ProposedChange(
                    change_type="add_operation",
                    target=op_name,
                    description=f"Add operation '{op_name}' (found in {drift.source})",
                    new_value={"name": op_name},
                )
            )

        # Operations removed from external source
        for op_name in drift.operations_removed:
            changes.append(
                ProposedChange(
                    change_type="remove_operation",
                    target=op_name,
                    description=(
                        f"Remove operation '{op_name}' "
                        f"(no longer in {drift.source})"
                    ),
                )
            )

        # Auto-applicable if only version change or removals
        auto = all(
            c.change_type in ("update_version", "remove_operation")
            for c in changes
        )

        return ProfileUpdateProposal(
            service_name=profile.service_name,
            drift_source=drift.source,
            proposed_changes=changes,
            auto_applicable=auto and bool(changes),
            requires_review=not auto,
        )

    async def apply(
        self,
        profile: ServiceProfileData,
        proposal: ProfileUpdateProposal,
    ) -> ServiceProfileData:
        """Apply a proposal to create an updated profile.

        Returns a new ServiceProfileData (frozen copy with updates).
        Does NOT save to disk — caller decides whether to save.
        """
        updates: dict[str, Any] = {}
        operations = list(profile.operations)

        for change in proposal.proposed_changes:
            if change.change_type == "update_version" and change.new_value:
                updates["version"] = change.new_value.get(
                    "version", profile.version
                )

            elif change.change_type == "remove_operation":
                operations = [
                    op for op in operations if op.name != change.target
                ]

            elif change.change_type == "add_operation" and change.new_value:
                # Add a minimal operation stub
                new_op = ProfileOperation(
                    name=change.new_value.get("name", change.target),
                    service=profile.service_name,
                    description=f"Added from {proposal.drift_source} sync",
                )
                operations.append(new_op)

        updates["operations"] = operations

        # Track sync in source_chain
        source_chain = list(profile.source_chain or [])
        sync_marker = f"sync:{proposal.drift_source}"
        if sync_marker not in source_chain:
            source_chain.append(sync_marker)
        updates["source_chain"] = source_chain

        return profile.model_copy(update=updates)
