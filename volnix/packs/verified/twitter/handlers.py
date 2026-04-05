"""Action handlers for the Twitter/X service pack.

Each function handles one tool action, producing a ResponseProposal with
any state mutations expressed as StateDelta objects.

Handlers import ONLY from volnix.core (types, context). They NEVER
import from persistence/, engines/, or bus/.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from volnix.core.context import ResponseProposal
from volnix.core.types import EntityId, StateDelta

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_id(prefix: str) -> str:
    """Generate a unique entity ID with the given prefix."""
    return f"{prefix}-{uuid.uuid4().hex}"


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _find_entity(entities: list[dict[str, Any]], entity_id: str) -> dict[str, Any] | None:
    """Find an entity by ID in a list of entity dicts."""
    for e in entities:
        if e.get("id") == entity_id:
            return e
    return None


def _twitter_error(error: str, description: str) -> dict[str, Any]:
    """Return a Twitter API v2-style error response body."""
    return {
        "errors": [
            {
                "title": error,
                "detail": description,
                "type": "about:blank",
            }
        ],
    }


def _extract_hashtags(text: str) -> list[str]:
    """Extract hashtags from tweet text (without the # prefix)."""
    return re.findall(r"#(\w+)", text)


def _extract_mentions(text: str) -> list[str]:
    """Extract @mentions from tweet text (without the @ prefix)."""
    return re.findall(r"@(\w+)", text)


# ---------------------------------------------------------------------------
# Tweet handlers
# ---------------------------------------------------------------------------


async def handle_create_tweet(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``create_tweet`` action.

    Creates a new tweet entity with tweet_type="original". Auto-extracts
    hashtags and mentions from text. Increments the author's tweet_count.
    """
    text = input_data["text"]
    if len(text) > 280:
        return ResponseProposal(
            response_body=_twitter_error(
                "InvalidRequest", "Tweet text exceeds 280 character limit."
            ),
        )

    author_id = input_data["author_id"]
    users = state.get("twitter_users", [])
    author = _find_entity(users, author_id)
    if author is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"User '{author_id}' not found."),
        )

    tweet_id = _new_id("tweet")
    now = _now_iso()

    tweet_fields: dict[str, Any] = {
        "id": tweet_id,
        "author_id": author_id,
        "text": text,
        "tweet_type": "original",
        "reply_to_tweet_id": None,
        "retweet_of_id": None,
        "quote_of_id": None,
        "hashtags": _extract_hashtags(text),
        "mentions": _extract_mentions(text),
        "media_urls": input_data.get("media_urls", []),
        "link_url": input_data.get("link_url"),
        "like_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
        "reply_count": 0,
        "view_count": 0,
        "bookmark_count": 0,
        "is_pinned": False,
        "status": "published",
        "created_at": now,
    }

    tweet_delta = StateDelta(
        entity_type="tweet",
        entity_id=EntityId(tweet_id),
        operation="create",
        fields=tweet_fields,
    )

    # Increment author tweet_count
    new_tweet_count = author.get("tweet_count", 0) + 1
    author_delta = StateDelta(
        entity_type="twitter_user",
        entity_id=EntityId(author_id),
        operation="update",
        fields={"tweet_count": new_tweet_count},
        previous_fields={"tweet_count": author.get("tweet_count", 0)},
    )

    return ResponseProposal(
        response_body={"data": tweet_fields},
        proposed_state_deltas=[tweet_delta, author_delta],
    )


async def handle_get_tweet(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``get_tweet`` action.

    Finds a single tweet by ID. No state mutations.
    """
    tweet_id = input_data["id"]
    tweets = state.get("tweets", [])
    tweet = _find_entity(tweets, tweet_id)

    if tweet is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"Tweet '{tweet_id}' not found."),
        )

    return ResponseProposal(
        response_body={"data": tweet},
    )


