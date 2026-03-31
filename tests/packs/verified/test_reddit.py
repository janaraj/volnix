"""Tests for terrarium.packs.verified.reddit -- RedditPack through pack's own handle_action."""

from __future__ import annotations

import pytest

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.verified.reddit.pack import RedditPack
from terrarium.packs.verified.reddit.state_machines import (
    REDDIT_POST_TRANSITIONS,
    REDDIT_USER_TRANSITIONS,
    SUBREDDIT_TRANSITIONS,
)


@pytest.fixture
def pack():
    return RedditPack()


@pytest.fixture
def sample_state():
    """State with subreddits, posts, comments, users, and votes."""
    return {
        "subreddits": [
            {
                "id": "sr-python",
                "name": "python",
                "display_name": "Python",
                "description": "News about the Python programming language",
                "rules": ["Be respectful"],
                "subscriber_count": 5,
                "moderator_ids": ["user-mod"],
                "topics": ["programming", "python"],
                "post_types_allowed": ["text", "link"],
                "visibility": "public",
                "status": "active",
                "created_at": "2025-01-01T00:00:00+00:00",
            },
            {
                "id": "sr-rust",
                "name": "rust",
                "display_name": "Rust",
                "description": "Rust programming language community",
                "rules": [],
                "subscriber_count": 3,
                "moderator_ids": [],
                "topics": ["programming", "rust"],
                "post_types_allowed": ["text", "link"],
                "visibility": "public",
                "status": "active",
                "created_at": "2025-02-01T00:00:00+00:00",
            },
            {
                "id": "sr-private",
                "name": "secretclub",
                "display_name": "Secret Club",
                "description": "Private subreddit",
                "rules": [],
                "subscriber_count": 1,
                "moderator_ids": [],
                "topics": [],
                "post_types_allowed": ["text"],
                "visibility": "private",
                "status": "active",
                "created_at": "2025-03-01T00:00:00+00:00",
            },
        ],
        "reddit_posts": [
            {
                "id": "t3_post1",
                "subreddit_id": "sr-python",
                "author_id": "user-alice",
                "title": "How to learn Python fast",
                "body": "I want to get started with Python quickly",
                "url": None,
                "post_type": "text",
                "flair": None,
                "upvotes": 10,
                "downvotes": 2,
                "score": 8,
                "comment_count": 2,
                "crosspost_parent_id": None,
                "is_pinned": False,
                "is_locked": False,
                "is_nsfw": False,
                "is_spoiler": False,
                "awards": [],
                "status": "published",
                "created_at": "2026-03-20T10:00:00+00:00",
                "updated_at": "2026-03-20T10:00:00+00:00",
            },
            {
                "id": "t3_post2",
                "subreddit_id": "sr-python",
                "author_id": "user-bob",
                "title": "Advanced Python decorators guide",
                "body": "Decorators are a powerful feature of Python",
                "url": None,
                "post_type": "text",
                "flair": "tutorial",
                "upvotes": 25,
                "downvotes": 1,
                "score": 24,
                "comment_count": 0,
                "crosspost_parent_id": None,
                "is_pinned": False,
                "is_locked": False,
                "is_nsfw": False,
                "is_spoiler": False,
                "awards": [],
                "status": "published",
                "created_at": "2026-03-21T08:00:00+00:00",
                "updated_at": "2026-03-21T08:00:00+00:00",
            },
            {
                "id": "t3_post3",
                "subreddit_id": "sr-rust",
                "author_id": "user-alice",
                "title": "Rust for beginners",
                "body": "Getting started with Rust",
                "url": None,
                "post_type": "text",
                "flair": None,
                "upvotes": 3,
                "downvotes": 0,
                "score": 3,
                "comment_count": 0,
                "crosspost_parent_id": None,
                "is_pinned": False,
                "is_locked": False,
                "is_nsfw": False,
                "is_spoiler": False,
                "awards": [],
                "status": "published",
                "created_at": "2026-03-22T12:00:00+00:00",
                "updated_at": "2026-03-22T12:00:00+00:00",
            },
        ],
        "reddit_comments": [
            {
                "id": "t1_c1",
                "post_id": "t3_post1",
                "parent_id": None,
                "author_id": "user-bob",
                "body": "Start with the official tutorial!",
                "upvotes": 5,
                "downvotes": 0,
                "score": 5,
                "depth": 0,
                "reply_count": 1,
                "is_stickied": False,
                "status": "published",
                "created_at": "2026-03-20T11:00:00+00:00",
                "updated_at": "2026-03-20T11:00:00+00:00",
            },
            {
                "id": "t1_c2",
                "post_id": "t3_post1",
                "parent_id": "t1_c1",
                "author_id": "user-alice",
                "body": "Thanks for the tip!",
                "upvotes": 2,
                "downvotes": 0,
                "score": 2,
                "depth": 1,
                "reply_count": 0,
                "is_stickied": False,
                "status": "published",
                "created_at": "2026-03-20T12:00:00+00:00",
                "updated_at": "2026-03-20T12:00:00+00:00",
            },
        ],
        "reddit_users": [
            {
                "id": "user-alice",
                "username": "alice_coder",
                "display_name": "Alice",
                "bio": "Python and Rust enthusiast",
                "avatar_url": "",
                "post_karma": 11,
                "comment_karma": 2,
                "is_moderator": False,
                "subscribed_subreddit_ids": ["sr-python"],
                "status": "active",
                "created_at": "2025-01-01T00:00:00+00:00",
            },
            {
                "id": "user-bob",
                "username": "bob_dev",
                "display_name": "Bob",
                "bio": "Coding all day",
                "avatar_url": "",
                "post_karma": 24,
                "comment_karma": 5,
                "is_moderator": False,
                "subscribed_subreddit_ids": ["sr-python", "sr-rust"],
                "status": "active",
                "created_at": "2025-02-01T00:00:00+00:00",
            },
            {
                "id": "user-mod",
                "username": "mod_supreme",
                "display_name": "Mod",
                "bio": "Moderator",
                "avatar_url": "",
                "post_karma": 0,
                "comment_karma": 0,
                "is_moderator": True,
                "subscribed_subreddit_ids": [],
                "status": "active",
                "created_at": "2025-01-01T00:00:00+00:00",
            },
        ],
        "reddit_votes": [
            {
                "id": "vote-existing",
                "user_id": "user-alice",
                "target_id": "t3_post2",
                "target_type": "post",
                "direction": "up",
            },
        ],
    }


