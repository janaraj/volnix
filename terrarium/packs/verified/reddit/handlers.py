"""Action handlers for the Reddit service pack.

Each function handles one tool action, producing a ResponseProposal with
any state mutations expressed as StateDelta objects.

Handlers import ONLY from terrarium.core (types, context). They NEVER
import from persistence/, engines/, or bus/.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from terrarium.core.context import ResponseProposal
from terrarium.core.types import EntityId, StateDelta

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reddit_error(error: str, description: str) -> dict[str, Any]:
    """Return a Reddit-style error response body."""
    return {
        "error": error,
        "description": description,
    }


def _new_id(prefix: str) -> str:
    """Generate a unique entity ID with the given prefix."""
    return f"{prefix}{uuid.uuid4().hex}"


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _find_entity(entities: list[dict[str, Any]], entity_id: str) -> dict[str, Any] | None:
    """Find an entity by its ``id`` field, or return ``None``."""
    for e in entities:
        if e.get("id") == entity_id:
            return e
    return None


def _find_subreddit_by_name(subreddits: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    """Find a subreddit by its lowercase ``name`` field."""
    for s in subreddits:
        if s.get("name") == name:
            return s
    return None


def _find_user_by_username(users: list[dict[str, Any]], username: str) -> dict[str, Any] | None:
    """Find a user by their ``username`` field."""
    for u in users:
        if u.get("username") == username:
            return u
    return None


def _hot_score(post: dict[str, Any]) -> float:
    """Compute Reddit hot-sort score: score / (hours_since_creation + 2)^1.8."""
    score = int(post.get("score", 0))
    created_at = str(post.get("created_at", ""))
    try:
        created = datetime.fromisoformat(created_at)
        now = datetime.now(UTC)
        hours: float = max((now - created).total_seconds() / 3600.0, 0)
    except (ValueError, TypeError):
        hours = 0.0
    denominator: float = (hours + 2) ** 1.8
    return float(score) / denominator


def _paginate_after(
    items: list[dict[str, Any]], after: str | None, limit: int
) -> tuple[list[dict[str, Any]], str | None]:
    """Paginate a list using cursor-based ``after`` pagination.

    Returns (page_items, next_after_cursor_or_none).
    """
    start = 0
    if after:
        for i, item in enumerate(items):
            if item.get("id") == after:
                start = i + 1
                break
    page = items[start : start + limit]
    next_after = page[-1]["id"] if len(page) == limit and start + limit < len(items) else None
    return page, next_after


# ---------------------------------------------------------------------------
# 1. subreddits_search — GET /subreddits/search
# ---------------------------------------------------------------------------


async def handle_subreddits_search(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Search subreddits by query, filter by topic."""
    query = input_data["query"].lower()
    limit = input_data.get("limit", 25)
    offset = input_data.get("offset", 0)

    subreddits = state.get("subreddits", [])
    results = []
    for s in subreddits:
        searchable = " ".join(
            [
                s.get("name", ""),
                s.get("display_name", ""),
                s.get("description", ""),
                " ".join(s.get("topics", [])),
            ]
        ).lower()
        if query in searchable:
            results.append(s)

    paginated = results[offset : offset + limit]

    return ResponseProposal(
        response_body={
            "subreddits": paginated,
            "count": len(paginated),
        },
    )


# ---------------------------------------------------------------------------
# 2. subreddit_about — GET /r/{subreddit}/about
# ---------------------------------------------------------------------------