async def handle_delete_tweet(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``delete_tweet`` action.

    Transitions a tweet to status="deleted".
    """
    tweet_id = input_data["id"]
    tweets = state.get("tweets", [])
    tweet = _find_entity(tweets, tweet_id)

    if tweet is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"Tweet '{tweet_id}' not found."),
        )

    if tweet.get("status") == "deleted":
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"Tweet '{tweet_id}' is already deleted."),
        )

    delta = StateDelta(
        entity_type="tweet",
        entity_id=EntityId(tweet_id),
        operation="update",
        fields={"status": "deleted"},
        previous_fields={"status": "published"},
    )

    return ResponseProposal(
        response_body={"data": {"deleted": True}},
        proposed_state_deltas=[delta],
    )


async def handle_search_recent(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``search_recent`` action.

    Searches recent tweets. Supports #hashtag filter, @mention filter,
    "from:username" filter, and free text substring matching.
    Sorts by created_at descending.
    """
    query = input_data["query"]
    max_results = input_data.get("max_results", 10)
    tweets = [t for t in state.get("tweets", []) if t.get("status") == "published"]
    users = state.get("twitter_users", [])

    # Parse structured filters
    from_username: str | None = None
    hashtag_filters: list[str] = []
    mention_filters: list[str] = []
    free_text_parts: list[str] = []

    for token in query.split():
        if token.lower().startswith("from:"):
            from_username = token.split(":", 1)[1]
        elif token.startswith("#"):
            hashtag_filters.append(token[1:].lower())
        elif token.startswith("@"):
            mention_filters.append(token[1:].lower())
        else:
            free_text_parts.append(token)

    free_text = " ".join(free_text_parts).lower()

    # Apply from:username filter
    if from_username:
        # Resolve username to user ID
        author_id: str | None = None
        for u in users:
            if u.get("username", "").lower() == from_username.lower():
                author_id = u["id"]
                break
        if author_id:
            tweets = [t for t in tweets if t.get("author_id") == author_id]
        else:
            tweets = []

    # Apply hashtag filters
    if hashtag_filters:
        filtered = []
        for t in tweets:
            tweet_tags = [h.lower() for h in t.get("hashtags", [])]
            if all(hf in tweet_tags for hf in hashtag_filters):
                filtered.append(t)
        tweets = filtered

    # Apply mention filters
    if mention_filters:
        filtered = []
        for t in tweets:
            tweet_mentions = [m.lower() for m in t.get("mentions", [])]
            if all(mf in tweet_mentions for mf in mention_filters):
                filtered.append(t)
        tweets = filtered

    # Apply free text search (tokenized — match any word)
    if free_text:
        tokens = [w for w in free_text.split() if len(w) > 2]
        if tokens:
            filtered = []
            for t in tweets:
                text_lower = t.get("text", "").lower()
                if any(tok in text_lower for tok in tokens):
                    filtered.append(t)
            tweets = filtered

    # Sort by created_at desc
    tweets.sort(key=lambda t: t.get("created_at", ""), reverse=True)

    # Limit results
    paginated = tweets[:max_results]

    return ResponseProposal(
        response_body={
            "data": paginated,
            "meta": {
                "result_count": len(paginated),
                "newest_id": paginated[0]["id"] if paginated else None,
                "oldest_id": paginated[-1]["id"] if paginated else None,
            },
        },
    )


async def handle_reply(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``reply`` action.

    Creates a reply tweet. Increments the parent tweet's reply_count
    and the author's tweet_count.
    """
    text = input_data["text"]
    if len(text) > 280:
        return ResponseProposal(
            response_body=_twitter_error(
                "InvalidRequest", "Tweet text exceeds 280 character limit."
            ),
        )

    author_id = input_data["author_id"]
    parent_tweet_id = input_data["in_reply_to_tweet_id"]

    users = state.get("twitter_users", [])
    author = _find_entity(users, author_id)
    if author is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"User '{author_id}' not found."),
        )

    tweets = state.get("tweets", [])
    parent = _find_entity(tweets, parent_tweet_id)
    if parent is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"Tweet '{parent_tweet_id}' not found."),
        )

    tweet_id = _new_id("tweet")
    now = _now_iso()

    tweet_fields: dict[str, Any] = {
        "id": tweet_id,
        "author_id": author_id,
        "text": text,
        "tweet_type": "reply",
        "reply_to_tweet_id": parent_tweet_id,
        "retweet_of_id": None,
        "quote_of_id": None,
        "hashtags": _extract_hashtags(text),
        "mentions": _extract_mentions(text),
        "media_urls": [],
        "link_url": None,
        "like_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
        "reply_count": 0,
        "view_count": 0,
        "bookmark_count": 0,
        "is_pinned": False,
        "status": "published",
        "created_at": now,
    }

    tweet_delta = StateDelta(
        entity_type="tweet",
        entity_id=EntityId(tweet_id),
        operation="create",
        fields=tweet_fields,
    )

    # Increment parent reply_count
    old_reply_count = parent.get("reply_count", 0)
    parent_delta = StateDelta(
        entity_type="tweet",
        entity_id=EntityId(parent_tweet_id),
        operation="update",
        fields={"reply_count": old_reply_count + 1},
        previous_fields={"reply_count": old_reply_count},
    )

    # Increment author tweet_count
    old_tweet_count = author.get("tweet_count", 0)
    author_delta = StateDelta(
        entity_type="twitter_user",
        entity_id=EntityId(author_id),
        operation="update",
        fields={"tweet_count": old_tweet_count + 1},
        previous_fields={"tweet_count": old_tweet_count},
    )

    return ResponseProposal(
        response_body={"data": tweet_fields},
        proposed_state_deltas=[tweet_delta, parent_delta, author_delta],
    )


async def handle_retweet(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``retweet`` action.

    Creates a retweet entity. Idempotent: if already retweeted, returns
    the existing retweet. Increments the original tweet's retweet_count
    and the retweeter's tweet_count.
    """
    user_id = input_data["user_id"]
    original_tweet_id = input_data["tweet_id"]

    users = state.get("twitter_users", [])
    user = _find_entity(users, user_id)
    if user is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"User '{user_id}' not found."),
        )

    tweets = state.get("tweets", [])
    original = _find_entity(tweets, original_tweet_id)
    if original is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"Tweet '{original_tweet_id}' not found."),
        )

    # Idempotency check: already retweeted?
    for t in tweets:
        if (
            t.get("author_id") == user_id
            and t.get("retweet_of_id") == original_tweet_id
            and t.get("tweet_type") == "retweet"
            and t.get("status") == "published"
        ):
            return ResponseProposal(
                response_body={"data": {"retweeted": True}},
            )

    retweet_id = _new_id("tweet")
    now = _now_iso()

    retweet_fields: dict[str, Any] = {
        "id": retweet_id,
        "author_id": user_id,
        "text": "",
        "tweet_type": "retweet",
        "reply_to_tweet_id": None,
        "retweet_of_id": original_tweet_id,
        "quote_of_id": None,
        "hashtags": [],
        "mentions": [],
        "media_urls": [],
        "link_url": None,
        "like_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
        "reply_count": 0,
        "view_count": 0,
        "bookmark_count": 0,
        "is_pinned": False,
        "status": "published",
        "created_at": now,
    }

    retweet_delta = StateDelta(
        entity_type="tweet",
        entity_id=EntityId(retweet_id),
        operation="create",
        fields=retweet_fields,
    )

    # Increment original retweet_count
    old_rt_count = original.get("retweet_count", 0)
    original_delta = StateDelta(
        entity_type="tweet",
        entity_id=EntityId(original_tweet_id),
        operation="update",
        fields={"retweet_count": old_rt_count + 1},
        previous_fields={"retweet_count": old_rt_count},
    )

    # Increment retweeter tweet_count
    old_tweet_count = user.get("tweet_count", 0)
    user_delta = StateDelta(
        entity_type="twitter_user",
        entity_id=EntityId(user_id),
        operation="update",
        fields={"tweet_count": old_tweet_count + 1},
        previous_fields={"tweet_count": old_tweet_count},
    )

    return ResponseProposal(
        response_body={"data": {"retweeted": True}},
        proposed_state_deltas=[retweet_delta, original_delta, user_delta],
    )