# =========================================================================
# State machine tests (4)
# =========================================================================


class TestStateMachines:
    def test_post_published_to_removed(self):
        """Published posts can transition to removed."""
        assert "removed" in REDDIT_POST_TRANSITIONS["published"]

    def test_post_removed_to_published(self):
        """Removed posts can be restored (mod restore)."""
        assert "published" in REDDIT_POST_TRANSITIONS["removed"]

    def test_post_spam_is_terminal(self):
        """Spam is a terminal state with no outgoing transitions."""
        assert REDDIT_POST_TRANSITIONS["spam"] == []

    def test_subreddit_quarantine_to_banned(self):
        """Quarantined subreddits can transition to banned."""
        assert "banned" in SUBREDDIT_TRANSITIONS["quarantined"]
        # Also verify quarantined can return to active
        assert "active" in SUBREDDIT_TRANSITIONS["quarantined"]
        # Banned is terminal
        assert SUBREDDIT_TRANSITIONS["banned"] == []


# =========================================================================
# Subreddit operations (3)
# =========================================================================


class TestSubredditOperations:
    async def test_subreddits_search_matches(self, pack, sample_state):
        """Searching for 'python' returns the python subreddit."""
        result = await pack.handle_action(
            ToolName("subreddits_search"),
            {"query": "python"},
            sample_state,
        )
        assert isinstance(result, ResponseProposal)
        body = result.response_body
        assert body["count"] >= 1
        names = [s["name"] for s in body["subreddits"]]
        assert "python" in names

    async def test_subreddit_about_found(self, pack, sample_state):
        """Getting details for an existing subreddit returns it."""
        result = await pack.handle_action(
            ToolName("subreddit_about"),
            {"subreddit": "python"},
            sample_state,
        )
        assert result.response_body["subreddit"]["id"] == "sr-python"
        assert result.response_body["subreddit"]["display_name"] == "Python"

    async def test_subreddit_about_not_found(self, pack, sample_state):
        """Getting a non-existent subreddit returns NOT_FOUND error."""
        result = await pack.handle_action(
            ToolName("subreddit_about"),
            {"subreddit": "nonexistent"},
            sample_state,
        )
        assert result.response_body["error"] == "NOT_FOUND"


