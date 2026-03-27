"""State machine definitions for repository entities.

Defines valid state transitions for issues, pull requests, and reviews.
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

REVIEW_STATES: list[str] = [
    "PENDING",
    "COMMENTED",
    "APPROVED",
    "CHANGES_REQUESTED",
    "DISMISSED",
]

REVIEW_TRANSITIONS: dict[str, list[str]] = {
    "PENDING": ["COMMENTED", "APPROVED", "CHANGES_REQUESTED"],
    "COMMENTED": ["APPROVED", "CHANGES_REQUESTED", "DISMISSED"],
    "APPROVED": ["DISMISSED"],
    "CHANGES_REQUESTED": ["APPROVED", "COMMENTED", "DISMISSED"],
    "DISMISSED": ["COMMENTED", "APPROVED", "CHANGES_REQUESTED"],
}
