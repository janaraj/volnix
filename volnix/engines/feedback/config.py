"""Feedback engine configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FeedbackConfig(BaseModel, frozen=True):
    """Configuration for the feedback engine.

    All thresholds are configurable — no hardcoded values in engine code.

    G4a fields:
        auto_annotate_gaps: Auto-annotate capability gap events.
        promotion_min_annotations: Min annotations before eligible.
        promotion_min_operations: Min operations in captured surface.
        promotion_max_error_rate: Max error rate (0.0-1.0).

    G4b fields:
        external_sync_enabled: Enable drift detection against external APIs.
        sync_check_on_startup: Check all profiles on app start.
        sync_max_concurrent: Concurrent drift checks.
        signals_enabled: Enable local signal computation.
        signals_max_runs: Max runs to scan for signals.
        signals_include_event_logs: Load event logs (heavier but more data).
        enabled_signals: Which signal collectors to run.
    """

    # G4a
    auto_annotate_gaps: bool = True
    promotion_min_annotations: int = 1
    promotion_min_operations: int = 3
    promotion_max_error_rate: float = 0.3

    # G4b — External sync
    external_sync_enabled: bool = False
    sync_check_on_startup: bool = False
    sync_max_concurrent: int = 5

    # G4b — Local signals
    signals_enabled: bool = True
    signals_max_runs: int = 100
    signals_include_event_logs: bool = True
    enabled_signals: list[str] = Field(
        default_factory=lambda: [
            "service_usage",
            "bootstrap_failures",
            "capability_gaps",
            "template_insights",
        ]
    )
