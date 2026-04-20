"""Configuration model for the world responder engine."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ResponderConfig(BaseModel):
    """Configuration for the world responder engine."""

    model_config = ConfigDict(frozen=True)

    max_retries: int = 2
    fallback_enabled: bool = True
    profiles_dir: str = "volnix/packs/profiles"
