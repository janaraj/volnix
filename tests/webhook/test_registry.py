"""Tests for WebhookRegistry — subscription storage and matching."""
from __future__ import annotations

import pytest


def test_register_returns_id(registry):
    """Register returns a subscription ID."""
    sub_id = registry.register(
        url="http://agent:3000/hook", events=["world.*"]
    )
    assert sub_id.startswith("wh_")


def test_unregister_removes(registry):
    """Unregister removes the subscription."""
    sub_id = registry.register(
        url="http://agent:3000/hook", events=["world.*"]
    )
    assert registry.unregister(sub_id) is True
    assert registry.count() == 0


def test_unregister_nonexistent(registry):
    """Unregister nonexistent ID returns False."""
    assert registry.unregister("wh_nonexistent") is False


def test_match_exact(registry):
    """Exact event pattern matches."""
    registry.register(
        url="http://agent:3000/hook", events=["world.email_send"]
    )
    matches = registry.match("world.email_send")
    assert len(matches) == 1
    assert matches[0].url == "http://agent:3000/hook"


def test_match_wildcard(registry):
    """Wildcard pattern matches multiple events."""
    registry.register(
        url="http://agent:3000/hook", events=["world.email_*"]
    )
    assert len(registry.match("world.email_send")) == 1
    assert len(registry.match("world.email_read")) == 1
    assert len(registry.match("world.chat_send")) == 0


def test_match_service_filter(registry):
    """Service filter narrows matches."""
    registry.register(
        url="http://agent:3000/hook",
        events=["world.*"],
        service="email",
    )
    assert len(registry.match("world.email_send", "email")) == 1
    assert len(registry.match("world.email_send", "chat")) == 0


def test_max_registrations(registry):
    """Exceeding max registrations raises ValueError."""
    for i in range(10):
        registry.register(
            url=f"http://agent:3000/hook{i}",
            events=["world.*"],
        )
    with pytest.raises(ValueError, match="Maximum"):
        registry.register(
            url="http://agent:3000/hook11", events=["world.*"]
        )


def test_empty_url_rejected(registry):
    """Empty URL raises ValueError."""
    with pytest.raises(ValueError, match="empty"):
        registry.register(url="", events=["world.*"])


def test_list_all(registry):
    """list_all returns all active subscriptions."""
    registry.register(url="http://a:1/h", events=["world.*"])
    registry.register(url="http://b:2/h", events=["world.*"])
    assert len(registry.list_all()) == 2


# -- SSRF prevention tests (C1) ---


def test_private_ip_rejected(registry):
    """C1: Private IP URLs rejected."""
    with pytest.raises(ValueError, match="private"):
        registry.register(
            url="http://10.0.0.1:8080/hook", events=["world.*"]
        )


def test_loopback_rejected(registry):
    """C1: Loopback URLs rejected."""
    with pytest.raises(ValueError, match="loopback"):
        registry.register(
            url="http://127.0.0.1/hook", events=["world.*"]
        )


def test_metadata_url_rejected(registry):
    """C1: Cloud metadata URLs rejected."""
    with pytest.raises(ValueError, match="Blocked"):
        registry.register(
            url="http://169.254.169.254/latest/meta-data/",
            events=["world.*"],
        )


def test_localhost_rejected(registry):
    """C1: localhost hostname rejected."""
    with pytest.raises(ValueError, match="Blocked"):
        registry.register(
            url="http://localhost:6379/", events=["world.*"]
        )


def test_file_scheme_rejected(registry):
    """C1: file:// scheme rejected."""
    with pytest.raises(ValueError, match="scheme"):
        registry.register(
            url="file:///etc/passwd", events=["world.*"]
        )


def test_internal_domain_rejected(registry):
    """C1: .internal domains rejected."""
    with pytest.raises(ValueError, match=".internal"):
        registry.register(
            url="http://metadata.google.internal/",
            events=["world.*"],
        )
