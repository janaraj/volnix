"""State machine definitions for payment entities.

Defines valid status transitions for payment intents and refunds,
aligned with Stripe's payment lifecycle.
"""

from __future__ import annotations

PAYMENT_INTENT_STATES: list[str] = [
    "requires_payment_method",
    "requires_confirmation",
    "requires_action",
    "processing",
    "requires_capture",
    "succeeded",
    "canceled",
]

PAYMENT_INTENT_TRANSITIONS: dict[str, list[str]] = {
    "requires_payment_method": ["requires_confirmation", "canceled"],
    "requires_confirmation": ["requires_action", "processing", "canceled"],
    "requires_action": ["requires_confirmation", "canceled"],
    "processing": ["requires_capture", "succeeded", "canceled"],
    "requires_capture": ["succeeded", "canceled"],
    "succeeded": [],
    "canceled": [],
}

REFUND_STATES: list[str] = [
    "pending",
    "requires_action",
    "succeeded",
    "failed",
    "canceled",
]

REFUND_TRANSITIONS: dict[str, list[str]] = {
    "pending": ["succeeded", "failed", "canceled"],
    "requires_action": ["pending", "canceled"],
    "succeeded": [],
    "failed": [],
    "canceled": [],
}
