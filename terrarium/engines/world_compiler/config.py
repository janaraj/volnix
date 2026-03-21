"""Configuration model for the world compiler engine."""

from __future__ import annotations

from pydantic import BaseModel


class WorldCompilerConfig(BaseModel):
    """Configuration for the world compiler engine."""

    default_seed: int
    max_entities_per_type: int
