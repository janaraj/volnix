"""State machine definitions for email entities.

Defines valid status transitions for emails and threads.
"""

from __future__ import annotations

EMAIL_STATES: list[str] = ["draft", "sent", "delivered", "read", "archived", "trashed"]

EMAIL_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["sent", "trashed"],
    "sent": ["delivered", "trashed"],
    "delivered": ["read", "archived", "trashed"],
    "read": ["archived", "trashed"],
    "archived": ["read", "trashed"],
    "trashed": [],
}
