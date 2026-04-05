"""Drift detection -- compare profiles against external API sources.

Two extension points via the ``DriftSource`` protocol:
- ``ContextHubDriftSource`` — compares against Context Hub curated docs
- ``OpenAPIDriftSource`` — compares against OpenAPI spec files

To add a new source (e.g., MCP manifest):
1. Create a class implementing ``DriftSource``
2. Register it in ``DRIFT_SOURCE_REGISTRY``
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from volnix.packs.profile_schema import ServiceProfileData

logger = logging.getLogger(__name__)


# ── Models ────────────────────────────────────────────────────────────


class DriftReport(BaseModel, frozen=True):
    """Result of comparing a profile against one external source."""

    service_name: str
    checked_at: str
    source: str  # "context_hub" | "openapi"
    has_drift: bool
    profile_version: str
    external_version: str | None = None
    operations_added: list[str] = Field(default_factory=list)
    operations_removed: list[str] = Field(default_factory=list)
    operations_changed: list[str] = Field(default_factory=list)
    content_hash_changed: bool = False
    summary: str = ""


# ── Protocol ──────────────────────────────────────────────────────────


@runtime_checkable
class DriftSource(Protocol):
    """Protocol for a drift detection source.

    Implement ``check()`` to compare a profile against your source.
    """

    source_name: str

    async def check(
        self, profile: ServiceProfileData
    ) -> DriftReport | None:
        """Check for drift. Return report if found, None if in sync."""
        ...


# ── Built-in sources ─────────────────────────────────────────────────


class ContextHubDriftSource:
    """Detects drift by comparing profile ops against Context Hub docs."""

    source_name = "context_hub"

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    async def check(
        self, profile: ServiceProfileData
    ) -> DriftReport | None:
        """Fetch latest Context Hub docs and compare operations."""
        if self._provider is None:
            return None
        if not await self._provider.is_available():
            return None

        data = await self._provider.fetch(profile.service_name)
        if data is None:
            return None

        content = data.get("raw_content", "")
        if not content:
            return None

        # Extract operation-like patterns from markdown
        # Look for HTTP method + path: GET /v1/something, POST /api/...
        external_ops = _extract_operations_from_markdown(content)
        profile_ops = {op.name for op in profile.operations}

        added, removed = _diff_operations(profile_ops, external_ops)

        has_drift = bool(added or removed)

        if not has_drift:
            return None

        summary_parts = []
        if added:
            summary_parts.append(f"{len(added)} new ops in docs")
        if removed:
            summary_parts.append(f"{len(removed)} ops no longer in docs")

        return DriftReport(
            service_name=profile.service_name,
            checked_at=datetime.now(UTC).isoformat(),
            source=self.source_name,
            has_drift=True,
            profile_version=profile.version,
            operations_added=sorted(added),
            operations_removed=sorted(removed),
            content_hash_changed=True,
            summary="; ".join(summary_parts),
        )


class OpenAPIDriftSource:
    """Detects drift by comparing profile against an OpenAPI spec."""

    source_name = "openapi"

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    async def check(
        self, profile: ServiceProfileData
    ) -> DriftReport | None:
        """Fetch OpenAPI spec and compare version + operations."""
        if self._provider is None:
            return None
        if not await self._provider.supports(profile.service_name):
            return None

        spec = await self._provider.fetch(profile.service_name)
        if spec is None:
            return None

        external_version = spec.get("version", "")
        external_op_names = {
            op.get("name", "") for op in spec.get("operations", [])
        }
        profile_op_names = {op.name for op in profile.operations}

        added, removed = _diff_operations(
            profile_op_names, external_op_names
        )
        version_changed = (
            bool(external_version)
            and external_version != profile.version
        )

        has_drift = bool(added or removed or version_changed)
        if not has_drift:
            return None

        summary_parts = []
        if version_changed:
            summary_parts.append(
                f"version {profile.version} → {external_version}"
            )
        if added:
            summary_parts.append(f"{len(added)} new ops")
        if removed:
            summary_parts.append(f"{len(removed)} removed ops")

        return DriftReport(
            service_name=profile.service_name,
            checked_at=datetime.now(UTC).isoformat(),
            source=self.source_name,
            has_drift=True,
            profile_version=profile.version,
            external_version=external_version or None,
            operations_added=sorted(added),
            operations_removed=sorted(removed),
            summary="; ".join(summary_parts),
        )


# ── Registry ─────────────────────────────────────────────────────────

DRIFT_SOURCE_REGISTRY: dict[str, type] = {
    "context_hub": ContextHubDriftSource,
    "openapi": OpenAPIDriftSource,
}


# ── Detector (orchestrator) ──────────────────────────────────────────


class DriftDetector:
    """Runs all registered drift sources against a profile.

    M8 fix: uses DRIFT_SOURCE_REGISTRY for source instantiation.
    To add a new source: create class, add to DRIFT_SOURCE_REGISTRY.
    """

    def __init__(
        self,
        providers: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with provider instances keyed by source name.

        Args:
            providers: Map of source_name → provider instance.
                Only sources present in DRIFT_SOURCE_REGISTRY AND
                in this dict will be active.
        """
        self._sources: list[Any] = []
        providers = providers or {}
        for source_name, source_cls in DRIFT_SOURCE_REGISTRY.items():
            provider = providers.get(source_name)
            if provider is not None:
                self._sources.append(source_cls(provider))

    async def check(
        self, profile: ServiceProfileData
    ) -> list[DriftReport]:
        """Check profile against ALL registered sources.

        Returns list of DriftReports (one per source that found drift).
        Empty list means no drift detected.
        """
        reports: list[DriftReport] = []
        for source in self._sources:
            try:
                report = await source.check(profile)
                if report is not None:
                    reports.append(report)
            except Exception as exc:
                logger.warning(
                    "Drift check failed for '%s' source '%s': %s",
                    profile.service_name,
                    source.source_name,
                    exc,
                )
        return reports


# ── Helpers ───────────────────────────────────────────────────────────

# Pattern to extract HTTP operations from markdown docs
_HTTP_OP_RE = re.compile(
    r"(GET|POST|PUT|PATCH|DELETE)\s+(/\S+)",
    re.IGNORECASE,
)


def _extract_operations_from_markdown(content: str) -> set[str]:
    """Extract operation-like patterns from markdown content.

    Looks for HTTP method + path pairs and normalizes them.
    """
    ops: set[str] = set()
    for match in _HTTP_OP_RE.finditer(content):
        method = match.group(1).upper()
        path = match.group(2).rstrip(")")
        ops.add(f"{method} {path}")
    return ops


def _diff_operations(
    profile_ops: set[str], external_ops: set[str]
) -> tuple[list[str], list[str]]:
    """Return (added, removed) operation names.

    added = in external but not in profile
    removed = in profile but not in external
    """
    added = sorted(external_ops - profile_ops)
    removed = sorted(profile_ops - external_ops)
    return added, removed