async def handle_subreddit_about(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Get subreddit details by name."""
    name = input_data["subreddit"]
    subreddits = state.get("subreddits", [])
    sub = _find_subreddit_by_name(subreddits, name)

    if sub is None:
        return ResponseProposal(
            response_body=_reddit_error("NOT_FOUND", f"Subreddit '{name}' not found"),
        )

    return ResponseProposal(
        response_body={"subreddit": sub},
    )


# ---------------------------------------------------------------------------
# 3. subscribe — POST /api/subscribe
# ---------------------------------------------------------------------------


async def handle_subscribe(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Subscribe a user to a subreddit."""
    name = input_data["subreddit"]
    user_id = input_data["user_id"]

    subreddits = state.get("subreddits", [])
    users = state.get("reddit_users", [])

    sub = _find_subreddit_by_name(subreddits, name)
    if sub is None:
        return ResponseProposal(
            response_body=_reddit_error("NOT_FOUND", f"Subreddit '{name}' not found"),
        )

    user = _find_entity(users, user_id)
    if user is None:
        return ResponseProposal(
            response_body=_reddit_error("NOT_FOUND", f"User '{user_id}' not found"),
        )

    # Check if already subscribed
    subscribed = list(user.get("subscribed_subreddit_ids", []))
    if sub["id"] in subscribed:
        return ResponseProposal(
            response_body={"ok": True},
        )

    # Increment subscriber_count on subreddit
    new_count = sub.get("subscriber_count", 0) + 1
    sub_delta = StateDelta(
        entity_type="subreddit",
        entity_id=EntityId(sub["id"]),
        operation="update",
        fields={"subscriber_count": new_count},
        previous_fields={"subscriber_count": sub.get("subscriber_count", 0)},
    )

    # Add subreddit to user's subscribed list
    subscribed.append(sub["id"])
    user_delta = StateDelta(
        entity_type="reddit_user",
        entity_id=EntityId(user_id),
        operation="update",
        fields={"subscribed_subreddit_ids": subscribed},
        previous_fields={"subscribed_subreddit_ids": user.get("subscribed_subreddit_ids", [])},
    )

    return ResponseProposal(
        response_body={"ok": True},
        proposed_state_deltas=[sub_delta, user_delta],
    )


# ---------------------------------------------------------------------------
# 4. unsubscribe — POST /api/unsubscribe
# ---------------------------------------------------------------------------


async def handle_unsubscribe(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Unsubscribe a user from a subreddit."""
    name = input_data["subreddit"]
    user_id = input_data["user_id"]

    subreddits = state.get("subreddits", [])
    users = state.get("reddit_users", [])

    sub = _find_subreddit_by_name(subreddits, name)
    if sub is None:
        return ResponseProposal(
            response_body=_reddit_error("NOT_FOUND", f"Subreddit '{name}' not found"),
        )

    user = _find_entity(users, user_id)
    if user is None:
        return ResponseProposal(
            response_body=_reddit_error("NOT_FOUND", f"User '{user_id}' not found"),
        )

    subscribed = list(user.get("subscribed_subreddit_ids", []))
    if sub["id"] not in subscribed:
        return ResponseProposal(
            response_body={"ok": True},
        )

    # Decrement subscriber_count on subreddit
    new_count = max(sub.get("subscriber_count", 0) - 1, 0)
    sub_delta = StateDelta(
        entity_type="subreddit",
        entity_id=EntityId(sub["id"]),
        operation="update",
        fields={"subscriber_count": new_count},
        previous_fields={"subscriber_count": sub.get("subscriber_count", 0)},
    )

    # Remove subreddit from user's subscribed list
    subscribed.remove(sub["id"])
    user_delta = StateDelta(
        entity_type="reddit_user",
        entity_id=EntityId(user_id),
        operation="update",
        fields={"subscribed_subreddit_ids": subscribed},
        previous_fields={"subscribed_subreddit_ids": user.get("subscribed_subreddit_ids", [])},
    )

    return ResponseProposal(
        response_body={"ok": True},
        proposed_state_deltas=[sub_delta, user_delta],
    )


# ---------------------------------------------------------------------------
# 5. submit — POST /api/submit
# ---------------------------------------------------------------------------


async def handle_submit(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Create a new post with auto-upvote."""
    sr_name = input_data["sr"]
    author_id = input_data["author_id"]

    subreddits = state.get("subreddits", [])
    users = state.get("reddit_users", [])

    sub = _find_subreddit_by_name(subreddits, sr_name)
    if sub is None:
        return ResponseProposal(
            response_body=_reddit_error("NOT_FOUND", f"Subreddit '{sr_name}' not found"),
        )

    author = _find_entity(users, author_id)
    if author is None:
        return ResponseProposal(
            response_body=_reddit_error("NOT_FOUND", f"User '{author_id}' not found"),
        )

    now = _now_iso()
    post_id = _new_id("t3_")
    vote_id = _new_id("vote_")
    kind = input_data.get("kind", "text")

    post_fields: dict[str, Any] = {
        "id": post_id,
        "subreddit_id": sub["id"],
        "author_id": author_id,
        "title": input_data["title"],
        "body": input_data.get("text", ""),
        "url": input_data.get("url"),
        "post_type": kind,
        "flair": input_data.get("flair"),
        "upvotes": 1,
        "downvotes": 0,
        "score": 1,
        "comment_count": 0,
        "crosspost_parent_id": None,
        "is_pinned": False,
        "is_locked": False,
        "is_nsfw": False,
        "is_spoiler": False,
        "awards": [],
        "status": "published",
        "created_at": now,
        "updated_at": now,
    }

    post_delta = StateDelta(
        entity_type="reddit_post",
        entity_id=EntityId(post_id),
        operation="create",
        fields=post_fields,
    )

    # Auto-upvote record
    vote_fields: dict[str, Any] = {
        "id": vote_id,
        "user_id": author_id,
        "target_id": post_id,
        "target_type": "post",
        "direction": "up",
    }

    vote_delta = StateDelta(
        entity_type="vote",
        entity_id=EntityId(vote_id),
        operation="create",
        fields=vote_fields,
    )

    # Increment author post_karma
    new_karma = author.get("post_karma", 0) + 1
    karma_delta = StateDelta(
        entity_type="reddit_user",
        entity_id=EntityId(author_id),
        operation="update",
        fields={"post_karma": new_karma},
        previous_fields={"post_karma": author.get("post_karma", 0)},
    )

    return ResponseProposal(
        response_body={"post": post_fields},
        proposed_state_deltas=[post_delta, vote_delta, karma_delta],
    )


# ---------------------------------------------------------------------------
# 6. post_detail — GET /comments/{id}
# ---------------------------------------------------------------------------


async def handle_post_detail(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Get post detail by ID."""
    post_id = input_data["id"]
    posts = state.get("reddit_posts", [])
    post = _find_entity(posts, post_id)

    if post is None:
        return ResponseProposal(
            response_body=_reddit_error("NOT_FOUND", f"Post '{post_id}' not found"),
        )

    return ResponseProposal(
        response_body={"post": post},
    )


# ---------------------------------------------------------------------------
# 7. subreddit_hot — GET /r/{subreddit}/hot
# ---------------------------------------------------------------------------


async def handle_subreddit_hot(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """List hot posts in a subreddit sorted by hotness."""
    sr_name = input_data["subreddit"]
    limit = input_data.get("limit", 25)
    after = input_data.get("after")

    subreddits = state.get("subreddits", [])
    sub = _find_subreddit_by_name(subreddits, sr_name)
    if sub is None:
        return ResponseProposal(
            response_body=_reddit_error("NOT_FOUND", f"Subreddit '{sr_name}' not found"),
        )

    posts = state.get("reddit_posts", [])
    sr_posts = [
        p for p in posts if p.get("subreddit_id") == sub["id"] and p.get("status") == "published"
    ]
    sr_posts.sort(key=_hot_score, reverse=True)

    page, next_after = _paginate_after(sr_posts, after, limit)

    return ResponseProposal(
        response_body={
            "posts": page,
            "count": len(page),
            "after": next_after,
        },
    )


# ---------------------------------------------------------------------------
# 8. subreddit_new — GET /r/{subreddit}/new
# ---------------------------------------------------------------------------


async def handle_subreddit_new(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """List newest posts in a subreddit."""
    sr_name = input_data["subreddit"]
    limit = input_data.get("limit", 25)
    after = input_data.get("after")

    subreddits = state.get("subreddits", [])
    sub = _find_subreddit_by_name(subreddits, sr_name)
    if sub is None:
        return ResponseProposal(
            response_body=_reddit_error("NOT_FOUND", f"Subreddit '{sr_name}' not found"),
        )

    posts = state.get("reddit_posts", [])
    sr_posts = [
        p for p in posts if p.get("subreddit_id") == sub["id"] and p.get("status") == "published"
    ]
    sr_posts.sort(key=lambda p: p.get("created_at", ""), reverse=True)

    page, next_after = _paginate_after(sr_posts, after, limit)

    return ResponseProposal(
        response_body={
            "posts": page,
            "count": len(page),
            "after": next_after,
        },
    )


# ---------------------------------------------------------------------------
# 9. subreddit_top — GET /r/{subreddit}/top
# ---------------------------------------------------------------------------


async def handle_subreddit_top(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """List top posts in a subreddit, optionally filtered by time window."""
    sr_name = input_data["subreddit"]
    t = input_data.get("t", "all")
    limit = input_data.get("limit", 25)
    after = input_data.get("after")

    subreddits = state.get("subreddits", [])
    sub = _find_subreddit_by_name(subreddits, sr_name)
    if sub is None:
        return ResponseProposal(
            response_body=_reddit_error("NOT_FOUND", f"Subreddit '{sr_name}' not found"),
        )

    posts = state.get("reddit_posts", [])
    sr_posts = [
        p for p in posts if p.get("subreddit_id") == sub["id"] and p.get("status") == "published"
    ]

    # Apply time filter
    if t != "all":
        now = datetime.now(UTC)
        hours_map = {
            "hour": 1,
            "day": 24,
            "week": 168,
            "month": 730,
            "year": 8760,
        }
        max_hours = hours_map.get(t, 0)
        if max_hours > 0:
            filtered = []
            for p in sr_posts:
                try:
                    created = datetime.fromisoformat(p.get("created_at", ""))
                    age_hours = (now - created).total_seconds() / 3600.0
                    if age_hours <= max_hours:
                        filtered.append(p)
                except (ValueError, TypeError):
                    pass
            sr_posts = filtered

    sr_posts.sort(key=lambda p: p.get("score", 0), reverse=True)

    page, next_after = _paginate_after(sr_posts, after, limit)

    return ResponseProposal(
        response_body={
            "posts": page,
            "count": len(page),
            "after": next_after,
        },
    )


# ---------------------------------------------------------------------------
# 10. search — GET /search
# ---------------------------------------------------------------------------


async def handle_search(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Search posts with relevance scoring."""
    query = input_data["q"].lower()
    sr_name = input_data.get("sr")
    sort = input_data.get("sort", "relevance")
    limit = input_data.get("limit", 25)

    posts = list(state.get("reddit_posts", []))

    # Filter to subreddit if specified
    if sr_name:
        subreddits = state.get("subreddits", [])
        sub = _find_subreddit_by_name(subreddits, sr_name)
        if sub is None:
            return ResponseProposal(
                response_body=_reddit_error("NOT_FOUND", f"Subreddit '{sr_name}' not found"),
            )
        posts = [p for p in posts if p.get("subreddit_id") == sub["id"]]

    # Only published posts
    posts = [p for p in posts if p.get("status") == "published"]

    # Score and filter by relevance (tokenized — match any word)
    query_tokens = [t for t in query.split() if len(t) > 2]
    scored: list[tuple[dict[str, Any], int]] = []
    for p in posts:
        relevance = 0
        title = p.get("title", "").lower()
        body = p.get("body", "").lower()
        for token in query_tokens:
            if token in title:
                relevance += 3
            if token in body:
                relevance += 1
        if relevance > 0:
            scored.append((p, relevance))

    # Sort
    if sort == "relevance":
        scored.sort(key=lambda x: x[1], reverse=True)
    elif sort == "hot":
        scored.sort(key=lambda x: _hot_score(x[0]), reverse=True)
    elif sort == "top":
        scored.sort(key=lambda x: x[0].get("score", 0), reverse=True)
    elif sort == "new":
        scored.sort(key=lambda x: x[0].get("created_at", ""), reverse=True)

    results = [item[0] for item in scored[:limit]]

    return ResponseProposal(
        response_body={
            "posts": results,
            "count": len(results),
        },
    )


# ---------------------------------------------------------------------------
# 11. remove — POST /api/remove
# ---------------------------------------------------------------------------


async def handle_remove(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Remove a post or comment (mod action). Transitions status to 'removed'."""
    target_id = input_data["id"]
    target_type = input_data["type"]

    if target_type == "post":
        entity_type = "reddit_post"
        entities = state.get("reddit_posts", [])
    elif target_type == "comment":
        entity_type = "comment"
        entities = state.get("reddit_comments", [])
    else:
        return ResponseProposal(
            response_body=_reddit_error(
                "INVALID_TYPE", f"Invalid type '{target_type}'. Must be 'post' or 'comment'."
            ),
        )

    entity = _find_entity(entities, target_id)
    if entity is None:
        return ResponseProposal(
            response_body=_reddit_error(
                "NOT_FOUND", f"{target_type.capitalize()} '{target_id}' not found"
            ),
        )

    old_status = entity.get("status", "published")
    now = _now_iso()

    delta = StateDelta(
        entity_type=entity_type,
        entity_id=EntityId(target_id),
        operation="update",
        fields={"status": "removed", "updated_at": now},
        previous_fields={"status": old_status},
    )

    return ResponseProposal(
        response_body={"ok": True},
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# 12. comment — POST /api/comment
# ---------------------------------------------------------------------------


async def handle_comment(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Create a comment on a post or reply to another comment."""
    parent_fullname = input_data["parent"]
    text = input_data["text"]
    author_id = input_data["author_id"]

    users = state.get("reddit_users", [])
    author = _find_entity(users, author_id)
    if author is None:
        return ResponseProposal(
            response_body=_reddit_error("NOT_FOUND", f"User '{author_id}' not found"),
        )

    now = _now_iso()
    comment_id = _new_id("t1_")
    vote_id = _new_id("vote_")
    deltas: list[StateDelta] = []

    depth = 0
    post_id: str

    if parent_fullname.startswith("t3_"):
        # Replying to a post
        post_id = parent_fullname
        posts = state.get("reddit_posts", [])
        post = _find_entity(posts, post_id)
        if post is None:
            return ResponseProposal(
                response_body=_reddit_error("NOT_FOUND", f"Post '{post_id}' not found"),
            )

        # Increment post comment_count
        new_count = post.get("comment_count", 0) + 1
        post_delta = StateDelta(
            entity_type="reddit_post",
            entity_id=EntityId(post_id),
            operation="update",
            fields={"comment_count": new_count, "updated_at": now},
            previous_fields={"comment_count": post.get("comment_count", 0)},
        )
        deltas.append(post_delta)

    elif parent_fullname.startswith("t1_"):
        # Replying to a comment
        parent_comment_id = parent_fullname
        comments = state.get("reddit_comments", [])
        parent_comment = _find_entity(comments, parent_comment_id)
        if parent_comment is None:
            return ResponseProposal(
                response_body=_reddit_error(
                    "NOT_FOUND", f"Comment '{parent_comment_id}' not found"
                ),
            )

        depth = parent_comment.get("depth", 0) + 1
        post_id = parent_comment["post_id"]

        # Increment parent reply_count
        new_reply_count = parent_comment.get("reply_count", 0) + 1
        parent_delta = StateDelta(
            entity_type="comment",
            entity_id=EntityId(parent_comment_id),
            operation="update",
            fields={"reply_count": new_reply_count, "updated_at": now},
            previous_fields={"reply_count": parent_comment.get("reply_count", 0)},
        )
        deltas.append(parent_delta)

        # Also increment post comment_count
        posts = state.get("reddit_posts", [])
        post = _find_entity(posts, post_id)
        if post is not None:
            new_count = post.get("comment_count", 0) + 1
            post_delta = StateDelta(
                entity_type="reddit_post",
                entity_id=EntityId(post_id),
                operation="update",
                fields={"comment_count": new_count, "updated_at": now},
                previous_fields={"comment_count": post.get("comment_count", 0)},
            )
            deltas.append(post_delta)

    else:
        return ResponseProposal(
            response_body=_reddit_error(
                "INVALID_PARENT",
                f"Parent '{parent_fullname}' must start with t3_ (post) or t1_ (comment).",
            ),
        )

    comment_fields: dict[str, Any] = {
        "id": comment_id,
        "post_id": post_id,
        "parent_id": parent_fullname if parent_fullname.startswith("t1_") else None,
        "author_id": author_id,
        "body": text,
        "upvotes": 1,
        "downvotes": 0,
        "score": 1,
        "depth": depth,
        "reply_count": 0,
        "is_stickied": False,
        "status": "published",
        "created_at": now,
        "updated_at": now,
    }

    comment_delta = StateDelta(
        entity_type="comment",
        entity_id=EntityId(comment_id),
        operation="create",
        fields=comment_fields,
    )
    deltas.append(comment_delta)

    # Auto-upvote record
    vote_fields: dict[str, Any] = {
        "id": vote_id,
        "user_id": author_id,
        "target_id": comment_id,
        "target_type": "comment",
        "direction": "up",
    }
    vote_delta = StateDelta(
        entity_type="vote",
        entity_id=EntityId(vote_id),
        operation="create",
        fields=vote_fields,
    )
    deltas.append(vote_delta)

    # Increment author comment_karma
    new_karma = author.get("comment_karma", 0) + 1
    karma_delta = StateDelta(
        entity_type="reddit_user",
        entity_id=EntityId(author_id),
        operation="update",
        fields={"comment_karma": new_karma},
        previous_fields={"comment_karma": author.get("comment_karma", 0)},
    )
    deltas.append(karma_delta)

    return ResponseProposal(
        response_body={"comment": comment_fields},
        proposed_state_deltas=deltas,
    )


# ---------------------------------------------------------------------------
# 13. post_comments — GET /comments/{id}/comments
# ---------------------------------------------------------------------------


async def handle_post_comments(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """List comments for a post."""
    post_id = input_data["id"]
    sort = input_data.get("sort", "best")

    comments = state.get("reddit_comments", [])
    filtered = [
        c for c in comments if c.get("post_id") == post_id and c.get("status") == "published"
    ]

    if sort in ("best", "top"):
        filtered.sort(key=lambda c: c.get("score", 0), reverse=True)
    elif sort == "new":
        filtered.sort(key=lambda c: c.get("created_at", ""), reverse=True)

    return ResponseProposal(
        response_body={
            "comments": filtered,
            "count": len(filtered),
        },
    )


# ---------------------------------------------------------------------------
# 14. vote — POST /api/vote
# ---------------------------------------------------------------------------


async def handle_vote(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Vote on a post or comment with idempotency."""
    target_id = input_data["id"]
    direction = input_data["dir"]  # 1, 0, -1
    user_id = input_data["user_id"]

    # Determine target type from ID prefix
    if target_id.startswith("t3_"):
        target_type = "post"
        entity_type = "reddit_post"
        entities = state.get("reddit_posts", [])
    elif target_id.startswith("t1_"):
        target_type = "comment"
        entity_type = "comment"
        entities = state.get("reddit_comments", [])
    else:
        return ResponseProposal(
            response_body=_reddit_error(
                "INVALID_ID",
                f"Target '{target_id}' must start with t3_ (post) or t1_ (comment).",
            ),
        )

    target = _find_entity(entities, target_id)
    if target is None:
        return ResponseProposal(
            response_body=_reddit_error(
                "NOT_FOUND", f"{target_type.capitalize()} '{target_id}' not found"
            ),
        )

    # Find existing vote by this user on this target
    votes = state.get("reddit_votes", [])
    existing_vote: dict[str, Any] | None = None
    for v in votes:
        if v.get("user_id") == user_id and v.get("target_id") == target_id:
            existing_vote = v
            break

    deltas: list[StateDelta] = []
    old_score = target.get("score", 0)
    old_upvotes = target.get("upvotes", 0)
    old_downvotes = target.get("downvotes", 0)
    score_change = 0
    upvote_change = 0
    downvote_change = 0

    dir_to_direction = {1: "up", -1: "down"}
    new_direction = dir_to_direction.get(direction)

    if direction == 0:
        # Unvote: remove existing vote
        if existing_vote is None:
            return ResponseProposal(response_body={"ok": True})

        old_dir = existing_vote.get("direction")
        if old_dir == "up":
            score_change = -1
            upvote_change = -1
        elif old_dir == "down":
            score_change = 1
            downvote_change = -1

        # Delete the vote record
        vote_delta = StateDelta(
            entity_type="vote",
            entity_id=EntityId(existing_vote["id"]),
            operation="delete",
            fields=existing_vote,
        )
        deltas.append(vote_delta)

    elif existing_vote is not None:
        old_dir = existing_vote.get("direction")
        if old_dir == new_direction:
            # Same direction: no-op
            return ResponseProposal(response_body={"ok": True})

        # Flip vote: opposite direction
        if old_dir == "up" and new_direction == "down":
            score_change = -2
            upvote_change = -1
            downvote_change = 1
        elif old_dir == "down" and new_direction == "up":
            score_change = 2
            upvote_change = 1
            downvote_change = -1

        vote_delta = StateDelta(
            entity_type="vote",
            entity_id=EntityId(existing_vote["id"]),
            operation="update",
            fields={"direction": new_direction},
            previous_fields={"direction": old_dir},
        )
        deltas.append(vote_delta)

    else:
        # New vote
        vote_id = _new_id("vote_")
        vote_fields: dict[str, Any] = {
            "id": vote_id,
            "user_id": user_id,
            "target_id": target_id,
            "target_type": target_type,
            "direction": new_direction,
        }
        vote_delta = StateDelta(
            entity_type="vote",
            entity_id=EntityId(vote_id),
            operation="create",
            fields=vote_fields,
        )
        deltas.append(vote_delta)

        if new_direction == "up":
            score_change = 1
            upvote_change = 1
        else:
            score_change = -1
            downvote_change = 1

    # Update the target's score
    if score_change != 0 or upvote_change != 0 or downvote_change != 0:
        new_upvotes = old_upvotes + upvote_change
        new_downvotes = old_downvotes + downvote_change
        new_score = old_score + score_change

        target_delta = StateDelta(
            entity_type=entity_type,
            entity_id=EntityId(target_id),
            operation="update",
            fields={
                "upvotes": new_upvotes,
                "downvotes": new_downvotes,
                "score": new_score,
            },
            previous_fields={
                "upvotes": old_upvotes,
                "downvotes": old_downvotes,
                "score": old_score,
            },
        )
        deltas.append(target_delta)

        # Update author karma
        author_id = target.get("author_id")
        if author_id:
            users = state.get("reddit_users", [])
            author = _find_entity(users, author_id)
            if author is not None:
                karma_field = "post_karma" if target_type == "post" else "comment_karma"
                old_karma = author.get(karma_field, 0)
                new_karma = old_karma + score_change
                karma_delta = StateDelta(
                    entity_type="reddit_user",
                    entity_id=EntityId(author_id),
                    operation="update",
                    fields={karma_field: new_karma},
                    previous_fields={karma_field: old_karma},
                )
                deltas.append(karma_delta)

    return ResponseProposal(
        response_body={"ok": True},
        proposed_state_deltas=deltas,
    )


# ---------------------------------------------------------------------------
# 15. user_about — GET /user/{username}/about
# ---------------------------------------------------------------------------


async def handle_user_about(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Get user profile by username."""
    username = input_data["username"]
    users = state.get("reddit_users", [])
    user = _find_user_by_username(users, username)

    if user is None:
        return ResponseProposal(
            response_body=_reddit_error("NOT_FOUND", f"User '{username}' not found"),
        )

    return ResponseProposal(
        response_body={"user": user},
    )


# ---------------------------------------------------------------------------
# 16. user_submitted — GET /user/{username}/submitted
# ---------------------------------------------------------------------------


async def handle_user_submitted(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """List posts submitted by a user."""
    username = input_data["username"]
    sort = input_data.get("sort", "new")
    limit = input_data.get("limit", 25)

    users = state.get("reddit_users", [])
    user = _find_user_by_username(users, username)
    if user is None:
        return ResponseProposal(
            response_body=_reddit_error("NOT_FOUND", f"User '{username}' not found"),
        )

    posts = state.get("reddit_posts", [])
    user_posts = [
        p for p in posts if p.get("author_id") == user["id"] and p.get("status") == "published"
    ]

    if sort == "hot":
        user_posts.sort(key=_hot_score, reverse=True)
    elif sort == "new":
        user_posts.sort(key=lambda p: p.get("created_at", ""), reverse=True)
    elif sort == "top":
        user_posts.sort(key=lambda p: p.get("score", 0), reverse=True)

    paginated = user_posts[:limit]

    return ResponseProposal(
        response_body={
            "posts": paginated,
            "count": len(paginated),
        },
    )


# ---------------------------------------------------------------------------
# 17. best — GET /best
# ---------------------------------------------------------------------------


async def handle_best(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Home feed: posts from subscribed subreddits, sorted by score."""
    user_id = input_data["user_id"]
    limit = input_data.get("limit", 25)
    after = input_data.get("after")

    users = state.get("reddit_users", [])
    user = _find_entity(users, user_id)
    if user is None:
        return ResponseProposal(
            response_body=_reddit_error("NOT_FOUND", f"User '{user_id}' not found"),
        )

    subscribed_ids = set(user.get("subscribed_subreddit_ids", []))
    posts = state.get("reddit_posts", [])
    feed_posts = [
        p
        for p in posts
        if p.get("subreddit_id") in subscribed_ids and p.get("status") == "published"
    ]
    feed_posts.sort(key=lambda p: p.get("score", 0), reverse=True)

    page, next_after = _paginate_after(feed_posts, after, limit)

    return ResponseProposal(
        response_body={
            "posts": page,
            "count": len(page),
            "after": next_after,
        },
    )


# ---------------------------------------------------------------------------
# 18. popular — GET /r/popular
# ---------------------------------------------------------------------------


async def handle_popular(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Trending posts from all public subreddits, sorted by score."""
    limit = input_data.get("limit", 25)
    after = input_data.get("after")

    # Build set of public subreddit IDs
    subreddits = state.get("subreddits", [])
    public_ids = {
        s["id"]
        for s in subreddits
        if s.get("visibility", "public") == "public" and s.get("status") == "active"
    }

    posts = state.get("reddit_posts", [])
    popular_posts = [
        p for p in posts if p.get("subreddit_id") in public_ids and p.get("status") == "published"
    ]
    popular_posts.sort(key=lambda p: p.get("score", 0), reverse=True)

    page, next_after = _paginate_after(popular_posts, after, limit)

    return ResponseProposal(
        response_body={
            "posts": page,
            "count": len(page),
            "after": next_after,
        },
    )