# =========================================================================
# Post operations (7)
# =========================================================================


class TestPostOperations:
    async def test_submit_creates_post_with_auto_upvote(self, pack, sample_state):
        """Submitting a post creates a post with upvotes=1, score=1, and a vote record."""
        result = await pack.handle_action(
            ToolName("submit"),
            {
                "sr": "python",
                "title": "My new post",
                "text": "Hello everyone!",
                "kind": "text",
                "author_id": "user-alice",
            },
            sample_state,
        )
        body = result.response_body
        assert "post" in body
        assert body["post"]["upvotes"] == 1
        assert body["post"]["score"] == 1
        assert body["post"]["status"] == "published"
        assert body["post"]["title"] == "My new post"

        # Check deltas: should have post create, vote create, and karma update
        deltas = result.proposed_state_deltas
        assert len(deltas) == 3

        # Post delta
        post_delta = deltas[0]
        assert post_delta.entity_type == "reddit_post"
        assert post_delta.operation == "create"
        assert post_delta.fields["upvotes"] == 1

        # Vote delta (auto-upvote)
        vote_delta = deltas[1]
        assert vote_delta.entity_type == "vote"
        assert vote_delta.operation == "create"
        assert vote_delta.fields["direction"] == "up"
        assert vote_delta.fields["user_id"] == "user-alice"

        # Karma delta
        karma_delta = deltas[2]
        assert karma_delta.entity_type == "reddit_user"
        assert karma_delta.operation == "update"
        assert karma_delta.fields["post_karma"] == 12  # was 11, +1

    async def test_submit_validates_subreddit_exists(self, pack, sample_state):
        """Submitting to a non-existent subreddit returns an error."""
        result = await pack.handle_action(
            ToolName("submit"),
            {
                "sr": "nonexistent",
                "title": "Test post",
                "kind": "text",
                "author_id": "user-alice",
            },
            sample_state,
        )
        assert result.response_body["error"] == "NOT_FOUND"
        assert len(result.proposed_state_deltas) == 0

    async def test_post_detail_found(self, pack, sample_state):
        """Getting an existing post by ID returns its data."""
        result = await pack.handle_action(
            ToolName("post_detail"),
            {"id": "t3_post1"},
            sample_state,
        )
        assert result.response_body["post"]["id"] == "t3_post1"
        assert result.response_body["post"]["title"] == "How to learn Python fast"

    async def test_post_detail_not_found(self, pack, sample_state):
        """Getting a non-existent post returns NOT_FOUND."""
        result = await pack.handle_action(
            ToolName("post_detail"),
            {"id": "t3_doesnotexist"},
            sample_state,
        )
        assert result.response_body["error"] == "NOT_FOUND"

    async def test_subreddit_hot_sort_order(self, pack, sample_state):
        """Hot sort returns posts ordered by hot score (score / age)."""
        result = await pack.handle_action(
            ToolName("subreddit_hot"),
            {"subreddit": "python"},
            sample_state,
        )
        posts = result.response_body["posts"]
        assert len(posts) == 2
        # post2 has higher score (24) and is newer than post1 (8), so hot score
        # should put post2 first.
        assert posts[0]["id"] == "t3_post2"
        assert posts[1]["id"] == "t3_post1"

    async def test_subreddit_new_sort_order(self, pack, sample_state):
        """New sort returns posts in descending created_at order."""
        result = await pack.handle_action(
            ToolName("subreddit_new"),
            {"subreddit": "python"},
            sample_state,
        )
        posts = result.response_body["posts"]
        assert len(posts) == 2
        # post2 was created later (2026-03-21) than post1 (2026-03-20)
        assert posts[0]["id"] == "t3_post2"
        assert posts[1]["id"] == "t3_post1"

    async def test_search_by_title_and_body(self, pack, sample_state):
        """Search finds posts matching query in title or body."""
        result = await pack.handle_action(
            ToolName("search"),
            {"q": "decorators"},
            sample_state,
        )
        posts = result.response_body["posts"]
        assert len(posts) == 1
        assert posts[0]["id"] == "t3_post2"

        # Search for something appearing only in body
        result2 = await pack.handle_action(
            ToolName("search"),
            {"q": "quickly"},
            sample_state,
        )
        posts2 = result2.response_body["posts"]
        assert len(posts2) == 1
        assert posts2[0]["id"] == "t3_post1"


