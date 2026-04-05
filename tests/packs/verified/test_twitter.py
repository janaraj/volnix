"""Tests for volnix.packs.verified.twitter -- TwitterPack through pack's own handle_action."""

import pytest

from volnix.core.context import ResponseProposal
from volnix.core.errors import PackNotFoundError
from volnix.core.types import ToolName
from volnix.packs.verified.twitter.pack import TwitterPack
from volnix.packs.verified.twitter.state_machines import (
    TWEET_STATES,
    TWEET_TRANSITIONS,
    TWITTER_USER_STATES,
    TWITTER_USER_TRANSITIONS,
)


@pytest.fixture
def pack():
    return TwitterPack()


@pytest.fixture
def alice():
    return {
        "id": "user-alice",
        "username": "alice",
        "display_name": "Alice",
        "bio": "Hello world",
        "avatar_url": "https://example.com/alice.png",
        "location": "NYC",
        "website_url": None,
        "follower_count": 10,
        "following_count": 5,
        "tweet_count": 3,
        "verified": False,
        "status": "active",
        "created_at": "2025-01-01T00:00:00+00:00",
    }


@pytest.fixture
def bob():
    return {
        "id": "user-bob",
        "username": "bob",
        "display_name": "Bob",
        "bio": "Just Bob",
        "avatar_url": "https://example.com/bob.png",
        "location": "SF",
        "website_url": None,
        "follower_count": 20,
        "following_count": 15,
        "tweet_count": 7,
        "verified": True,
        "status": "active",
        "created_at": "2025-02-01T00:00:00+00:00",
    }


@pytest.fixture
def tweet_a():
    """A published tweet by alice."""
    return {
        "id": "tweet-aaa",
        "author_id": "user-alice",
        "text": "Hello #python and @bob!",
        "tweet_type": "original",
        "reply_to_tweet_id": None,
        "retweet_of_id": None,
        "quote_of_id": None,
        "hashtags": ["python"],
        "mentions": ["bob"],
        "media_urls": [],
        "link_url": None,
        "like_count": 5,
        "retweet_count": 2,
        "quote_count": 1,
        "reply_count": 0,
        "view_count": 100,
        "bookmark_count": 0,
        "is_pinned": False,
        "status": "published",
        "created_at": "2026-03-01T10:00:00+00:00",
    }


@pytest.fixture
def tweet_b():
    """A second published tweet by bob."""
    return {
        "id": "tweet-bbb",
        "author_id": "user-bob",
        "text": "Rust is great #rust",
        "tweet_type": "original",
        "reply_to_tweet_id": None,
        "retweet_of_id": None,
        "quote_of_id": None,
        "hashtags": ["rust"],
        "mentions": [],
        "media_urls": [],
        "link_url": None,
        "like_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
        "reply_count": 0,
        "view_count": 50,
        "bookmark_count": 0,
        "is_pinned": False,
        "status": "published",
        "created_at": "2026-03-02T12:00:00+00:00",
    }


@pytest.fixture
def deleted_tweet():
    """A deleted tweet by alice."""
    return {
        "id": "tweet-del",
        "author_id": "user-alice",
        "text": "This was deleted",
        "tweet_type": "original",
        "reply_to_tweet_id": None,
        "retweet_of_id": None,
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
        "status": "deleted",
        "created_at": "2026-02-15T08:00:00+00:00",
    }


@pytest.fixture
def sample_state(alice, bob, tweet_a, tweet_b, deleted_tweet):
    return {
        "twitter_users": [alice, bob],
        "tweets": [tweet_a, tweet_b, deleted_tweet],
        "twitter_likes": [],
        "twitter_follows": [],
    }


# ---------------------------------------------------------------------------
# State machines
# ---------------------------------------------------------------------------


class TestStateMachines:
    def test_tweet_deleted_is_terminal(self):
        """The 'deleted' tweet state has no outgoing transitions (terminal)."""
        assert TWEET_TRANSITIONS["deleted"] == []
        assert "published" in TWEET_TRANSITIONS
        assert "deleted" in TWEET_TRANSITIONS["published"]
        assert set(TWEET_STATES) == set(TWEET_TRANSITIONS.keys())

    def test_user_suspend_and_reinstate(self):
        """A user can be suspended from active and reinstated back to active."""
        assert "suspended" in TWITTER_USER_TRANSITIONS["active"]
        assert "active" in TWITTER_USER_TRANSITIONS["suspended"]
        assert "deactivated" in TWITTER_USER_TRANSITIONS["active"]
        assert "active" in TWITTER_USER_TRANSITIONS["deactivated"]
        assert set(TWITTER_USER_STATES) == set(TWITTER_USER_TRANSITIONS.keys())


