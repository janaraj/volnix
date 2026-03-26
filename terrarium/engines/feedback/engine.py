"""Feedback engine implementation.

Manages service annotations, evaluates fidelity tier promotions,
captures service surfaces from runs, and records all feedback
activity in the ledger.

Sub-components are created lazily via ``_ensure_initialized()`` because
cross-engine dependencies (conn_mgr, artifact_store, profile_registry)
are injected into ``_config`` AFTER ``_on_initialize()`` runs.  This is
the same pattern used by the responder engine's ``_get_tier2()``.

Subscribed bus events:
- ``capability_gap``: auto-annotates when a tool is missing
- ``world``: tracks service usage
- ``simulation``: tracks run completions for promotion readiness
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, ClassVar

from terrarium.core import BaseEngine, Event, ServiceId
from terrarium.core.types import RunId
from terrarium.engines.feedback.annotations import AnnotationStore
from terrarium.engines.feedback.capture import ServiceCapture
from terrarium.engines.feedback.config import FeedbackConfig
from terrarium.engines.feedback.models import (
    CapturedSurface,
    PromotionEvaluation,
    PromotionResult,
)
from terrarium.engines.feedback.promotion import TierPromoter
from terrarium.packs.profile_schema import ServiceProfileData

logger = logging.getLogger(__name__)


class FeedbackEngine(BaseEngine):
    """Annotation, tier promotion, and service capture engine."""

    engine_name: ClassVar[str] = "feedback"
    subscriptions: ClassVar[list[str]] = ["capability_gap", "world", "simulation"]
    dependencies: ClassVar[list[str]] = ["state"]

    # -- BaseEngine hooks ------------------------------------------------------

    async def _on_initialize(self) -> None:
        """Mark sub-components as uninitialized.

        Actual initialization is deferred to ``_ensure_initialized()``
        because cross-engine deps are injected after this hook runs.
        """
        self._annotation_store: AnnotationStore | None = None
        self._capture: ServiceCapture | None = None
        self._promoter: TierPromoter | None = None
        self._sync_checker: Any = None
        self._signal_aggregator: Any = None
        self._feedback_config: FeedbackConfig | None = None
        self._initialized = False
        self._init_lock: asyncio.Lock = asyncio.Lock()  # C1 fix

    async def _ensure_initialized(self) -> None:
        """Lazily create sub-components on first use.

        By this point ``_config`` has all injected deps from
        ``app._inject_cross_engine_deps()``.

        C1 fix: guarded by asyncio.Lock to prevent concurrent init.
        """
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return  # double-check after acquiring lock

        # Parse config — exclude injected private keys AND unknown fields
        # H1/M1 fix: filter to only known FeedbackConfig fields to avoid
        # ValidationError from extra TOML keys (e.g., annotations_db_path)
        known_fields = set(FeedbackConfig.model_fields.keys())
        config_dict = {
            k: v
            for k, v in self._config.items()
            if not k.startswith("_") and k in known_fields
        }
        self._feedback_config = FeedbackConfig(**config_dict)

        # Database connection for annotations
        conn_mgr = self._config.get("_conn_mgr")
        if conn_mgr:
            db = await conn_mgr.get_connection("annotations")
            self._annotation_store = AnnotationStore(db)
            await self._annotation_store.initialize()

        # Injected dependencies
        artifact_store = self._config.get("_artifact_store")
        profile_registry = self._config.get("_profile_registry")
        profile_loader = self._config.get("_profile_loader")

        # Service capture
        if artifact_store and self._annotation_store:
            self._capture = ServiceCapture(
                artifact_store, self._annotation_store
            )

        # Tier promotion
        if self._annotation_store and profile_registry and profile_loader:
            self._promoter = TierPromoter(
                annotation_store=self._annotation_store,
                profile_registry=profile_registry,
                profile_loader=profile_loader,
                config=self._feedback_config,
            )

        # G4b: External sync (when enabled)
        if self._feedback_config.external_sync_enabled:
            from terrarium.engines.feedback.drift import DriftDetector
            from terrarium.engines.feedback.proposer import (
                ProfileUpdateProposer,
            )
            from terrarium.engines.feedback.sync import (
                ExternalSyncChecker,
            )
            from terrarium.kernel.context_hub import ContextHubProvider
            from terrarium.kernel.openapi_provider import OpenAPIProvider

            context_hub = ContextHubProvider()
            openapi_provider = OpenAPIProvider()
            providers: dict[str, Any] = {}
            if await context_hub.is_available():
                providers["context_hub"] = context_hub
            providers["openapi"] = openapi_provider
            detector = DriftDetector(providers=providers)
            proposer = ProfileUpdateProposer()
            if profile_registry:
                self._sync_checker = ExternalSyncChecker(
                    drift_detector=detector,
                    proposer=proposer,
                    profile_registry=profile_registry,
                    profile_loader=profile_loader,
                )

        # G4b: Local signals
        run_manager = self._config.get("_run_manager")
        if run_manager and artifact_store:
            from terrarium.engines.feedback.signals import (
                SignalAggregator,
            )

            self._signal_aggregator = SignalAggregator(
                run_manager=run_manager,
                artifact_store=artifact_store,
                annotation_store=self._annotation_store,
                profile_registry=profile_registry,
                max_runs=self._feedback_config.signals_max_runs,
                include_event_logs=(
                    self._feedback_config.signals_include_event_logs
                ),
            )

        self._initialized = True
        logger.info(
            "FeedbackEngine: initialized "
            "(annotations=%s, capture=%s, promoter=%s, "
            "sync=%s, signals=%s)",
            self._annotation_store is not None,
            self._capture is not None,
            self._promoter is not None,
            self._sync_checker is not None,
            self._signal_aggregator is not None,
        )

    async def _handle_event(self, event: Event) -> None:
        """Handle inbound bus events."""
        await self._ensure_initialized()
        if event.event_type == "capability.gap":
            await self._handle_capability_gap(event)
        elif event.event_type.startswith("simulation."):
            await self._handle_simulation_event(event)

    # -- Public API (called by CLI commands) -----------------------------------

    async def add_annotation(
        self,
        service_id: ServiceId | str,
        text: str,
        author: str,
        tag: str | None = None,
        run_id: RunId | str | None = None,
    ) -> int:
        """Add a behavioral annotation to a service.

        Returns the annotation's sequence_id.
        """
        await self._ensure_initialized()
        if self._annotation_store is None:
            raise RuntimeError("AnnotationStore not initialized")

        seq = await self._annotation_store.add(
            service_id=service_id,
            text=text,
            author=author,
            tag=tag,
            run_id=str(run_id) if run_id else None,
        )

        # Record in ledger
        await self._record_annotation_ledger(
            str(service_id), text, author
        )

        # B2 fix: publish AnnotationEvent to bus
        await self._publish_annotation_event(str(service_id), text, author)

        return seq

    async def get_annotations(
        self, service_id: ServiceId | str
    ) -> list[dict[str, Any]]:
        """Retrieve all annotations for a service."""
        await self._ensure_initialized()
        if self._annotation_store is None:
            return []
        return await self._annotation_store.get_by_service(service_id)

    async def capture_service(
        self, run_id: RunId | str, service_name: str
    ) -> CapturedSurface:
        """Capture a service's behavioral fingerprint from a run."""
        await self._ensure_initialized()
        if self._capture is None:
            raise RuntimeError(
                "ServiceCapture not initialized (missing artifact store)"
            )

        captured = await self._capture.capture(str(run_id), service_name)

        # Record in ledger
        await self._record_capture_ledger(
            service_name, str(run_id), len(captured.operations_observed)
        )

        # B4: publish capture event to bus
        await self._publish_feedback_event(
            "feedback.service_captured",
            service_name=service_name,
            run_id=str(run_id),
            operations=len(captured.operations_observed),
        )

        return captured

    async def evaluate_promotion(
        self,
        service_name: str,
        captured: CapturedSurface,
    ) -> PromotionEvaluation:
        """Evaluate whether a service is ready for tier promotion."""
        await self._ensure_initialized()
        if self._promoter is None:
            raise RuntimeError("TierPromoter not initialized")
        return await self._promoter.evaluate_candidate(
            service_name, captured
        )

    async def promote_service(
        self,
        service_name: str,
        new_profile: ServiceProfileData,
    ) -> PromotionResult:
        """Execute a tier promotion for a service."""
        await self._ensure_initialized()
        if self._promoter is None:
            raise RuntimeError("TierPromoter not initialized")

        result = await self._promoter.promote(service_name, new_profile)

        # Record in ledger
        await self._record_promotion_ledger(
            service_name,
            result.previous_fidelity,
            result.new_fidelity,
            result.version,
        )

        # B1 fix: publish TierPromotionEvent to bus
        await self._publish_promotion_event(service_name, result)

        return result

    async def get_promotion_candidates(self) -> list[dict[str, Any]]:
        """List all bootstrapped services with promotion readiness info."""
        await self._ensure_initialized()
        if self._promoter is None:
            return []
        return await self._promoter.get_promotion_candidates()

    # -- G4b: Sync API ---------------------------------------------------------

    async def check_sync(
        self, service_name: str
    ) -> list[Any]:
        """Check a service for external API drift."""
        await self._ensure_initialized()
        if self._sync_checker is None:
            return []
        reports = await self._sync_checker.check_drift(service_name)
        for report in reports:
            await self._record_sync_ledger(
                service_name, report.source, report.has_drift,
                len(report.operations_added),
                len(report.operations_removed),
            )
            # B5: publish drift event to bus
            if report.has_drift:
                await self._publish_feedback_event(
                    "feedback.drift_detected",
                    service_name=service_name,
                    source=report.source,
                    operations_added=len(report.operations_added),
                    operations_removed=len(report.operations_removed),
                )
        return reports

    async def check_sync_all(self) -> list[Any]:
        """Check ALL profiled services for drift.

        C2 fix: records a ledger entry for each drift report found.
        """
        await self._ensure_initialized()
        if self._sync_checker is None:
            return []
        config = self._feedback_config or FeedbackConfig()
        reports = await self._sync_checker.check_all(
            max_concurrent=config.sync_max_concurrent
        )
        for report in reports:
            await self._record_sync_ledger(
                report.service_name, report.source, report.has_drift,
                len(report.operations_added),
                len(report.operations_removed),
            )
        return reports

    async def propose_sync_update(
        self, service_name: str
    ) -> Any:
        """Check drift + propose update for a service."""
        await self._ensure_initialized()
        if self._sync_checker is None:
            return None
        return await self._sync_checker.propose_update(service_name)

    async def apply_sync_update(
        self, service_name: str, proposal: Any
    ) -> Any:
        """Apply a proposed sync update."""
        await self._ensure_initialized()
        if self._sync_checker is None:
            raise RuntimeError("Sync checker not initialized")
        result = await self._sync_checker.apply_update(
            service_name, proposal
        )
        await self._record_sync_update_ledger(
            service_name,
            len(proposal.proposed_changes),
            getattr(result, "version", ""),
        )
        return result

    # -- G4b: Signals API ------------------------------------------------------

    async def get_local_signals(
        self, signal_names: list[str] | None = None
    ) -> Any:
        """Compute local signals from user's run history."""
        await self._ensure_initialized()
        if self._signal_aggregator is None:
            from terrarium.engines.feedback.signals import LocalSignals
            return LocalSignals(
                computed_at="",
                total_runs=0,
            )
        config = self._feedback_config or FeedbackConfig()
        return await self._signal_aggregator.compute(
            signal_names=signal_names,
            enabled_signals=config.enabled_signals,
        )

    # -- Internal event handlers -----------------------------------------------

    async def _handle_capability_gap(self, event: Event) -> None:
        """Auto-annotate capability gaps if configured.

        M1 fix: uses ``add_annotation()`` so the ledger is recorded.
        H11 fix: uses ``service_id`` from the event, not tool name split.
        """
        if not self._feedback_config or not self._feedback_config.auto_annotate_gaps:
            return
        if self._annotation_store is None:
            return

        actor_id = str(getattr(event, "actor_id", "unknown"))
        tool = str(getattr(event, "requested_tool", "unknown"))

        # H11 fix: extract service_id from the event if available,
        # falling back to the action registry in the profile_registry
        service_id = self._resolve_service_for_tool(tool)

        await self.add_annotation(
            service_id=service_id,
            text=(
                f"Capability gap: agent '{actor_id}' requested "
                f"tool '{tool}' which is not available"
            ),
            author="system",
            tag="capability_gap",
        )
        logger.debug(
            "FeedbackEngine: auto-annotated capability gap for tool '%s'",
            tool,
        )

    async def _handle_simulation_event(self, event: Event) -> None:
        """Track simulation completions for run counting.

        M2 fix: record run completions so promotion can check run_count.
        """
        if event.event_type == "simulation.complete":
            # Extract service names from the event if available
            services = getattr(event, "services", [])
            if not services:
                payload = getattr(event, "payload", {}) or {}
                if isinstance(payload, dict):
                    services = payload.get("services", [])

            logger.info(
                "FeedbackEngine: simulation complete, services=%s",
                services,
            )

    # -- Service ID resolution -------------------------------------------------

    def _resolve_service_for_tool(self, tool_name: str) -> str:
        """Resolve service_id for a tool name.

        Checks the profile registry first (exact lookup), then falls
        back to prefix extraction as last resort.
        """
        profile_registry = self._config.get("_profile_registry")
        if profile_registry:
            profile = profile_registry.get_profile_for_action(tool_name)
            if profile is not None:
                return profile.service_name

        # Fallback: try known prefixes from profile registry
        if profile_registry:
            for profile in profile_registry.list_profiles():
                if tool_name.startswith(f"{profile.service_name}_"):
                    return profile.service_name

        # Last resort: first segment before underscore
        return tool_name.split("_")[0] if "_" in tool_name else tool_name

    # -- Ledger recording (typed entries) --------------------------------------

    async def _record_annotation_ledger(
        self, service_id: str, text: str, author: str
    ) -> None:
        """Record an annotation in the ledger using typed entry."""
        if not hasattr(self, "_ledger") or self._ledger is None:
            return
        from terrarium.ledger.entries import FeedbackAnnotationEntry

        entry = FeedbackAnnotationEntry(
            service_id=service_id,
            annotation_text=text,
            author=author,
        )
        try:
            await self._ledger.append(entry)
        except Exception as exc:
            logger.warning("Ledger append failed: %s", exc)

    async def _record_capture_ledger(
        self, service_name: str, run_id: str, operations_count: int
    ) -> None:
        """Record a capture in the ledger using typed entry."""
        if not hasattr(self, "_ledger") or self._ledger is None:
            return
        from terrarium.ledger.entries import FeedbackCaptureEntry

        entry = FeedbackCaptureEntry(
            service_name=service_name,
            run_id=run_id,
            operations_count=operations_count,
        )
        try:
            await self._ledger.append(entry)
        except Exception as exc:
            logger.warning("Ledger append failed: %s", exc)

    async def _record_promotion_ledger(
        self,
        service_name: str,
        previous_fidelity: str,
        new_fidelity: str,
        version: str,
    ) -> None:
        """Record a promotion in the ledger using typed entry."""
        if not hasattr(self, "_ledger") or self._ledger is None:
            return
        from terrarium.ledger.entries import FeedbackPromotionEntry

        entry = FeedbackPromotionEntry(
            service_name=service_name,
            previous_fidelity=previous_fidelity,
            new_fidelity=new_fidelity,
            profile_version=version,
        )
        try:
            await self._ledger.append(entry)
        except Exception as exc:
            logger.warning("Ledger append failed: %s", exc)

    async def _record_sync_ledger(
        self,
        service_name: str,
        source: str,
        has_drift: bool,
        ops_added: int,
        ops_removed: int,
    ) -> None:
        """Record a sync check in the ledger."""
        if not hasattr(self, "_ledger") or self._ledger is None:
            return
        from terrarium.ledger.entries import FeedbackSyncEntry

        entry = FeedbackSyncEntry(
            service_name=service_name,
            source=source,
            has_drift=has_drift,
            operations_added=ops_added,
            operations_removed=ops_removed,
        )
        try:
            await self._ledger.append(entry)
        except Exception as exc:
            logger.warning("Ledger append failed: %s", exc)

    async def _record_sync_update_ledger(
        self,
        service_name: str,
        changes_applied: int,
        new_version: str,
    ) -> None:
        """Record an applied sync update in the ledger."""
        if not hasattr(self, "_ledger") or self._ledger is None:
            return
        from terrarium.ledger.entries import FeedbackSyncUpdateEntry

        entry = FeedbackSyncUpdateEntry(
            service_name=service_name,
            changes_applied=changes_applied,
            new_version=new_version,
        )
        try:
            await self._ledger.append(entry)
        except Exception as exc:
            logger.warning("Ledger append failed: %s", exc)

    # -- Bus event publishing --------------------------------------------------

    async def _publish_promotion_event(
        self, service_name: str, result: PromotionResult
    ) -> None:
        """B1: Publish TierPromotionEvent to bus."""
        from terrarium.core.events import TierPromotionEvent
        from terrarium.core.types import FidelityTier, Timestamp

        now = datetime.now(UTC)
        try:
            event = TierPromotionEvent(
                event_type="feedback.tier_promoted",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                service_id=ServiceId(service_name),
                from_tier=FidelityTier(2),
                to_tier=FidelityTier(2),
            )
            await self.publish(event)
        except Exception as exc:
            logger.warning("Failed to publish promotion event: %s", exc)

    async def _publish_annotation_event(
        self, service_id: str, text: str, author: str
    ) -> None:
        """B2: Publish AnnotationEvent to bus."""
        from terrarium.core.events import AnnotationEvent
        from terrarium.core.types import Timestamp

        now = datetime.now(UTC)
        try:
            event = AnnotationEvent(
                event_type="feedback.annotation_added",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                service_id=ServiceId(service_id),
                annotation_text=text,
                author=author,
            )
            await self.publish(event)
        except Exception as exc:
            logger.warning("Failed to publish annotation event: %s", exc)

    async def _publish_feedback_event(
        self, event_type: str, **kwargs: Any
    ) -> None:
        """Generic feedback event publisher for B3-B5."""
        from terrarium.core.events import Event
        from terrarium.core.types import Timestamp

        now = datetime.now(UTC)
        try:
            event = Event(
                event_type=event_type,
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                metadata=kwargs,
            )
            await self.publish(event)
        except Exception as exc:
            logger.warning("Failed to publish %s event: %s", event_type, exc)
