"""State machine definitions for browser pack entities.

Defines valid status transitions for web pages and browser sessions.
"""

from __future__ import annotations

WEB_PAGE_STATES: list[str] = ["draft", "published", "archived", "compromised"]

WEB_PAGE_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["published"],
    "published": ["archived", "compromised"],
    "compromised": ["published"],
    "archived": ["published"],
}

WEB_SESSION_STATES: list[str] = ["active", "expired"]

WEB_SESSION_TRANSITIONS: dict[str, list[str]] = {
    "active": ["expired"],
    "expired": [],
}
