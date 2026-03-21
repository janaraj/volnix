"""Configuration model for the world animator engine."""

from __future__ import annotations

from pydantic import BaseModel


class AnimatorConfig(BaseModel):
    """Configuration for the world animator engine."""

    creativity_budget: int
    intensity: str
    enabled: bool