async def handle_unretweet(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``unretweet`` action.

    Deletes the retweet tweet entity and decrements the original
    tweet's retweet_count.
    """
    user_id = input_data["user_id"]
    original_tweet_id = input_data["tweet_id"]

    tweets = state.get("tweets", [])
    original = _find_entity(tweets, original_tweet_id)
    if original is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"Tweet '{original_tweet_id}' not found."),
        )

    # Find the user's retweet of this tweet
    retweet = None
    for t in tweets:
        if (
            t.get("author_id") == user_id
            and t.get("retweet_of_id") == original_tweet_id
            and t.get("tweet_type") == "retweet"
            and t.get("status") == "published"
        ):
            retweet = t
            break

    if retweet is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", "Retweet not found for this user and tweet."),
        )

    # Mark retweet as deleted
    retweet_delta = StateDelta(
        entity_type="tweet",
        entity_id=EntityId(retweet["id"]),
        operation="update",
        fields={"status": "deleted"},
        previous_fields={"status": "published"},
    )

    # Decrement original retweet_count
    old_rt_count = original.get("retweet_count", 0)
    new_rt_count = max(0, old_rt_count - 1)
    original_delta = StateDelta(
        entity_type="tweet",
        entity_id=EntityId(original_tweet_id),
        operation="update",
        fields={"retweet_count": new_rt_count},
        previous_fields={"retweet_count": old_rt_count},
    )

    return ResponseProposal(
        response_body={"data": {"retweeted": False}},
        proposed_state_deltas=[retweet_delta, original_delta],
    )


async def handle_quote_tweet(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``quote_tweet`` action.

    Creates a quote tweet. Increments the original tweet's quote_count
    and the author's tweet_count.
    """
    text = input_data["text"]
    if len(text) > 280:
        return ResponseProposal(
            response_body=_twitter_error(
                "InvalidRequest", "Tweet text exceeds 280 character limit."
            ),
        )

    author_id = input_data["author_id"]
    quote_tweet_id = input_data["quote_tweet_id"]

    users = state.get("twitter_users", [])
    author = _find_entity(users, author_id)
    if author is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"User '{author_id}' not found."),
        )

    tweets = state.get("tweets", [])
    original = _find_entity(tweets, quote_tweet_id)
    if original is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"Tweet '{quote_tweet_id}' not found."),
        )

    tweet_id = _new_id("tweet")
    now = _now_iso()

    tweet_fields: dict[str, Any] = {
        "id": tweet_id,
        "author_id": author_id,
        "text": text,
        "tweet_type": "quote",
        "reply_to_tweet_id": None,
        "retweet_of_id": None,
        "quote_of_id": quote_tweet_id,
        "hashtags": _extract_hashtags(text),
        "mentions": _extract_mentions(text),
        "media_urls": [],
        "link_url": None,
        "like_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
        "reply_count": 0,
        "view_count": 0,
        "bookmark_count": 0,
        "is_pinned": False,
        "status": "published",
        "created_at": now,
    }

    tweet_delta = StateDelta(
        entity_type="tweet",
        entity_id=EntityId(tweet_id),
        operation="create",
        fields=tweet_fields,
    )

    # Increment original quote_count
    old_quote_count = original.get("quote_count", 0)
    original_delta = StateDelta(
        entity_type="tweet",
        entity_id=EntityId(quote_tweet_id),
        operation="update",
        fields={"quote_count": old_quote_count + 1},
        previous_fields={"quote_count": old_quote_count},
    )

    # Increment author tweet_count
    old_tweet_count = author.get("tweet_count", 0)
    author_delta = StateDelta(
        entity_type="twitter_user",
        entity_id=EntityId(author_id),
        operation="update",
        fields={"tweet_count": old_tweet_count + 1},
        previous_fields={"tweet_count": old_tweet_count},
    )

    return ResponseProposal(
        response_body={"data": tweet_fields},
        proposed_state_deltas=[tweet_delta, original_delta, author_delta],
    )


