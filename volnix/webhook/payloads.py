"""Webhook payload formatters — transform events to service-specific shapes.

Plugin pattern: each service can register a formatter function.
Adding a new format = one function + one line in PAYLOAD_FORMATTERS.

If no service-specific formatter exists, the raw Volnix event
envelope is used.
"""
from __future__ import annotations

import base64
import json
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def format_payload(event: Any, service: str = "") -> dict[str, Any]:
    """Format an event for webhook delivery.

    Uses service-specific formatter if available, otherwise
    returns the default Volnix event envelope.
    """
    formatter = PAYLOAD_FORMATTERS.get(service)
    if formatter:
        try:
            return formatter(event)
        except Exception as exc:
            logger.warning(
                "Formatter for '%s' failed: %s — using default",
                service, exc,
            )
    return _default_format(event)


def _default_format(event: Any) -> dict[str, Any]:
    """Default Volnix event envelope.

    M5 fix: falls back to vars() then str() for non-Pydantic events.
    """
    data: dict[str, Any] = {}
    if hasattr(event, "model_dump"):
        try:
            data = event.model_dump(mode="json")
        except Exception:
            data = {"raw": str(event)}
    else:
        try:
            data = dict(vars(event))
        except Exception:
            data = {"raw": str(event)}

    return {
        "source": "volnix",
        "event_type": str(getattr(event, "event_type", "unknown")),
        "event_id": str(getattr(event, "event_id", "")),
        "timestamp": str(getattr(event, "timestamp", "")),
        "data": data,
    }


def _gmail_format(event: Any) -> dict[str, Any]:
    """Gmail Pub/Sub notification shape.

    Real Gmail sends::

        {"message": {"data": "<base64>", "messageId": "...",
                      "publishTime": "..."}, "subscription": "..."}
    """
    data = {}
    if hasattr(event, "model_dump"):
        data = event.model_dump(mode="json")

    encoded = base64.b64encode(
        json.dumps(data, default=str).encode()
    ).decode()

    return {
        "message": {
            "data": encoded,
            "messageId": str(getattr(event, "event_id", "")),
            "publishTime": str(getattr(event, "timestamp", "")),
        },
        "subscription": "volnix-simulated",
    }


def _slack_format(event: Any) -> dict[str, Any]:
    """Slack Events API shape.

    M4 fix: includes required fields (team_id, api_app_id, channel,
    user, event_ts) that real Slack sends.
    """
    input_data = getattr(event, "input_data", {}) or {}
    ts = str(getattr(event, "timestamp", ""))

    return {
        "type": "event_callback",
        "token": "volnix-simulated",
        "team_id": "T-simulated",
        "api_app_id": "A-simulated",
        "event": {
            "type": str(getattr(event, "action", "message")),
            "channel": input_data.get("channel", "C-simulated"),
            "user": input_data.get("user", "U-simulated"),
            "ts": ts,
            "event_ts": ts,
            "text": str(input_data.get("body", "")),
        },
    }


def _stripe_format(event: Any) -> dict[str, Any]:
    """Stripe webhook event shape.

    M3 fix: correct event type format.
    Real Stripe uses ``"charge.created"`` (resource.past_tense_verb).
    We parse ``"stripe_create_charge"`` → ``"charge.created"``.
    """
    data = {}
    if hasattr(event, "model_dump"):
        try:
            data = event.model_dump(mode="json")
        except Exception:
            data = {}

    action = str(getattr(event, "action", "unknown"))

    # Parse action: "stripe_create_charge" → verb="create", resource="charge"
    parts = action.replace("stripe_", "").split("_", 1)
    verb = parts[0] if parts else "unknown"
    resource = parts[1] if len(parts) > 1 else "event"

    # Map verb to past tense (Stripe convention)
    verb_map = {
        "create": "created",
        "update": "updated",
        "delete": "deleted",
        "list": "listed",
        "get": "retrieved",
        "refund": "refunded",
        "cancel": "canceled",
        "capture": "captured",
    }
    past_verb = verb_map.get(verb, verb)
    stripe_event_type = f"{resource}.{past_verb}"

    return {
        "id": f"evt_{getattr(event, 'event_id', 'sim')}",
        "object": "event",
        "type": stripe_event_type,
        "data": {"object": data.get("response_body", data)},
        "livemode": False,
    }


# ---------------------------------------------------------------------------
# Formatter registry — add new services here
# ---------------------------------------------------------------------------

PAYLOAD_FORMATTERS: dict[str, Callable[..., dict[str, Any]]] = {
    "email": _gmail_format,
    "gmail": _gmail_format,
    "chat": _slack_format,
    "slack": _slack_format,
    "payments": _stripe_format,
    "stripe": _stripe_format,
}
