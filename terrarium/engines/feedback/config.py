"""Feedback engine configuration."""
from __future__ import annotations

from pydantic import BaseModel


class FeedbackConfig(BaseModel, frozen=True):
    """Configuration for the feedback engine.

    All promotion thresholds are configurable — no hardcoded values
    in the engine code.

    Attributes:
        external_sync_enabled: Whether external source sync is active (G4b).
        auto_annotate_gaps: Automatically annotate capability gap events.
        promotion_min_runs: Minimum runs before promotion is eligible.
        promotion_min_annotations: Minimum human annotations before eligible.
        promotion_min_operations: Minimum operations in the captured surface.
        promotion_max_error_rate: Maximum error rate (0.0-1.0) allowed.
    """

    external_sync_enabled: bool = False
    auto_annotate_gaps: bool = True
    promotion_min_runs: int = 3
    promotion_min_annotations: int = 1
    promotion_min_operations: int = 3
    promotion_max_error_rate: float = 0.3