# ---------------------------------------------------------------------------
# Tweet CRUD
# ---------------------------------------------------------------------------


class TestTweetCRUD:
    async def test_create_tweet(self, pack, sample_state):
        """create_tweet creates a tweet and increments author tweet_count."""
        proposal = await pack.handle_action(
            ToolName("create_tweet"),
            {"text": "My first tweet!", "author_id": "user-alice"},
            sample_state,
        )
        assert isinstance(proposal, ResponseProposal)
        data = proposal.response_body["data"]
        assert data["text"] == "My first tweet!"
        assert data["author_id"] == "user-alice"
        assert data["tweet_type"] == "original"
        assert data["status"] == "published"
        assert data["like_count"] == 0
        assert "id" in data
        assert "created_at" in data

        # Two deltas: tweet create + author tweet_count update
        assert len(proposal.proposed_state_deltas) == 2
        tweet_delta = proposal.proposed_state_deltas[0]
        author_delta = proposal.proposed_state_deltas[1]
        assert tweet_delta.entity_type == "tweet"
        assert tweet_delta.operation == "create"
        assert author_delta.entity_type == "twitter_user"
        assert author_delta.operation == "update"
        assert author_delta.fields["tweet_count"] == 4  # was 3

    async def test_create_tweet_280_char_limit(self, pack, sample_state):
        """create_tweet returns error if text exceeds 280 characters."""
        long_text = "x" * 281
        proposal = await pack.handle_action(
            ToolName("create_tweet"),
            {"text": long_text, "author_id": "user-alice"},
            sample_state,
        )
        assert "errors" in proposal.response_body
        assert proposal.response_body["errors"][0]["title"] == "InvalidRequest"
        assert "280" in proposal.response_body["errors"][0]["detail"]
        assert proposal.proposed_state_deltas == []

    async def test_create_tweet_extracts_hashtags(self, pack, sample_state):
        """create_tweet auto-extracts hashtags from text."""
        proposal = await pack.handle_action(
            ToolName("create_tweet"),
            {"text": "Love #Python and #AI!", "author_id": "user-alice"},
            sample_state,
        )
        data = proposal.response_body["data"]
        assert set(data["hashtags"]) == {"Python", "AI"}

    async def test_create_tweet_extracts_mentions(self, pack, sample_state):
        """create_tweet auto-extracts @mentions from text."""
        proposal = await pack.handle_action(
            ToolName("create_tweet"),
            {"text": "Hey @bob and @carol check this out", "author_id": "user-alice"},
            sample_state,
        )
        data = proposal.response_body["data"]
        assert set(data["mentions"]) == {"bob", "carol"}

    async def test_get_tweet_found(self, pack, sample_state):
        """get_tweet returns the tweet when it exists."""
        proposal = await pack.handle_action(
            ToolName("get_tweet"),
            {"id": "tweet-aaa"},
            sample_state,
        )
        assert proposal.response_body["data"]["id"] == "tweet-aaa"
        assert proposal.response_body["data"]["text"] == "Hello #python and @bob!"
        assert proposal.proposed_state_deltas == []

    async def test_get_tweet_not_found(self, pack, sample_state):
        """get_tweet returns error for a nonexistent tweet."""
        proposal = await pack.handle_action(
            ToolName("get_tweet"),
            {"id": "tweet-nonexistent"},
            sample_state,
        )
        assert "errors" in proposal.response_body
        assert proposal.response_body["errors"][0]["title"] == "NotFound"
        assert proposal.proposed_state_deltas == []


# ---------------------------------------------------------------------------
# Reply / Retweet / Quote
# ---------------------------------------------------------------------------


