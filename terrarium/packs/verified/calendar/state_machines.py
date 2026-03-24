"""State machine definitions for calendar entities.

Defines valid status transitions for calendar events and attendee responses.
"""

from __future__ import annotations

EVENT_STATES: list[str] = ["confirmed", "tentative", "cancelled"]

EVENT_TRANSITIONS: dict[str, list[str]] = {
    "confirmed": ["cancelled"],
    "tentative": ["confirmed", "cancelled"],
    "cancelled": ["confirmed"],  # can re-confirm via update
}

RESPONSE_STATUSES: list[str] = ["needsAction", "accepted", "declined", "tentative"]

RESPONSE_TRANSITIONS: dict[str, list[str]] = {
    "needsAction": ["accepted", "declined", "tentative"],
    "accepted": ["declined", "tentative"],
    "declined": ["accepted", "tentative"],
    "tentative": ["accepted", "declined"],
}
