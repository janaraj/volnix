"""State machine definitions for ticket entities."""

from __future__ import annotations

TICKET_STATES: list[str] = ["open", "in_progress", "pending", "escalated", "resolved", "closed"]

TICKET_TRANSITIONS: dict[str, list[str]] = {
    "open": ["in_progress", "pending", "escalated", "closed"],
    "in_progress": ["pending", "escalated", "resolved", "closed"],
    "pending": ["in_progress", "escalated", "closed"],
    "escalated": ["in_progress", "resolved", "closed"],
    "resolved": ["open", "closed"],
    "closed": ["open"],
}
