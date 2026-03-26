"""Tier promotion logic -- evaluates and executes fidelity tier changes.

Promotion criteria (ALL configurable via FeedbackConfig):
1. At least promotion_min_annotations human annotations
2. At least promotion_min_operations observed in capture
3. Error rate <= promotion_max_error_rate
4. Has entity mutations observed

The standard promotion path:
  bootstrapped → curated_profile (Tier 2)
  curated_profile → verified_pack (Tier 1, via compile-pack + verify)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from terrarium.engines.feedback.annotations import AnnotationStore
from terrarium.engines.feedback.config import FeedbackConfig
from terrarium.engines.feedback.models import (
    CapturedSurface,
    PromotionEvaluation,
    PromotionResult,
)
from terrarium.packs.profile_schema import ServiceProfileData

logger = logging.getLogger(__name__)


class TierPromoter:
    """Evaluates and proposes fidelity tier promotions for services."""

    def __init__(
        self,
        annotation_store: AnnotationStore,
        profile_registry: Any,  # ProfileRegistry
        profile_loader: Any,    # ProfileLoader
        config: FeedbackConfig | None = None,
    ) -> None:
        self._annotations = annotation_store
        self._registry = profile_registry
        self._loader = profile_loader
        self._config = config or FeedbackConfig()

    async def evaluate_candidate(
        self,
        service_name: str,
        captured: CapturedSurface,
    ) -> PromotionEvaluation:
        """Evaluate whether a service is ready for tier promotion.

        All thresholds come from ``FeedbackConfig`` — nothing hardcoded.
        """
        name = service_name.lower()
        criteria_met: list[str] = []
        criteria_missing: list[str] = []

        # Get current profile
        profile = (
            self._registry.get_profile(name) if self._registry else None
        )
        current_fidelity = (
            profile.fidelity_source if profile else captured.fidelity_source
        )

        # Already curated — nothing to promote to
        if current_fidelity == "curated_profile":
            return PromotionEvaluation(
                service_name=name,
                eligible=False,
                current_fidelity=current_fidelity,
                proposed_fidelity=current_fidelity,
                criteria_met=["Already curated"],
                criteria_missing=[],
                recommendation=(
                    "Service is already a curated profile. "
                    "Use compile-pack for Tier 1."
                ),
            )

        # Criterion 1: Annotation count (from config)
        annotation_count = await self._annotations.count_by_service(name)
        min_ann = self._config.promotion_min_annotations
        if annotation_count >= min_ann:
            criteria_met.append(
                f"Annotations: {annotation_count} >= {min_ann}"
            )
        else:
            criteria_missing.append(
                f"Annotations: {annotation_count} < {min_ann} required"
            )

        # Criterion 2: Operations count (from config — C3 fix)
        op_count = len(captured.operations_observed)
        min_ops = self._config.promotion_min_operations
        if op_count >= min_ops:
            criteria_met.append(f"Operations: {op_count} >= {min_ops}")
        else:
            criteria_missing.append(
                f"Operations: {op_count} < {min_ops} required"
            )

        # Criterion 3: Error rate (from config — C4 fix)
        total_errors = sum(
            e.error_count for e in captured.operations_observed
        )
        total_calls = sum(
            o.call_count for o in captured.operations_observed
        )
        max_error_rate = self._config.promotion_max_error_rate
        if total_calls > 0:
            error_rate = total_errors / total_calls
            if error_rate <= max_error_rate:
                criteria_met.append(
                    f"Error rate: {error_rate:.0%} "
                    f"<= {max_error_rate:.0%}"
                )
            else:
                criteria_missing.append(
                    f"Error rate: {error_rate:.0%} "
                    f"> {max_error_rate:.0%} threshold"
                )
        else:
            criteria_missing.append("No operations observed in run")

        # Criterion 4: Has entity mutations
        if captured.entity_mutations:
            criteria_met.append(
                f"Entity mutations: "
                f"{len(captured.entity_mutations)} types"
            )
        else:
            criteria_missing.append("No entity mutations observed")

        eligible = len(criteria_missing) == 0

        recommendation = (
            f"Promote '{name}' from bootstrapped to curated_profile"
            if eligible
            else f"Not yet eligible: {'; '.join(criteria_missing)}"
        )

        return PromotionEvaluation(
            service_name=name,
            eligible=eligible,
            current_fidelity=current_fidelity,
            proposed_fidelity=(
                "curated_profile" if eligible else current_fidelity
            ),
            criteria_met=criteria_met,
            criteria_missing=criteria_missing,
            recommendation=recommendation,
            annotation_count=annotation_count,
        )

    async def promote(
        self,
        service_name: str,
        new_profile: ServiceProfileData,
    ) -> PromotionResult:
        """Execute the promotion: update fidelity_source, save, register.

        H2 fix: file I/O wrapped with asyncio.to_thread().
        """
        previous_fidelity = new_profile.fidelity_source

        # Increment version
        old_version = new_profile.version or "0.1.0"
        new_version = self._increment_version(old_version)

        # Create updated profile (frozen model — must copy)
        promoted = new_profile.model_copy(update={
            "fidelity_source": "curated_profile",
            "version": new_version,
        })

        # Save to disk (H2 fix: async file I/O)
        profile_path = ""
        if self._loader:
            saved = await asyncio.to_thread(self._loader.save, promoted)
            profile_path = str(saved)

        # Register in shared registry
        if self._registry:
            self._registry.register(promoted)

        logger.info(
            "Promoted '%s' from '%s' to 'curated_profile' (v%s)",
            service_name, previous_fidelity, new_version,
        )

        return PromotionResult(
            service_name=service_name,
            previous_fidelity=previous_fidelity,
            new_fidelity="curated_profile",
            profile_path=profile_path,
            version=new_version,
        )

    async def get_promotion_candidates(self) -> list[dict[str, Any]]:
        """List all bootstrapped services with promotion readiness."""
        if self._registry is None:
            return []

        candidates: list[dict[str, Any]] = []
        for profile in self._registry.list_profiles():
            if profile.fidelity_source == "bootstrapped":
                count = await self._annotations.count_by_service(
                    profile.service_name
                )
                candidates.append({
                    "service_name": profile.service_name,
                    "fidelity_source": profile.fidelity_source,
                    "operations": len(profile.operations),
                    "entities": len(profile.entities),
                    "annotation_count": count,
                    "min_annotations": (
                        self._config.promotion_min_annotations
                    ),
                })

        return candidates

    @staticmethod
    def _increment_version(version: str) -> str:
        """Increment version: 0.x.x → 1.0.0, 1.x.x → 1.x+1.0.

        Returns ``"1.0.0"`` for malformed version strings.
        """
        parts = version.split(".")
        if len(parts) != 3:
            return "1.0.0"
        try:
            major, minor = int(parts[0]), int(parts[1])
        except ValueError:
            return "1.0.0"
        if major == 0:
            return "1.0.0"
        return f"{major}.{minor + 1}.0"
