"""Configuration models for the reality system.

These Pydantic models map to the ``[reality]`` and ``[seeds]`` sections
of the Terrarium TOML configuration file.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RealityConfig(BaseModel):
    """Top-level reality configuration section."""

    preset: str = "realistic"              # pristine | realistic | harsh
    overrides: dict[str, Any] = Field(default_factory=dict)
    overlays: list[str] = Field(default_factory=list)


class SeedConfig(BaseModel):
    """Configuration for a single seed entry."""

    description: str
    customer: dict[str, Any] | None = None
    charge: dict[str, Any] | None = None
    ticket: dict[str, Any] | None = None