class TestReplyRetweetQuote:
    async def test_reply_increments_reply_count(self, pack, sample_state):
        """reply creates a reply tweet and increments parent reply_count."""
        proposal = await pack.handle_action(
            ToolName("reply"),
            {
                "text": "Great point!",
                "author_id": "user-bob",
                "in_reply_to_tweet_id": "tweet-aaa",
            },
            sample_state,
        )
        data = proposal.response_body["data"]
        assert data["tweet_type"] == "reply"
        assert data["reply_to_tweet_id"] == "tweet-aaa"
        assert data["author_id"] == "user-bob"

        # Three deltas: reply create, parent reply_count, author tweet_count
        assert len(proposal.proposed_state_deltas) == 3
        parent_delta = proposal.proposed_state_deltas[1]
        assert parent_delta.entity_type == "tweet"
        assert parent_delta.fields["reply_count"] == 1  # was 0

    async def test_retweet_creates_entity_and_increments_count(self, pack, sample_state):
        """retweet creates a retweet entity and increments retweet_count."""
        proposal = await pack.handle_action(
            ToolName("retweet"),
            {"user_id": "user-bob", "tweet_id": "tweet-aaa"},
            sample_state,
        )
        assert proposal.response_body["data"]["retweeted"] is True

        # Three deltas: retweet create, original retweet_count, user tweet_count
        assert len(proposal.proposed_state_deltas) == 3
        retweet_delta = proposal.proposed_state_deltas[0]
        assert retweet_delta.operation == "create"
        assert retweet_delta.fields["tweet_type"] == "retweet"
        assert retweet_delta.fields["retweet_of_id"] == "tweet-aaa"

        original_delta = proposal.proposed_state_deltas[1]
        assert original_delta.fields["retweet_count"] == 3  # was 2

    async def test_unretweet_decrements_count(self, pack, sample_state):
        """unretweet marks retweet as deleted and decrements retweet_count."""
        # Add a retweet by bob of tweet-aaa to the state
        retweet = {
            "id": "tweet-rt-bob",
            "author_id": "user-bob",
            "text": "",
            "tweet_type": "retweet",
            "reply_to_tweet_id": None,
            "retweet_of_id": "tweet-aaa",
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
            "created_at": "2026-03-03T00:00:00+00:00",
        }
        sample_state["tweets"].append(retweet)

        proposal = await pack.handle_action(
            ToolName("unretweet"),
            {"user_id": "user-bob", "tweet_id": "tweet-aaa"},
            sample_state,
        )
        assert proposal.response_body["data"]["retweeted"] is False

        # Two deltas: retweet status->deleted, original retweet_count decremented
        assert len(proposal.proposed_state_deltas) == 2
        rt_delta = proposal.proposed_state_deltas[0]
        assert rt_delta.fields["status"] == "deleted"
        orig_delta = proposal.proposed_state_deltas[1]
        assert orig_delta.fields["retweet_count"] == 1  # was 2

    async def test_quote_tweet_with_text(self, pack, sample_state):
        """quote_tweet creates a quote tweet with the given text."""
        proposal = await pack.handle_action(
            ToolName("quote_tweet"),
            {
                "text": "This is so true!",
                "author_id": "user-bob",
                "quote_tweet_id": "tweet-aaa",
            },
            sample_state,
        )
        data = proposal.response_body["data"]
        assert data["tweet_type"] == "quote"
        assert data["quote_of_id"] == "tweet-aaa"
        assert data["text"] == "This is so true!"
        assert data["author_id"] == "user-bob"

    async def test_quote_increments_quote_count(self, pack, sample_state):
        """quote_tweet increments the original tweet's quote_count."""
        proposal = await pack.handle_action(
            ToolName("quote_tweet"),
            {
                "text": "Interesting take",
                "author_id": "user-bob",
                "quote_tweet_id": "tweet-aaa",
            },
            sample_state,
        )
        # Three deltas: quote create, original quote_count, author tweet_count
        assert len(proposal.proposed_state_deltas) == 3
        orig_delta = proposal.proposed_state_deltas[1]
        assert orig_delta.entity_type == "tweet"
        assert orig_delta.fields["quote_count"] == 2  # was 1


# ---------------------------------------------------------------------------
# Likes
# ---------------------------------------------------------------------------


