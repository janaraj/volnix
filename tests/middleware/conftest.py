"""Test harness for API surface middleware."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from volnix.middleware.config import MiddlewareConfig


@pytest.fixture
def auth_config():
    """Config with auth enabled and sample rules."""
    return MiddlewareConfig(
        auth_enabled=True,
        status_codes_enabled=False,
        auth_rules={
            "stripe": "Bearer sk_.*",
            "slack": "Bearer xoxb-.*",
        },
        service_prefixes={
            "stripe": "/stripe",
            "slack": "/slack/api",
        },
    )


@pytest.fixture
def status_config():
    """Config with status codes enabled."""
    return MiddlewareConfig(
        auth_enabled=False,
        status_codes_enabled=True,
    )


@pytest.fixture
def prefix_config():
    """Config with prefixes enabled."""
    return MiddlewareConfig(
        prefixes_enabled=True,
        service_prefixes={
            "stripe": "/stripe",
            "slack": "/slack/api",
        },
    )


@pytest.fixture
def mock_gateway():
    """Mock gateway for middleware tests."""
    gw = MagicMock()
    gw.get_tool_manifest = AsyncMock(return_value=[
        {
            "method": "POST",
            "path": "/v1/charges",
            "tool_name": "stripe_create_charge",
        },
        {
            "method": "GET",
            "path": "/v1/charges/{id}",
            "tool_name": "stripe_get_charge",
        },
    ])
    gw.handle_request = AsyncMock(return_value={
        "id": "ch_123",
        "object": "charge",
    })

    mock_app = MagicMock()
    mock_app.bus = MagicMock()
    mock_app.bus.subscribe = AsyncMock()
    mock_app._config = MagicMock()
    mock_app._config.middleware = MiddlewareConfig()
    mock_app.read_entities = AsyncMock(return_value={})
    gw._app = mock_app
    return gw
