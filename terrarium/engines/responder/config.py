"""Configuration model for the world responder engine."""

from __future__ import annotations

from pydantic import BaseModel


class ResponderConfig(BaseModel):
    """Configuration for the world responder engine."""

    max_retries: int = 2
    fallback_enabled: bool = True
    profiles_dir: str = "terrarium/packs/profiles"
