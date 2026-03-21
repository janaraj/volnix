"""Configuration model for the agent adapter engine."""

from __future__ import annotations

from pydantic import BaseModel


class AdapterConfig(BaseModel):
    """Configuration for the agent adapter engine."""

    protocols: list[str]
    host: str
    port: int
