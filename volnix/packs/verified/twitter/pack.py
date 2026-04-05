"""Twitter/X service pack (Tier 1 -- verified).

Provides the canonical tool surface for Twitter/X social media services:
create, get, delete, search tweets; reply, retweet, unretweet, quote tweet;
like, unlike; follow, unfollow; get followers, following; get user profile;
get user tweets.
"""

from __future__ import annotations

from typing import ClassVar

from volnix.core.context import ResponseProposal
from volnix.core.types import ToolName
from volnix.packs.base import ActionHandler, ServicePack
from volnix.packs.verified.twitter.handlers import (
    handle_create_tweet,
    handle_delete_tweet,
    handle_follow,
    handle_get_followers,
    handle_get_following,
    handle_get_tweet,
    handle_get_user,
    handle_like,
    handle_quote_tweet,
    handle_reply,
    handle_retweet,
    handle_search_recent,
    handle_unfollow,
    handle_unlike,
    handle_unretweet,
    handle_user_tweets,
)
from volnix.packs.verified.twitter.schemas import (
    TWEET_ENTITY_SCHEMA,
    TWITTER_FOLLOW_ENTITY_SCHEMA,
    TWITTER_LIKE_ENTITY_SCHEMA,
    TWITTER_TOOL_DEFINITIONS,
    TWITTER_USER_ENTITY_SCHEMA,
)
from volnix.packs.verified.twitter.state_machines import (
    TWEET_TRANSITIONS,
    TWITTER_USER_TRANSITIONS,
)


class TwitterPack(ServicePack):
    """Verified pack for Twitter/X social media services.

    Tools: create_tweet, get_tweet, delete_tweet,
    search_recent, reply, retweet, unretweet,
    quote_tweet, like, unlike, follow,
    unfollow, get_followers, get_following,
    get_user, user_tweets.
    """

    pack_name: ClassVar[str] = "twitter"
    category: ClassVar[str] = "social_media"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "create_tweet": handle_create_tweet,
        "get_tweet": handle_get_tweet,
        "delete_tweet": handle_delete_tweet,
        "search_recent": handle_search_recent,
        "reply": handle_reply,
        "retweet": handle_retweet,
        "unretweet": handle_unretweet,
        "quote_tweet": handle_quote_tweet,
        "like": handle_like,
        "unlike": handle_unlike,
        "follow": handle_follow,
        "unfollow": handle_unfollow,
        "get_followers": handle_get_followers,
        "get_following": handle_get_following,
        "get_user": handle_get_user,
        "user_tweets": handle_user_tweets,
    }

    def get_tools(self) -> list[dict]:
        """Return the Twitter tool manifest."""
        return list(TWITTER_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (tweet, user, follow, like)."""
        return {
            "tweet": TWEET_ENTITY_SCHEMA,
            "user": TWITTER_USER_ENTITY_SCHEMA,
            "follow": TWITTER_FOLLOW_ENTITY_SCHEMA,
            "like": TWITTER_LIKE_ENTITY_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        """Return state machines for tweet and user entities."""
        return {
            "tweet": {"transitions": TWEET_TRANSITIONS},
            "user": {"transitions": TWITTER_USER_TRANSITIONS},
        }

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate Twitter action handler."""
        return await self.dispatch_action(action, input_data, state)
