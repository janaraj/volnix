"""State machine definitions for Reddit entities.

Defines valid status transitions for posts, comments, users, and subreddits.
"""

from __future__ import annotations

REDDIT_POST_STATES: list[str] = ["published", "removed", "spam"]

REDDIT_POST_TRANSITIONS: dict[str, list[str]] = {
    "published": ["removed", "spam"],
    "removed": ["published"],
    "spam": [],
}

REDDIT_COMMENT_STATES: list[str] = ["published", "removed", "spam"]

REDDIT_COMMENT_TRANSITIONS: dict[str, list[str]] = {
    "published": ["removed", "spam"],
    "removed": ["published"],
    "spam": [],
}

REDDIT_USER_STATES: list[str] = ["active", "suspended", "deleted"]

REDDIT_USER_TRANSITIONS: dict[str, list[str]] = {
    "active": ["suspended", "deleted"],
    "suspended": ["active"],
    "deleted": [],
}

SUBREDDIT_STATES: list[str] = ["active", "quarantined", "banned"]

SUBREDDIT_TRANSITIONS: dict[str, list[str]] = {
    "active": ["quarantined", "banned"],
    "quarantined": ["active", "banned"],
    "banned": [],
}
