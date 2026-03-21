"""State machine definitions for payment entities."""

from __future__ import annotations

CHARGE_STATES: list[str] = ["pending", "succeeded", "failed", "refunded", "disputed"]

CHARGE_TRANSITIONS: dict[str, list[str]] = {
    "pending": ["succeeded", "failed"],
    "succeeded": ["refunded", "disputed"],
    "failed": [],
    "refunded": [],
    "disputed": ["succeeded", "refunded"],
}

REFUND_STATES: list[str] = ["pending", "succeeded", "failed"]

REFUND_TRANSITIONS: dict[str, list[str]] = {
    "pending": ["succeeded", "failed"],
    "succeeded": [],
    "failed": [],
}
