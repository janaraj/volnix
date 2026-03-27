"""State machine definitions for payment entities.

Defines valid status transitions for payment intents, refunds, invoices,
and disputes — aligned with Stripe's payment lifecycle.
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

INVOICE_STATES: list[str] = [
    "draft",
    "open",
    "paid",
    "void",
    "uncollectible",
]

INVOICE_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["open", "void"],
    "open": ["paid", "void", "uncollectible"],
    "paid": [],
    "void": [],
    "uncollectible": [],
}

DISPUTE_STATES: list[str] = [
    "warning_needs_response",
    "warning_under_review",
    "warning_closed",
    "needs_response",
    "under_review",
    "charge_refunded",
    "won",
    "lost",
]

DISPUTE_TRANSITIONS: dict[str, list[str]] = {
    "warning_needs_response": ["warning_under_review", "warning_closed"],
    "warning_under_review": ["warning_closed"],
    "warning_closed": [],
    "needs_response": ["under_review", "charge_refunded", "won", "lost"],
    "under_review": ["won", "lost", "charge_refunded"],
    "charge_refunded": [],
    "won": [],
    "lost": [],
}
