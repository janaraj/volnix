"""Tests for PrefixRouter — service-prefixed URL aliases."""
from __future__ import annotations

from volnix.middleware.prefix_router import mount_service_prefixes


def test_mount_returns_count():
    """mount_service_prefixes returns number of routes mounted."""
    import fastapi

    app = fastapi.FastAPI()
    routes = [
        {"path": "/v1/charges", "method": "POST",
         "tool_name": "stripe_create_charge"},
        {"path": "/v1/charges/{id}", "method": "GET",
         "tool_name": "stripe_get_charge"},
    ]
    prefixes = {"stripe": "/stripe"}

    from unittest.mock import AsyncMock, MagicMock
    gateway = MagicMock()
    gateway.handle_request = AsyncMock()

    count = mount_service_prefixes(app, routes, prefixes, gateway)
    assert count == 2


def test_no_prefixes_returns_zero():
    """Empty prefix config mounts nothing."""
    from unittest.mock import MagicMock

    import fastapi
    app = fastapi.FastAPI()
    count = mount_service_prefixes(app, [], {}, MagicMock())
    assert count == 0


def test_unmatched_service_skipped():
    """Routes for services without prefix config are skipped."""
    from unittest.mock import AsyncMock, MagicMock

    import fastapi

    app = fastapi.FastAPI()
    routes = [
        {"path": "/v1/messages", "method": "GET",
         "tool_name": "email_list"},
    ]
    # Only stripe prefix configured, not email
    prefixes = {"stripe": "/stripe"}
    gateway = MagicMock()
    gateway.handle_request = AsyncMock()

    count = mount_service_prefixes(app, routes, prefixes, gateway)
    assert count == 0