# ---------------------------------------------------------------------------
# Like handlers
# ---------------------------------------------------------------------------


async def handle_like(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``like`` action.

    Idempotent: checks twitter_likes for an existing like. Creates a
    like entity and increments the tweet's like_count.
    """
    user_id = input_data["user_id"]
    tweet_id = input_data["tweet_id"]

    tweets = state.get("tweets", [])
    tweet = _find_entity(tweets, tweet_id)
    if tweet is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"Tweet '{tweet_id}' not found."),
        )

    # Idempotency check
    likes = state.get("twitter_likes", [])
    for like in likes:
        if like.get("user_id") == user_id and like.get("tweet_id") == tweet_id:
            return ResponseProposal(
                response_body={"data": {"liked": True}},
            )

    like_id = _new_id("like")
    now = _now_iso()

    like_fields: dict[str, Any] = {
        "id": like_id,
        "user_id": user_id,
        "tweet_id": tweet_id,
        "created_at": now,
    }

    like_delta = StateDelta(
        entity_type="like",
        entity_id=EntityId(like_id),
        operation="create",
        fields=like_fields,
    )

    # Increment tweet like_count
    old_like_count = tweet.get("like_count", 0)
    tweet_delta = StateDelta(
        entity_type="tweet",
        entity_id=EntityId(tweet_id),
        operation="update",
        fields={"like_count": old_like_count + 1},
        previous_fields={"like_count": old_like_count},
    )

    return ResponseProposal(
        response_body={"data": {"liked": True}},
        proposed_state_deltas=[like_delta, tweet_delta],
    )


async def handle_unlike(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``unlike`` action.

    Deletes the like entity and decrements the tweet's like_count.
    """
    user_id = input_data["user_id"]
    tweet_id = input_data["tweet_id"]

    tweets = state.get("tweets", [])
    tweet = _find_entity(tweets, tweet_id)
    if tweet is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"Tweet '{tweet_id}' not found."),
        )

    # Find the like
    likes = state.get("twitter_likes", [])
    existing_like = None
    for like in likes:
        if like.get("user_id") == user_id and like.get("tweet_id") == tweet_id:
            existing_like = like
            break

    if existing_like is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", "Like not found for this user and tweet."),
        )

    like_delta = StateDelta(
        entity_type="like",
        entity_id=EntityId(existing_like["id"]),
        operation="delete",
        fields=existing_like,
    )

    # Decrement tweet like_count
    old_like_count = tweet.get("like_count", 0)
    new_like_count = max(0, old_like_count - 1)
    tweet_delta = StateDelta(
        entity_type="tweet",
        entity_id=EntityId(tweet_id),
        operation="update",
        fields={"like_count": new_like_count},
        previous_fields={"like_count": old_like_count},
    )

    return ResponseProposal(
        response_body={"data": {"liked": False}},
        proposed_state_deltas=[like_delta, tweet_delta],
    )


