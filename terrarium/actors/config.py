"""Configuration models for the actor system.

These Pydantic models map to the ``[actors]`` section of the Terrarium
TOML configuration file.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ActorConfig(BaseModel):
    """Top-level actor configuration section."""

    default_agent_budget: dict[str, Any] = Field(default_factory=dict)
    default_human_response_time: str = "5m"
