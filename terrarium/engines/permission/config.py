"""Configuration model for the permission engine."""

from __future__ import annotations

from pydantic import BaseModel


class PermissionConfig(BaseModel):
    """Configuration for the permission engine."""

    cache_ttl_seconds: int
