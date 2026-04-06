"""Test harness for webhook module."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from volnix.webhook.config import WebhookConfig
from volnix.webhook.manager import WebhookManager
from volnix.webhook.registry import WebhookRegistry


@pytest.fixture
def webhook_config():
    """Config with webhooks enabled, fast retries for testing."""
    return WebhookConfig(
        enabled=True,
        max_retries=1,
        retry_backoff_base=0.01,  # fast for tests
        delivery_timeout=2.0,
        max_registrations=10,
    )


@pytest.fixture
def registry():
    """Fresh webhook registry."""
    return WebhookRegistry(max_registrations=10)


@pytest.fixture
def webhook_manager(webhook_config):
    """WebhookManager with test config."""
    return WebhookManager(webhook_config)


@pytest.fixture
def mock_bus():
    """Mock event bus."""
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    bus.unsubscribe = AsyncMock()
    return bus


@pytest.fixture
def sample_event():
    """Minimal event-like object for testing."""

    class FakeEvent:
        event_type = "world.email_send"
        event_id = "evt-123"
        service_id = "gmail"
        action = "email_send"
        timestamp = datetime.now(UTC).isoformat()
        input_data = {"to": "a@b.com", "body": "hello"}

        def model_dump(self, mode: str = "json") -> dict[str, Any]:
            return {
                "event_type": self.event_type,
                "event_id": self.event_id,
                "service_id": self.service_id,
                "action": self.action,
                "input_data": self.input_data,
            }

    return FakeEvent()
