"""Configuration model for the policy engine."""

from __future__ import annotations

from pydantic import BaseModel


class PolicyConfig(BaseModel):
    """Configuration for the policy engine."""

    condition_timeout_ms: int
    max_policies_per_action: int
