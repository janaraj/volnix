"""Configuration model for the feedback engine."""

from __future__ import annotations

from pydantic import BaseModel


class FeedbackConfig(BaseModel):
    """Configuration for the feedback engine."""

    annotations_db_path: str
    external_sync_enabled: bool
