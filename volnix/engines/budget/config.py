"""Configuration model for the budget engine."""

from __future__ import annotations

from pydantic import BaseModel


class BudgetConfig(BaseModel):
    """Configuration for the budget engine."""

    warning_threshold_pct: float = 80.0
    critical_threshold_pct: float = 95.0
    track_api_calls: bool = True
    track_world_actions: bool = True
    track_llm_spend: bool = True
    track_spend_usd: bool = True
    track_time: bool = True
