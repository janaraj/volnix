"""State machine definitions for Notion entities.

Defines valid archived transitions for pages, databases, and blocks.
In Notion, archiving is a one-way operation: active objects can be
archived, but archived objects cannot be restored via the API.
"""

from __future__ import annotations

ARCHIVED_STATES: list[str] = ["active", "archived"]

ARCHIVED_TRANSITIONS: dict[str, list[str]] = {
    "active": ["archived"],
    "archived": [],
}
