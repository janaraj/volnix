"""State machine definitions for email entities.

Defines valid status transitions for legacy email entities.

NOTE: Gmail uses labels (INBOX, SENT, TRASH, UNREAD, STARRED, etc.) as
its state mechanism rather than explicit status-based state machines.
The Gmail-aligned handlers manipulate ``labelIds`` arrays on message
entities.  The transitions below are retained for backward compatibility
with the legacy ``email_*`` handlers which use a ``status`` field.
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
