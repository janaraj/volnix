"""State machine definitions for repository entities."""

from __future__ import annotations

PR_STATES: list[str] = ["draft", "open", "approved", "changes_requested", "merged", "closed"]

PR_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["open", "closed"],
    "open": ["approved", "changes_requested", "merged", "closed"],
    "approved": ["merged", "closed"],
    "changes_requested": ["open", "closed"],
    "merged": [],
    "closed": ["open"],
}
