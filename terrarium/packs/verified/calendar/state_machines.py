"""State machine definitions for calendar entities."""

from __future__ import annotations

EVENT_STATES: list[str] = ["tentative", "confirmed", "cancelled"]

EVENT_TRANSITIONS: dict[str, list[str]] = {
    "tentative": ["confirmed", "cancelled"],
    "confirmed": ["cancelled"],
    "cancelled": [],
}