# =========================================================================
# Comments (5)
# =========================================================================


class TestComments:
    async def test_comment_top_level(self, pack, sample_state):
        """A top-level comment on a post has depth=0."""
        result = await pack.handle_action(
            ToolName("comment"),
            {
                "parent": "t3_post2",
                "text": "Great tutorial!",
                "author_id": "user-alice",
            },
            sample_state,
        )
        body = result.response_body
        assert "comment" in body
        assert body["comment"]["depth"] == 0
        assert body["comment"]["post_id"] == "t3_post2"
        assert body["comment"]["parent_id"] is None

    async def test_comment_nested_reply(self, pack, sample_state):
        """Replying to a comment sets depth = parent.depth + 1."""
        result = await pack.handle_action(
            ToolName("comment"),
            {
                "parent": "t1_c1",  # depth=0 comment
                "text": "I agree with this!",
                "author_id": "user-alice",
            },
            sample_state,
        )
        body = result.response_body
        assert body["comment"]["depth"] == 1
        assert body["comment"]["parent_id"] == "t1_c1"
        assert body["comment"]["post_id"] == "t3_post1"

    async def test_comment_increments_post_count(self, pack, sample_state):
        """Commenting on a post produces a delta incrementing comment_count."""
        result = await pack.handle_action(
            ToolName("comment"),
            {
                "parent": "t3_post2",
                "text": "Nice work!",
                "author_id": "user-bob",
            },
            sample_state,
        )
        # Find the post update delta
        post_deltas = [
            d
            for d in result.proposed_state_deltas
            if d.entity_type == "reddit_post" and d.operation == "update"
        ]
        assert len(post_deltas) == 1
        assert post_deltas[0].fields["comment_count"] == 1  # was 0, now 1

    async def test_post_comments_returns_tree(self, pack, sample_state):
        """Listing comments for a post returns all published comments."""
        result = await pack.handle_action(
            ToolName("post_comments"),
            {"id": "t3_post1"},
            sample_state,
        )
        body = result.response_body
        assert body["count"] == 2
        comment_ids = [c["id"] for c in body["comments"]]
        assert "t1_c1" in comment_ids
        assert "t1_c2" in comment_ids

    async def test_comment_on_nonexistent_post_error(self, pack, sample_state):
        """Commenting on a non-existent post returns NOT_FOUND."""
        result = await pack.handle_action(
            ToolName("comment"),
            {
                "parent": "t3_ghost",
                "text": "Hello?",
                "author_id": "user-alice",
            },
            sample_state,
        )
        assert result.response_body["error"] == "NOT_FOUND"


# =========================================================================
# Voting (6)
# =========================================================================


