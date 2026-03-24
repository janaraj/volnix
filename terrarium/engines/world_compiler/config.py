"""Configuration model for the world compiler engine."""

from __future__ import annotations

from pydantic import BaseModel


class WorldCompilerConfig(BaseModel):
    """Configuration for the world compiler engine."""

    default_seed: int = 42
    max_entities_per_type: int = 1000
    max_section_retries: int = 2
    collect_all_validation_errors: bool = True
