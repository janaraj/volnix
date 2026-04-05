"""Configuration for world storage."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WorldsConfig(BaseModel):
    """World storage configuration."""

    model_config = ConfigDict(frozen=True)
    data_dir: str = "data/worlds"
