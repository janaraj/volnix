"""State machine definitions for chat entities."""

from __future__ import annotations

CHANNEL_STATES: list[str] = ["active", "archived", "deleted"]

CHANNEL_TRANSITIONS: dict[str, list[str]] = {
    "active": ["archived", "deleted"],
    "archived": ["active", "deleted"],
    "deleted": [],
}
