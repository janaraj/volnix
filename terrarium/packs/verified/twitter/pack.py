"""Twitter/X service pack (Tier 1 -- verified).

Provides the canonical tool surface for Twitter/X social media services:
create, get, delete, search tweets; reply, retweet, unretweet, quote tweet;
like, unlike; follow, unfollow; get followers, following; get user profile;
get user tweets.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.base import ActionHandler, ServicePack
from terrarium.packs.verified.twitter.handlers import (
    handle_twitter_create_tweet,
    handle_twitter_delete_tweet,
    handle_twitter_follow,
    handle_twitter_get_followers,
    handle_twitter_get_following,
    handle_twitter_get_tweet,
    handle_twitter_get_user,
    handle_twitter_like,
    handle_twitter_quote_tweet,
    handle_twitter_reply,
    handle_twitter_retweet,
    handle_twitter_search_recent,
    handle_twitter_unfollow,
    handle_twitter_unlike,
    handle_twitter_unretweet,
    handle_twitter_user_tweets,
)
from terrarium.packs.verified.twitter.schemas import (
    TWEET_ENTITY_SCHEMA,
    TWITTER_FOLLOW_ENTITY_SCHEMA,
    TWITTER_LIKE_ENTITY_SCHEMA,
    TWITTER_TOOL_DEFINITIONS,
    TWITTER_USER_ENTITY_SCHEMA,
)
from terrarium.packs.verified.twitter.state_machines import (
    TWEET_TRANSITIONS,
    TWITTER_USER_TRANSITIONS,
)


class TwitterPack(ServicePack):
    """Verified pack for Twitter/X social media services.

    Tools: twitter_create_tweet, twitter_get_tweet, twitter_delete_tweet,
    twitter_search_recent, twitter_reply, twitter_retweet, twitter_unretweet,
    twitter_quote_tweet, twitter_like, twitter_unlike, twitter_follow,
    twitter_unfollow, twitter_get_followers, twitter_get_following,
    twitter_get_user, twitter_user_tweets.
    """

    pack_name: ClassVar[str] = "twitter"
    category: ClassVar[str] = "social_media"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "twitter_create_tweet": handle_twitter_create_tweet,
        "twitter_get_tweet": handle_twitter_get_tweet,
        "twitter_delete_tweet": handle_twitter_delete_tweet,
        "twitter_search_recent": handle_twitter_search_recent,
        "twitter_reply": handle_twitter_reply,
        "twitter_retweet": handle_twitter_retweet,
        "twitter_unretweet": handle_twitter_unretweet,
        "twitter_quote_tweet": handle_twitter_quote_tweet,
        "twitter_like": handle_twitter_like,
        "twitter_unlike": handle_twitter_unlike,
        "twitter_follow": handle_twitter_follow,
        "twitter_unfollow": handle_twitter_unfollow,
        "twitter_get_followers": handle_twitter_get_followers,
        "twitter_get_following": handle_twitter_get_following,
        "twitter_get_user": handle_twitter_get_user,
        "twitter_user_tweets": handle_twitter_user_tweets,
    }

    def get_tools(self) -> list[dict]:
        """Return the Twitter tool manifest."""
        return list(TWITTER_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (tweet, twitter_user, twitter_follow, twitter_like)."""
        return {
            "tweet": TWEET_ENTITY_SCHEMA,
            "twitter_user": TWITTER_USER_ENTITY_SCHEMA,
            "twitter_follow": TWITTER_FOLLOW_ENTITY_SCHEMA,
            "twitter_like": TWITTER_LIKE_ENTITY_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        """Return state machines for tweet and twitter_user entities."""
        return {
            "tweet": {"transitions": TWEET_TRANSITIONS},
            "twitter_user": {"transitions": TWITTER_USER_TRANSITIONS},
        }

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate Twitter action handler."""
        return await self.dispatch_action(action, input_data, state)
