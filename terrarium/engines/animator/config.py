"""Configuration model for the world animator engine."""

from __future__ import annotations

from pydantic import BaseModel


class AnimatorConfig(BaseModel):
    """Configuration for the world animator engine."""

    creativity_budget: float = 0.3
    intensity: float = 0.5
    enabled: bool = True
