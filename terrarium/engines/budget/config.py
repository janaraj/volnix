"""Configuration model for the budget engine."""

from __future__ import annotations

from pydantic import BaseModel


class BudgetConfig(BaseModel):
    """Configuration for the budget engine."""

    warning_threshold_pct: float = 80.0
    critical_threshold_pct: float = 95.0
