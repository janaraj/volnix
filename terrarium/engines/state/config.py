"""Configuration model for the state engine."""

from __future__ import annotations

from pydantic import BaseModel


class StateConfig(BaseModel):
    """Configuration for the state engine."""

    db_path: str
    snapshot_dir: str
