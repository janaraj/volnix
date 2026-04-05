"""State machine definitions for Twitter/X entities.

Defines valid status transitions for tweets and user accounts.
"""

from __future__ import annotations

TWEET_STATES: list[str] = ["published", "deleted"]

TWEET_TRANSITIONS: dict[str, list[str]] = {
    "published": ["deleted"],
    "deleted": [],
}

TWITTER_USER_STATES: list[str] = ["active", "suspended", "deactivated"]

TWITTER_USER_TRANSITIONS: dict[str, list[str]] = {
    "active": ["suspended", "deactivated"],
    "suspended": ["active"],
    "deactivated": ["active"],
}