class TestLikes:
    async def test_like_creates_record_and_increments(self, pack, sample_state):
        """like creates a like entity and increments tweet like_count."""
        proposal = await pack.handle_action(
            ToolName("like"),
            {"user_id": "user-bob", "tweet_id": "tweet-aaa"},
            sample_state,
        )
        assert proposal.response_body["data"]["liked"] is True

        # Two deltas: like create + tweet like_count update
        assert len(proposal.proposed_state_deltas) == 2
        like_delta = proposal.proposed_state_deltas[0]
        assert like_delta.entity_type == "like"
        assert like_delta.operation == "create"
        assert like_delta.fields["user_id"] == "user-bob"
        assert like_delta.fields["tweet_id"] == "tweet-aaa"

        tweet_delta = proposal.proposed_state_deltas[1]
        assert tweet_delta.fields["like_count"] == 6  # was 5

    async def test_like_idempotent_error(self, pack, sample_state):
        """like returns liked=True with no deltas if already liked."""
        sample_state["twitter_likes"] = [
            {
                "id": "like-existing",
                "user_id": "user-bob",
                "tweet_id": "tweet-aaa",
                "created_at": "2026-03-01T00:00:00+00:00",
            }
        ]
        proposal = await pack.handle_action(
            ToolName("like"),
            {"user_id": "user-bob", "tweet_id": "tweet-aaa"},
            sample_state,
        )
        assert proposal.response_body["data"]["liked"] is True
        assert proposal.proposed_state_deltas == []

    async def test_unlike_decrements(self, pack, sample_state):
        """unlike deletes the like and decrements tweet like_count."""
        sample_state["twitter_likes"] = [
            {
                "id": "like-001",
                "user_id": "user-bob",
                "tweet_id": "tweet-aaa",
                "created_at": "2026-03-01T00:00:00+00:00",
            }
        ]
        proposal = await pack.handle_action(
            ToolName("unlike"),
            {"user_id": "user-bob", "tweet_id": "tweet-aaa"},
            sample_state,
        )
        assert proposal.response_body["data"]["liked"] is False

        # Two deltas: like delete + tweet like_count update
        assert len(proposal.proposed_state_deltas) == 2
        like_delta = proposal.proposed_state_deltas[0]
        assert like_delta.entity_type == "like"
        assert like_delta.operation == "delete"

        tweet_delta = proposal.proposed_state_deltas[1]
        assert tweet_delta.fields["like_count"] == 4  # was 5

    async def test_unlike_nonexistent_error(self, pack, sample_state):
        """unlike returns error if the like does not exist."""
        proposal = await pack.handle_action(
            ToolName("unlike"),
            {"user_id": "user-bob", "tweet_id": "tweet-aaa"},
            sample_state,
        )
        assert "errors" in proposal.response_body
        assert proposal.response_body["errors"][0]["title"] == "NotFound"
        assert proposal.proposed_state_deltas == []


# ---------------------------------------------------------------------------
# Social graph
# ---------------------------------------------------------------------------


