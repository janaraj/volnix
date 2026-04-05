"""Middleware configuration model."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MiddlewareConfig(BaseModel, frozen=True):
    """Configuration for API surface middleware.

    All middleware is OFF by default for backward compatibility.
    Service-specific rules are data (TOML config), not code.

    Attributes:
        auth_enabled: Enable auth token shape validation.
        status_codes_enabled: Map response errors to HTTP status codes.
        prefixes_enabled: Mount service-prefixed URL aliases.
        auth_rules: Per-service regex patterns for Authorization header.
            Key = service name, value = regex (e.g., ``"Bearer sk_.*"``).
        service_prefixes: Per-service URL prefixes.
            Key = service name, value = prefix (e.g., ``"/stripe"``).
    """

    auth_enabled: bool = False
    status_codes_enabled: bool = True
    prefixes_enabled: bool = False
    auth_rules: dict[str, str] = Field(default_factory=dict)
    service_prefixes: dict[str, str] = Field(default_factory=dict)
