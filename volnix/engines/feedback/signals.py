"""Signal framework -- aggregate local intelligence from user's run history.

Extension point: each signal is a plugin implementing ``SignalCollector``.
To add a new signal:
1. Create a class with ``signal_name: str`` and ``async def collect(ctx)``
2. Register it in ``SIGNAL_REGISTRY``
3. Done — the framework handles the rest

The framework loads run data ONCE into a shared ``SignalContext``,
then passes it to every registered collector.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from volnix.engines.feedback.annotations import AnnotationStore

logger = logging.getLogger(__name__)


# ── Models ────────────────────────────────────────────────────────────


class SignalContext(BaseModel, frozen=True):
    """Pre-loaded data shared across all signal collectors.

    Built once by the framework, then passed to every collector.
    """

    runs: list[dict[str, Any]] = Field(default_factory=list)
    event_logs: dict[str, list[dict[str, Any]]] = Field(
        default_factory=dict
    )
    annotation_counts: dict[str, int] = Field(default_factory=dict)
    profile_fidelities: dict[str, str] = Field(default_factory=dict)


class SignalResult(BaseModel, frozen=True):
    """Output from a single signal collector."""

    signal_name: str
    entries: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class LocalSignals(BaseModel, frozen=True):
    """All signal results combined."""

    computed_at: str
    total_runs: int
    signals: dict[str, SignalResult] = Field(default_factory=dict)


# ── Protocol ──────────────────────────────────────────────────────────


@runtime_checkable
class SignalCollector(Protocol):
    """Protocol for a signal collector plugin."""

    signal_name: str

    async def collect(self, context: SignalContext) -> SignalResult: ...


# ── Built-in collectors ──────────────────────────────────────────────


class ServiceUsageSignal:
    """Tracks which services the user uses most across runs."""

    signal_name = "service_usage"

    async def collect(self, ctx: SignalContext) -> SignalResult:
        """Count service mentions in run world_defs."""
        service_counts: Counter[str] = Counter()

        for run in ctx.runs:
            world_def = run.get("world_def", {})
            if isinstance(world_def, dict):
                services = world_def.get("services", {})
                if isinstance(services, dict):
                    service_counts.update(services.keys())
                elif isinstance(services, list):
                    service_counts.update(services)

        entries = [
            {
                "service_name": name,
                "run_count": count,
                "fidelity": ctx.profile_fidelities.get(name, "unknown"),
                "annotations": ctx.annotation_counts.get(name, 0),
            }
            for name, count in service_counts.most_common()
        ]

        return SignalResult(
            signal_name=self.signal_name,
            entries=entries,
            summary=(
                f"{len(entries)} services used across "
                f"{len(ctx.runs)} runs"
            ),
        )


class BootstrapFailureSignal:
    """Tracks bootstrapped services with high error/gap rates."""

    signal_name = "bootstrap_failures"

    async def collect(self, ctx: SignalContext) -> SignalResult:
        """Find bootstrapped services with errors in event logs."""
        error_counts: Counter[str] = Counter()
        total_counts: Counter[str] = Counter()

        for events in ctx.event_logs.values():
            for event in events:
                service = event.get("service_id", "")
                if not service:
                    continue
                total_counts[service] += 1
                if event.get("error"):
                    error_counts[service] += 1

        entries = []
        for service, total in total_counts.most_common():
            fidelity = ctx.profile_fidelities.get(service, "unknown")
            if fidelity != "bootstrapped":
                continue
            errors = error_counts.get(service, 0)
            rate = errors / total if total > 0 else 0.0
            entries.append({
                "service_name": service,
                "error_rate": round(rate, 2),
                "total_calls": total,
                "error_count": errors,
            })

        # Sort by error rate descending
        entries.sort(key=lambda e: e["error_rate"], reverse=True)

        return SignalResult(
            signal_name=self.signal_name,
            entries=entries,
            summary=f"{len(entries)} bootstrapped services with errors",
        )


class CapabilityGapSignal:
    """Tracks most-requested missing tools across runs."""

    signal_name = "capability_gaps"

    async def collect(self, ctx: SignalContext) -> SignalResult:
        """Aggregate capability gap events from all runs."""
        gap_counts: Counter[str] = Counter()

        for events in ctx.event_logs.values():
            for event in events:
                if event.get("event_type") == "capability.gap":
                    tool = event.get("requested_tool", "")
                    if tool:
                        gap_counts[tool] += 1

        entries = [
            {"tool_name": tool, "request_count": count}
            for tool, count in gap_counts.most_common()
        ]

        return SignalResult(
            signal_name=self.signal_name,
            entries=entries,
            summary=f"{len(entries)} missing tools requested",
        )


class TemplateInsightSignal:
    """Tracks which world definitions the user reuses most."""

    signal_name = "template_insights"

    async def collect(self, ctx: SignalContext) -> SignalResult:
        """Count world template reuse by name."""
        template_counts: Counter[str] = Counter()
        template_services: dict[str, set[str]] = {}

        for run in ctx.runs:
            world_def = run.get("world_def", {})
            if isinstance(world_def, dict):
                name = world_def.get("name", world_def.get(
                    "description", "unnamed"
                ))
                if name:
                    template_counts[name] += 1
                    services = world_def.get("services", {})
                    if isinstance(services, dict):
                        template_services.setdefault(name, set()).update(
                            services.keys()
                        )
                    elif isinstance(services, list):
                        template_services.setdefault(name, set()).update(
                            services
                        )

        entries = [
            {
                "template_name": name,
                "run_count": count,
                "services": sorted(template_services.get(name, set())),
            }
            for name, count in template_counts.most_common()
        ]

        return SignalResult(
            signal_name=self.signal_name,
            entries=entries,
            summary=f"{len(entries)} templates across {len(ctx.runs)} runs",
        )


# ── Registry ─────────────────────────────────────────────────────────

SIGNAL_REGISTRY: dict[str, type] = {
    "service_usage": ServiceUsageSignal,
    "bootstrap_failures": BootstrapFailureSignal,
    "capability_gaps": CapabilityGapSignal,
    "template_insights": TemplateInsightSignal,
}


# ── Aggregator (framework) ───────────────────────────────────────────


class SignalAggregator:
    """Runs all registered signal collectors against run history.

    Usage::

        aggregator = SignalAggregator(run_manager, artifact_store, ...)
        signals = await aggregator.compute()
        signals.signals["service_usage"].entries  # → [...]

    To add a new signal:
    1. Define class with ``signal_name`` + ``async collect(ctx)``
    2. Add to ``SIGNAL_REGISTRY``
    3. Done
    """

    def __init__(
        self,
        run_manager: Any,
        artifact_store: Any,
        annotation_store: AnnotationStore | None,
        profile_registry: Any | None,
        max_runs: int = 100,
        include_event_logs: bool = True,
    ) -> None:
        self._run_manager = run_manager
        self._artifacts = artifact_store
        self._annotations = annotation_store
        self._profiles = profile_registry
        self._max_runs = max_runs
        self._include_logs = include_event_logs

    async def compute(
        self,
        signal_names: list[str] | None = None,
        enabled_signals: list[str] | None = None,
    ) -> LocalSignals:
        """Compute signals.

        Args:
            signal_names: Specific signals to compute. None = all registered.
            enabled_signals: Config-driven filter. Applied after signal_names.
        """
        ctx = await self._build_context()

        # Determine which signals to run
        names = signal_names or list(SIGNAL_REGISTRY.keys())
        if enabled_signals is not None:
            names = [n for n in names if n in enabled_signals]

        results: dict[str, SignalResult] = {}
        for name in names:
            collector_cls = SIGNAL_REGISTRY.get(name)
            if collector_cls is None:
                logger.warning("Unknown signal: '%s'", name)
                continue
            try:
                collector = collector_cls()
                result = await collector.collect(ctx)
                results[name] = result
            except Exception as exc:
                logger.warning(
                    "Signal '%s' failed: %s", name, exc
                )

        return LocalSignals(
            computed_at=datetime.now(UTC).isoformat(),
            total_runs=len(ctx.runs),
            signals=results,
        )

    async def _build_context(self) -> SignalContext:
        """Load all shared data once."""
        # Runs
        runs: list[dict[str, Any]] = []
        if self._run_manager:
            runs = await self._run_manager.list_runs(
                limit=self._max_runs
            )

        # Event logs (optional, heavier — H6 fix: cap per-log size)
        max_events_per_log = 5000  # prevent unbounded memory
        event_logs: dict[str, list[dict[str, Any]]] = {}
        if self._include_logs and self._artifacts:
            for run in runs:
                run_id = run.get("run_id", "")
                if run_id:
                    try:
                        events = await self._artifacts.load_artifact(
                            run_id, "event_log"
                        )
                        if isinstance(events, list):
                            event_logs[run_id] = events[:max_events_per_log]
                    except Exception:
                        pass  # Skip runs without event logs

        # Annotation counts per service
        annotation_counts: dict[str, int] = {}
        if self._annotations and self._profiles:
            for profile in self._profiles.list_profiles():
                count = await self._annotations.count_by_service(
                    profile.service_name
                )
                annotation_counts[profile.service_name] = count

        # Profile fidelities
        profile_fidelities: dict[str, str] = {}
        if self._profiles:
            for profile in self._profiles.list_profiles():
                profile_fidelities[profile.service_name] = (
                    profile.fidelity_source
                )

        return SignalContext(
            runs=runs,
            event_logs=event_logs,
            annotation_counts=annotation_counts,
            profile_fidelities=profile_fidelities,
        )