class TestSocialGraph:
    async def test_follow_increments_both_counts(self, pack, sample_state):
        """follow creates a follow entity and increments both user counts."""
        proposal = await pack.handle_action(
            ToolName("follow"),
            {"user_id": "user-alice", "target_user_id": "user-bob"},
            sample_state,
        )
        assert proposal.response_body["data"]["following"] is True

        # Three deltas: follow create, alice following_count, bob follower_count
        assert len(proposal.proposed_state_deltas) == 3
        follow_delta = proposal.proposed_state_deltas[0]
        assert follow_delta.entity_type == "follow"
        assert follow_delta.operation == "create"
        assert follow_delta.fields["follower_id"] == "user-alice"
        assert follow_delta.fields["following_id"] == "user-bob"

        alice_delta = proposal.proposed_state_deltas[1]
        assert alice_delta.fields["following_count"] == 6  # was 5

        bob_delta = proposal.proposed_state_deltas[2]
        assert bob_delta.fields["follower_count"] == 21  # was 20

    async def test_follow_idempotent_error(self, pack, sample_state):
        """follow returns following=True with no deltas if already following."""
        sample_state["twitter_follows"] = [
            {
                "id": "follow-existing",
                "follower_id": "user-alice",
                "following_id": "user-bob",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        ]
        proposal = await pack.handle_action(
            ToolName("follow"),
            {"user_id": "user-alice", "target_user_id": "user-bob"},
            sample_state,
        )
        assert proposal.response_body["data"]["following"] is True
        assert proposal.proposed_state_deltas == []

    async def test_unfollow_decrements_counts(self, pack, sample_state):
        """unfollow deletes the follow and decrements both user counts."""
        sample_state["twitter_follows"] = [
            {
                "id": "follow-001",
                "follower_id": "user-alice",
                "following_id": "user-bob",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        ]
        proposal = await pack.handle_action(
            ToolName("unfollow"),
            {"user_id": "user-alice", "target_user_id": "user-bob"},
            sample_state,
        )
        assert proposal.response_body["data"]["following"] is False

        # Three deltas: follow delete, alice following_count, bob follower_count
        assert len(proposal.proposed_state_deltas) == 3
        follow_delta = proposal.proposed_state_deltas[0]
        assert follow_delta.operation == "delete"

        alice_delta = proposal.proposed_state_deltas[1]
        assert alice_delta.fields["following_count"] == 4  # was 5

        bob_delta = proposal.proposed_state_deltas[2]
        assert bob_delta.fields["follower_count"] == 19  # was 20

    async def test_get_followers_paginated(self, pack, sample_state):
        """get_followers returns paginated follower list."""
        # alice and bob both follow user-bob (need a third user for multiple followers)
        sample_state["twitter_follows"] = [
            {
                "id": "follow-a2b",
                "follower_id": "user-alice",
                "following_id": "user-bob",
                "created_at": "2026-01-01T00:00:00+00:00",
            },
        ]
        proposal = await pack.handle_action(
            ToolName("get_followers"),
            {"id": "user-bob", "max_results": 1},
            sample_state,
        )
        body = proposal.response_body
        assert body["meta"]["result_count"] == 1
        assert body["data"][0]["id"] == "user-alice"
        # With only 1 follower and max_results=1, no next page
        assert body["meta"]["next_token"] is None
        assert proposal.proposed_state_deltas == []


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    async def test_search_recent_by_hashtag(self, pack, sample_state):
        """search_recent filters tweets by #hashtag."""
        proposal = await pack.handle_action(
            ToolName("search_recent"),
            {"query": "#python"},
            sample_state,
        )
        results = proposal.response_body["data"]
        assert len(results) == 1
        assert results[0]["id"] == "tweet-aaa"
        assert proposal.proposed_state_deltas == []

    async def test_search_recent_by_text(self, pack, sample_state):
        """search_recent matches free text substring."""
        proposal = await pack.handle_action(
            ToolName("search_recent"),
            {"query": "great"},
            sample_state,
        )
        results = proposal.response_body["data"]
        assert len(results) == 1
        assert results[0]["id"] == "tweet-bbb"

    async def test_user_tweets_reverse_chronological(self, pack, sample_state):
        """user_tweets returns tweets sorted by created_at descending."""
        # Add a second published tweet by alice (newer than tweet-aaa)
        newer_tweet = {
            "id": "tweet-ccc",
            "author_id": "user-alice",
            "text": "Newer tweet",
            "tweet_type": "original",
            "reply_to_tweet_id": None,
            "retweet_of_id": None,
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
            "created_at": "2026-03-10T00:00:00+00:00",
        }
        sample_state["tweets"].append(newer_tweet)

        proposal = await pack.handle_action(
            ToolName("user_tweets"),
            {"id": "user-alice"},
            sample_state,
        )
        results = proposal.response_body["data"]
        # Should be newest first; deleted tweets excluded
        assert len(results) == 2
        assert results[0]["id"] == "tweet-ccc"
        assert results[1]["id"] == "tweet-aaa"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    async def test_unknown_action_raises_error(self, pack, sample_state):
        """Dispatching an unknown action raises PackNotFoundError."""
        with pytest.raises(PackNotFoundError):
            await pack.handle_action(
                ToolName("nonexistent_action"),
                {},
                sample_state,
            )

    async def test_delete_tweet_transitions_to_deleted(self, pack, sample_state):
        """delete_tweet transitions a published tweet to deleted status."""
        proposal = await pack.handle_action(
            ToolName("delete_tweet"),
            {"id": "tweet-aaa"},
            sample_state,
        )
        assert proposal.response_body["data"]["deleted"] is True

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "tweet"
        assert delta.operation == "update"
        assert delta.fields["status"] == "deleted"
        assert delta.previous_fields["status"] == "published"


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


class TestTimeline:
    async def test_user_tweets_returns_only_that_users_tweets(self, pack, sample_state):
        """user_tweets only returns tweets authored by the requested user."""
        proposal = await pack.handle_action(
            ToolName("user_tweets"),
            {"id": "user-bob"},
            sample_state,
        )
        results = proposal.response_body["data"]
        assert len(results) == 1
        assert results[0]["id"] == "tweet-bbb"
        assert all(t["author_id"] == "user-bob" for t in results)

    async def test_user_tweets_excludes_deleted(self, pack, sample_state):
        """user_tweets excludes tweets with status='deleted'."""
        proposal = await pack.handle_action(
            ToolName("user_tweets"),
            {"id": "user-alice"},
            sample_state,
        )
        results = proposal.response_body["data"]
        # alice has tweet-aaa (published) and tweet-del (deleted) -- only published returned
        assert len(results) == 1
        assert results[0]["id"] == "tweet-aaa"
        assert all(t["status"] == "published" for t in results)
