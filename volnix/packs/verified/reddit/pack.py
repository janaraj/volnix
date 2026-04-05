"""Reddit service pack (Tier 1 -- verified).

Provides the canonical tool surface for Reddit-style social media services:
subreddit management, post submission, commenting, voting, user profiles,
and feed listings.
"""

from __future__ import annotations

from typing import ClassVar

from volnix.core.context import ResponseProposal
from volnix.core.types import ToolName
from volnix.packs.base import ActionHandler, ServicePack
from volnix.packs.verified.reddit.handlers import (
    handle_best,
    handle_comment,
    handle_popular,
    handle_post_comments,
    handle_post_detail,
    handle_remove,
    handle_search,
    handle_submit,
    handle_subreddit_about,
    handle_subreddit_hot,
    handle_subreddit_new,
    handle_subreddit_top,
    handle_subreddits_search,
    handle_subscribe,
    handle_unsubscribe,
    handle_user_about,
    handle_user_submitted,
    handle_vote,
)
from volnix.packs.verified.reddit.schemas import (
    REDDIT_COMMENT_ENTITY_SCHEMA,
    REDDIT_POST_ENTITY_SCHEMA,
    REDDIT_TOOL_DEFINITIONS,
    REDDIT_USER_ENTITY_SCHEMA,
    REDDIT_VOTE_ENTITY_SCHEMA,
    SUBREDDIT_ENTITY_SCHEMA,
)
from volnix.packs.verified.reddit.state_machines import (
    REDDIT_COMMENT_TRANSITIONS,
    REDDIT_POST_TRANSITIONS,
    REDDIT_USER_TRANSITIONS,
    SUBREDDIT_TRANSITIONS,
)


class RedditPack(ServicePack):
    """Verified pack for Reddit-style social media services.

    Tools: subreddits_search, subreddit_about, subscribe,
    unsubscribe, submit, post_detail, subreddit_hot,
    subreddit_new, subreddit_top, search, remove,
    comment, post_comments, vote, user_about,
    user_submitted, best, popular.
    """

    pack_name: ClassVar[str] = "reddit"
    category: ClassVar[str] = "social_media"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "subreddits_search": handle_subreddits_search,
        "subreddit_about": handle_subreddit_about,
        "subscribe": handle_subscribe,
        "unsubscribe": handle_unsubscribe,
        "submit": handle_submit,
        "post_detail": handle_post_detail,
        "subreddit_hot": handle_subreddit_hot,
        "subreddit_new": handle_subreddit_new,
        "subreddit_top": handle_subreddit_top,
        "search": handle_search,
        "remove": handle_remove,
        "comment": handle_comment,
        "post_comments": handle_post_comments,
        "vote": handle_vote,
        "user_about": handle_user_about,
        "user_submitted": handle_user_submitted,
        "best": handle_best,
        "popular": handle_popular,
    }

    def get_tools(self) -> list[dict]:
        """Return the Reddit tool manifest."""
        return list(REDDIT_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (subreddit, post, comment, user, vote)."""
        return {
            "subreddit": SUBREDDIT_ENTITY_SCHEMA,
            "reddit_post": REDDIT_POST_ENTITY_SCHEMA,
            "comment": REDDIT_COMMENT_ENTITY_SCHEMA,
            "reddit_user": REDDIT_USER_ENTITY_SCHEMA,
            "vote": REDDIT_VOTE_ENTITY_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        """Return state machines for Reddit entities."""
        return {
            "reddit_post": {"transitions": REDDIT_POST_TRANSITIONS},
            "comment": {"transitions": REDDIT_COMMENT_TRANSITIONS},
            "reddit_user": {"transitions": REDDIT_USER_TRANSITIONS},
            "subreddit": {"transitions": SUBREDDIT_TRANSITIONS},
        }

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate Reddit action handler."""
        return await self.dispatch_action(action, input_data, state)
