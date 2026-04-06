"""Configuration model for the agent adapter engine."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AdapterConfig(BaseModel):
    """Configuration for the agent adapter engine."""

    protocols: list[str] = Field(default_factory=lambda: ["mcp", "http"])
    host: str = "0.0.0.0"
    port: int = 8100
