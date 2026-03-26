"""External sync checker -- orchestrates drift detection + update proposals.

Ties together :class:`DriftDetector` and :class:`ProfileUpdateProposer`
to provide a single interface for checking and updating profiles.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from terrarium.engines.feedback.drift import DriftDetector, DriftReport
from terrarium.engines.feedback.proposer import (
    ProfileUpdateProposal,
    ProfileUpdateProposer,
)
from terrarium.packs.profile_schema import ServiceProfileData

logger = logging.getLogger(__name__)


class ExternalSyncChecker:
    """Checks profiled services for external API drift.

    Orchestrates drift detection across all registered sources
    and generates update proposals when drift is found.
    """

    def __init__(
        self,
        drift_detector: DriftDetector,
        proposer: ProfileUpdateProposer,
        profile_registry: Any,  # ProfileRegistry
        profile_loader: Any,    # ProfileLoader
    ) -> None:
        self._detector = drift_detector
        self._proposer = proposer
        self._registry = profile_registry
        self._loader = profile_loader

    async def check_drift(
        self, service_name: str
    ) -> list[DriftReport]:
        """Check a single service for drift against all sources.

        Returns list of DriftReports (empty if no drift).
        """
        profile = self._registry.get_profile(service_name)
        if profile is None:
            logger.warning(
                "No profile found for '%s' — skipping sync",
                service_name,
            )
            return []

        return await self._detector.check(profile)

    async def check_all(
        self, max_concurrent: int = 5
    ) -> list[DriftReport]:
        """Check ALL profiled services for drift.

        Returns combined list of all drift reports found.
        """
        all_profiles = self._registry.list_profiles()
        if not all_profiles:
            return []

        semaphore = asyncio.Semaphore(max_concurrent)
        all_reports: list[DriftReport] = []

        async def _check_one(
            profile: ServiceProfileData,
        ) -> list[DriftReport]:
            async with semaphore:
                return await self._detector.check(profile)

        tasks = [_check_one(p) for p in all_profiles]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_reports.extend(result)
            elif isinstance(result, Exception):
                logger.warning("Sync check failed: %s", result)

        return all_reports

    async def propose_update(
        self, service_name: str
    ) -> ProfileUpdateProposal | None:
        """Check drift + propose update for a service.

        Returns None if no drift detected.
        """
        reports = await self.check_drift(service_name)
        if not reports:
            return None

        profile = self._registry.get_profile(service_name)
        if profile is None:
            return None

        # M2 fix: merge all drift reports into one proposal
        # Use the report with the most changes as primary
        primary = max(
            reports,
            key=lambda r: (
                len(r.operations_added) + len(r.operations_removed)
            ),
        )
        return await self._proposer.propose(profile, primary)

    async def apply_update(
        self,
        service_name: str,
        proposal: ProfileUpdateProposal,
    ) -> ServiceProfileData:
        """Apply a proposed update: create new profile, save, register."""
        profile = self._registry.get_profile(service_name)
        if profile is None:
            raise ValueError(f"No profile found for '{service_name}'")

        updated = await self._proposer.apply(profile, proposal)

        # Save to disk
        if self._loader:
            await asyncio.to_thread(self._loader.save, updated)

        # Register in shared registry
        if self._registry:
            self._registry.register(updated)

        logger.info(
            "Applied sync update to '%s' (%d changes)",
            service_name,
            len(proposal.proposed_changes),
        )

        return updated
