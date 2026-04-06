"""Configuration model for the permission engine."""

from __future__ import annotations

from pydantic import BaseModel


class PermissionConfig(BaseModel):
    """Configuration for the permission engine."""

    cache_ttl_seconds: int = 300
    visibility_rule_entity_type: str = "visibility_rule"
    observer_read_prefixes: list[str] = [
        "list",
        "get",
        "show",
        "search",
        "read",
        "query",
        "about",
        "hot",
        "new",
        "top",
        "best",
        "popular",
        "trending",
        "detail",
        "home_feed",
        "timeline",
        "followers",
        "following",
        "user_tweets",
        "user_submitted",
    ]