class TestVoting:
    async def test_upvote_increments_score(self, pack, sample_state):
        """A new upvote on a post increments score by 1."""
        result = await pack.handle_action(
            ToolName("vote"),
            {"id": "t3_post3", "dir": 1, "user_id": "user-bob"},
            sample_state,
        )
        assert result.response_body["ok"] is True
        # Find the target update delta
        target_deltas = [
            d
            for d in result.proposed_state_deltas
            if d.entity_type == "reddit_post" and d.operation == "update"
        ]
        assert len(target_deltas) == 1
        assert target_deltas[0].fields["score"] == 4  # was 3, +1
        assert target_deltas[0].fields["upvotes"] == 4  # was 3, +1

    async def test_downvote_decrements_score(self, pack, sample_state):
        """A new downvote on a post decrements score by 1."""
        result = await pack.handle_action(
            ToolName("vote"),
            {"id": "t3_post3", "dir": -1, "user_id": "user-bob"},
            sample_state,
        )
        assert result.response_body["ok"] is True
        target_deltas = [
            d
            for d in result.proposed_state_deltas
            if d.entity_type == "reddit_post" and d.operation == "update"
        ]
        assert len(target_deltas) == 1
        assert target_deltas[0].fields["score"] == 2  # was 3, -1
        assert target_deltas[0].fields["downvotes"] == 1  # was 0, +1

    async def test_flip_vote_adjusts_by_two(self, pack, sample_state):
        """Flipping from up to down changes score by -2."""
        # user-alice has an existing upvote on t3_post2
        result = await pack.handle_action(
            ToolName("vote"),
            {"id": "t3_post2", "dir": -1, "user_id": "user-alice"},
            sample_state,
        )
        assert result.response_body["ok"] is True

        # Vote direction should be updated
        vote_deltas = [
            d
            for d in result.proposed_state_deltas
            if d.entity_type == "vote" and d.operation == "update"
        ]
        assert len(vote_deltas) == 1
        assert vote_deltas[0].fields["direction"] == "down"
        assert vote_deltas[0].previous_fields["direction"] == "up"

        # Score adjusts by -2 (remove +1, add -1)
        target_deltas = [
            d
            for d in result.proposed_state_deltas
            if d.entity_type == "reddit_post" and d.operation == "update"
        ]
        assert len(target_deltas) == 1
        assert target_deltas[0].fields["score"] == 22  # was 24, -2

    async def test_duplicate_same_direction_noop(self, pack, sample_state):
        """Voting the same direction twice is a no-op."""
        # user-alice already has an upvote on t3_post2
        result = await pack.handle_action(
            ToolName("vote"),
            {"id": "t3_post2", "dir": 1, "user_id": "user-alice"},
            sample_state,
        )
        assert result.response_body["ok"] is True
        assert len(result.proposed_state_deltas) == 0

    async def test_unvote_removes_vote(self, pack, sample_state):
        """Unvoting (dir=0) removes the existing vote and adjusts score."""
        # user-alice has an existing upvote on t3_post2
        result = await pack.handle_action(
            ToolName("vote"),
            {"id": "t3_post2", "dir": 0, "user_id": "user-alice"},
            sample_state,
        )
        assert result.response_body["ok"] is True

        # Vote should be deleted
        vote_deltas = [
            d
            for d in result.proposed_state_deltas
            if d.entity_type == "vote" and d.operation == "delete"
        ]
        assert len(vote_deltas) == 1

        # Score goes down by 1 (was an upvote)
        target_deltas = [
            d
            for d in result.proposed_state_deltas
            if d.entity_type == "reddit_post" and d.operation == "update"
        ]
        assert len(target_deltas) == 1
        assert target_deltas[0].fields["score"] == 23  # was 24, -1

    async def test_vote_updates_author_karma(self, pack, sample_state):
        """Voting updates the post author's karma."""
        # Upvote post3 (author: user-alice, post_karma: 11)
        result = await pack.handle_action(
            ToolName("vote"),
            {"id": "t3_post3", "dir": 1, "user_id": "user-bob"},
            sample_state,
        )
        karma_deltas = [
            d
            for d in result.proposed_state_deltas
            if d.entity_type == "reddit_user" and d.operation == "update"
        ]
        assert len(karma_deltas) == 1
        assert karma_deltas[0].fields["post_karma"] == 12  # was 11, +1
        assert karma_deltas[0].entity_id == "user-alice"