# ---------------------------------------------------------------------------
# Follow handlers
# ---------------------------------------------------------------------------


async def handle_follow(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``follow`` action.

    Idempotent check. Creates a follow entity, increments the
    follower's following_count and the target's follower_count.
    """
    user_id = input_data["user_id"]
    target_user_id = input_data["target_user_id"]

    users = state.get("twitter_users", [])
    user = _find_entity(users, user_id)
    if user is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"User '{user_id}' not found."),
        )

    target = _find_entity(users, target_user_id)
    if target is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"User '{target_user_id}' not found."),
        )

    # Idempotency check
    follows = state.get("twitter_follows", [])
    for f in follows:
        if f.get("follower_id") == user_id and f.get("following_id") == target_user_id:
            return ResponseProposal(
                response_body={"data": {"following": True}},
            )

    follow_id = _new_id("follow")
    now = _now_iso()

    follow_fields: dict[str, Any] = {
        "id": follow_id,
        "follower_id": user_id,
        "following_id": target_user_id,
        "created_at": now,
    }

    follow_delta = StateDelta(
        entity_type="follow",
        entity_id=EntityId(follow_id),
        operation="create",
        fields=follow_fields,
    )

    # Increment follower's following_count
    old_following = user.get("following_count", 0)
    user_delta = StateDelta(
        entity_type="twitter_user",
        entity_id=EntityId(user_id),
        operation="update",
        fields={"following_count": old_following + 1},
        previous_fields={"following_count": old_following},
    )

    # Increment target's follower_count
    old_followers = target.get("follower_count", 0)
    target_delta = StateDelta(
        entity_type="twitter_user",
        entity_id=EntityId(target_user_id),
        operation="update",
        fields={"follower_count": old_followers + 1},
        previous_fields={"follower_count": old_followers},
    )

    return ResponseProposal(
        response_body={"data": {"following": True}},
        proposed_state_deltas=[follow_delta, user_delta, target_delta],
    )


async def handle_unfollow(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``unfollow`` action.

    Deletes the follow entity and decrements the follower's
    following_count and the target's follower_count.
    """
    user_id = input_data["user_id"]
    target_user_id = input_data["target_user_id"]

    users = state.get("twitter_users", [])
    user = _find_entity(users, user_id)
    if user is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"User '{user_id}' not found."),
        )

    target = _find_entity(users, target_user_id)
    if target is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"User '{target_user_id}' not found."),
        )

    # Find the follow relationship
    follows = state.get("twitter_follows", [])
    existing_follow = None
    for f in follows:
        if f.get("follower_id") == user_id and f.get("following_id") == target_user_id:
            existing_follow = f
            break

    if existing_follow is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", "Follow relationship not found."),
        )

    follow_delta = StateDelta(
        entity_type="follow",
        entity_id=EntityId(existing_follow["id"]),
        operation="delete",
        fields=existing_follow,
    )

    # Decrement follower's following_count
    old_following = user.get("following_count", 0)
    user_delta = StateDelta(
        entity_type="twitter_user",
        entity_id=EntityId(user_id),
        operation="update",
        fields={"following_count": max(0, old_following - 1)},
        previous_fields={"following_count": old_following},
    )

    # Decrement target's follower_count
    old_followers = target.get("follower_count", 0)
    target_delta = StateDelta(
        entity_type="twitter_user",
        entity_id=EntityId(target_user_id),
        operation="update",
        fields={"follower_count": max(0, old_followers - 1)},
        previous_fields={"follower_count": old_followers},
    )

    return ResponseProposal(
        response_body={"data": {"following": False}},
        proposed_state_deltas=[follow_delta, user_delta, target_delta],
    )


