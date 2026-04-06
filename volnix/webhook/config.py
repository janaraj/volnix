"""Webhook delivery configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WebhookConfig(BaseModel, frozen=True):
    """Configuration for webhook event delivery.

    Disabled by default. All values configurable via volnix.toml.

    Attributes:
        enabled: Enable webhook delivery.
        max_retries: Retry attempts on 5xx/connection failure.
        retry_backoff_base: Base delay seconds (doubles each retry).
        delivery_timeout: Per-request timeout seconds.
        max_registrations: Maximum number of subscriptions.
        admin_token: If set, webhook CRUD requires this Bearer token.
            Empty = no auth on webhook endpoints.
    """

    enabled: bool = False
    max_retries: int = Field(default=3, ge=0)
    retry_backoff_base: float = Field(default=1.0, gt=0)
    delivery_timeout: float = Field(default=10.0, gt=0)
    max_registrations: int = Field(default=100, gt=0)
    admin_token: str = ""
