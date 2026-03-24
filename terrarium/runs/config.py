"""Configuration model for the runs subsystem."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RunConfig(BaseModel):
    """Configuration for run management.

    Attributes:
        data_dir: Base directory for run data storage.
        snapshot_on_complete: Whether to auto-snapshot when a run completes.
        snapshot_interval_ticks: Take an auto-snapshot every N ticks (0 = disabled).
        retention_days: How many days to retain run data before cleanup.
    """

    model_config = ConfigDict(frozen=True)

    data_dir: str = "data/runs"
    snapshot_on_complete: bool = True
    snapshot_interval_ticks: int = 0
    retention_days: int = 30
