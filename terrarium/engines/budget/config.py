"""Configuration model for the budget engine."""

from __future__ import annotations

from pydantic import BaseModel


class BudgetConfig(BaseModel):
    """Configuration for the budget engine."""

    warning_threshold_pct: float
    critical_threshold_pct: float
