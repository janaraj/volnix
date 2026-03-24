"""State machine definitions for Zendesk ticket entities.

Defines valid status transitions following the Zendesk ticket lifecycle.
"""

from __future__ import annotations

TICKET_STATES: list[str] = ["new", "open", "pending", "hold", "solved", "closed"]

TICKET_TRANSITIONS: dict[str, list[str]] = {
    "new": ["open", "pending", "hold", "solved"],
    "open": ["pending", "hold", "solved"],
    "pending": ["open", "hold", "solved"],
    "hold": ["open", "pending", "solved"],
    "solved": ["open", "closed"],
    "closed": [],
}