# =========================================================================
# Feed & discovery (3)
# =========================================================================


class TestFeedAndDiscovery:
    async def test_best_feed_from_subscriptions(self, pack, sample_state):
        """Best feed returns only posts from subscribed subreddits."""
        # user-alice subscribes to sr-python only
        result = await pack.handle_action(
            ToolName("best"),
            {"user_id": "user-alice"},
            sample_state,
        )
        posts = result.response_body["posts"]
        # Should only include posts from sr-python
        for p in posts:
            assert p["subreddit_id"] == "sr-python"
        assert len(posts) == 2

    async def test_popular_returns_all_public(self, pack, sample_state):
        """Popular returns posts from all public, active subreddits."""
        result = await pack.handle_action(
            ToolName("popular"),
            {},
            sample_state,
        )
        posts = result.response_body["posts"]
        # Should include posts from sr-python (public) and sr-rust (public)
        # but not sr-private
        sub_ids = {p["subreddit_id"] for p in posts}
        assert "sr-python" in sub_ids
        assert "sr-rust" in sub_ids
        assert "sr-private" not in sub_ids
        assert len(posts) == 3

    async def test_user_submitted_returns_author_posts(self, pack, sample_state):
        """User submitted returns only posts by that user."""
        result = await pack.handle_action(
            ToolName("user_submitted"),
            {"username": "alice_coder"},
            sample_state,
        )
        posts = result.response_body["posts"]
        assert len(posts) == 2
        for p in posts:
            assert p["author_id"] == "user-alice"


# =========================================================================
# Subscribe (2)
# =========================================================================


class TestSubscribe:
    async def test_subscribe_adds_to_user_list(self, pack, sample_state):
        """Subscribing adds the subreddit to the user's subscribed list."""
        # user-alice is not subscribed to rust
        result = await pack.handle_action(
            ToolName("subscribe"),
            {"subreddit": "rust", "user_id": "user-alice"},
            sample_state,
        )
        assert result.response_body["ok"] is True

        # Check user delta: subscribed_subreddit_ids now includes sr-rust
        user_deltas = [
            d
            for d in result.proposed_state_deltas
            if d.entity_type == "reddit_user"
        ]
        assert len(user_deltas) == 1
        assert "sr-rust" in user_deltas[0].fields["subscribed_subreddit_ids"]

        # Check subreddit delta: subscriber_count incremented
        sub_deltas = [
            d
            for d in result.proposed_state_deltas
            if d.entity_type == "subreddit"
        ]
        assert len(sub_deltas) == 1
        assert sub_deltas[0].fields["subscriber_count"] == 4  # was 3, +1

    async def test_unsubscribe_removes_from_list(self, pack, sample_state):
        """Unsubscribing removes the subreddit from the user's subscribed list."""
        # user-alice is subscribed to sr-python
        result = await pack.handle_action(
            ToolName("unsubscribe"),
            {"subreddit": "python", "user_id": "user-alice"},
            sample_state,
        )
        assert result.response_body["ok"] is True

        # Check user delta: subscribed_subreddit_ids no longer includes sr-python
        user_deltas = [
            d
            for d in result.proposed_state_deltas
            if d.entity_type == "reddit_user"
        ]
        assert len(user_deltas) == 1
        assert "sr-python" not in user_deltas[0].fields["subscribed_subreddit_ids"]

        # Check subreddit delta: subscriber_count decremented
        sub_deltas = [
            d
            for d in result.proposed_state_deltas
            if d.entity_type == "subreddit"
        ]
        assert len(sub_deltas) == 1
        assert sub_deltas[0].fields["subscriber_count"] == 4  # was 5, -1
