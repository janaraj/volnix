"""Tests for webhook payload formatters."""
from __future__ import annotations

import base64
import json

from volnix.webhook.payloads import (
    PAYLOAD_FORMATTERS,
    format_payload,
)


def test_default_format(sample_event):
    """Default format wraps event in Volnix envelope."""
    payload = format_payload(sample_event)
    assert payload["source"] == "volnix"
    assert payload["event_type"] == "world.email_send"
    assert "data" in payload


def test_gmail_format(sample_event):
    """Gmail formatter produces Pub/Sub notification shape."""
    payload = format_payload(sample_event, service="gmail")
    assert "message" in payload
    assert "data" in payload["message"]
    # Data should be base64-encoded
    decoded = json.loads(
        base64.b64decode(payload["message"]["data"])
    )
    assert "event_type" in decoded
    assert payload["subscription"] == "volnix-simulated"


def test_slack_format(sample_event):
    """Slack formatter produces Events API shape."""
    payload = format_payload(sample_event, service="slack")
    assert payload["type"] == "event_callback"
    assert "event" in payload
    assert payload["event"]["type"] == "email_send"


def test_stripe_format(sample_event):
    """Stripe formatter produces webhook event shape."""
    sample_event.action = "stripe_create_charge"
    payload = format_payload(sample_event, service="stripe")
    assert payload["object"] == "event"
    assert payload["livemode"] is False
    assert "data" in payload


def test_unknown_service_uses_default(sample_event):
    """Unknown service falls back to default format."""
    payload = format_payload(sample_event, service="unknown_svc")
    assert payload["source"] == "volnix"


def test_formatter_registry():
    """Registry has expected built-in formatters."""
    assert "email" in PAYLOAD_FORMATTERS
    assert "gmail" in PAYLOAD_FORMATTERS
    assert "chat" in PAYLOAD_FORMATTERS
    assert "slack" in PAYLOAD_FORMATTERS
    assert "payments" in PAYLOAD_FORMATTERS
    assert "stripe" in PAYLOAD_FORMATTERS
