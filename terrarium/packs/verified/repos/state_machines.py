"""State machine definitions for repository entities.

Defines valid state transitions for issues and pull requests.
"""

from __future__ import annotations

ISSUE_STATES: list[str] = ["open", "closed"]

ISSUE_TRANSITIONS: dict[str, list[str]] = {
    "open": ["closed"],
    "closed": ["open"],
}

PULL_REQUEST_STATES: list[str] = ["open", "closed", "merged"]

PULL_REQUEST_TRANSITIONS: dict[str, list[str]] = {
    "open": ["closed", "merged"],
    "closed": ["open"],
    "merged": [],
}
