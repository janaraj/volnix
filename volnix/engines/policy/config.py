"""Configuration model for the policy engine."""

from __future__ import annotations

from pydantic import BaseModel


class PolicyConfig(BaseModel):
    """Configuration for the policy engine."""

    condition_timeout_ms: int = 500
    max_policies_per_action: int = 50
    hold_expiry_check_interval_seconds: float = 60.0
    hold_default_timeout_seconds: float = 1800.0