async def handle_get_followers(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``get_followers`` action.

    Lists followers of a user. Paginated. No state mutations.
    """
    user_id = input_data["id"]
    max_results = input_data.get("max_results", 20)
    pagination_token = input_data.get("pagination_token")

    follows = state.get("twitter_follows", [])
    users = state.get("twitter_users", [])

    # Find all follower IDs for this user
    follower_ids = [f["follower_id"] for f in follows if f.get("following_id") == user_id]

    # Resolve follower user objects
    followers = []
    for fid in follower_ids:
        u = _find_entity(users, fid)
        if u is not None:
            followers.append(u)

    # Pagination via token (index-based)
    start = int(pagination_token) if pagination_token else 0
    end = start + max_results
    paginated = followers[start:end]

    next_token = str(end) if end < len(followers) else None

    return ResponseProposal(
        response_body={
            "data": paginated,
            "meta": {
                "result_count": len(paginated),
                "next_token": next_token,
            },
        },
    )


async def handle_get_following(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``get_following`` action.

    Lists users that a user is following. Paginated. No state mutations.
    """
    user_id = input_data["id"]
    max_results = input_data.get("max_results", 20)
    pagination_token = input_data.get("pagination_token")

    follows = state.get("twitter_follows", [])
    users = state.get("twitter_users", [])

    # Find all following IDs for this user
    following_ids = [f["following_id"] for f in follows if f.get("follower_id") == user_id]

    # Resolve following user objects
    following = []
    for fid in following_ids:
        u = _find_entity(users, fid)
        if u is not None:
            following.append(u)

    # Pagination via token (index-based)
    start = int(pagination_token) if pagination_token else 0
    end = start + max_results
    paginated = following[start:end]

    next_token = str(end) if end < len(following) else None

    return ResponseProposal(
        response_body={
            "data": paginated,
            "meta": {
                "result_count": len(paginated),
                "next_token": next_token,
            },
        },
    )


# ---------------------------------------------------------------------------
# User handlers
# ---------------------------------------------------------------------------


async def handle_get_user(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``get_user`` action.

    Finds a single user by ID. No state mutations.
    """
    user_id = input_data["id"]
    users = state.get("twitter_users", [])
    user = _find_entity(users, user_id)

    if user is None:
        return ResponseProposal(
            response_body=_twitter_error("NotFound", f"User '{user_id}' not found."),
        )

    return ResponseProposal(
        response_body={"data": user},
    )


async def handle_user_tweets(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``user_tweets`` action.

    Returns a user's published tweets sorted by created_at desc. Paginated.
    No state mutations.
    """
    user_id = input_data["id"]
    max_results = input_data.get("max_results", 20)
    pagination_token = input_data.get("pagination_token")

    tweets = state.get("tweets", [])

    # Filter to user's published tweets
    user_tweets = [
        t for t in tweets if t.get("author_id") == user_id and t.get("status") == "published"
    ]

    # Sort by created_at desc
    user_tweets.sort(key=lambda t: t.get("created_at", ""), reverse=True)

    # Pagination via token (index-based)
    start = int(pagination_token) if pagination_token else 0
    end = start + max_results
    paginated = user_tweets[start:end]

    next_token = str(end) if end < len(user_tweets) else None

    return ResponseProposal(
        response_body={
            "data": paginated,
            "meta": {
                "result_count": len(paginated),
                "next_token": next_token,
                "newest_id": paginated[0]["id"] if paginated else None,
                "oldest_id": paginated[-1]["id"] if paginated else None,
            },
        },
    )
