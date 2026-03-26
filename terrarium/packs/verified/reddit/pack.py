"""Reddit service pack (Tier 1 -- verified).

Provides the canonical tool surface for Reddit-style social media services:
subreddit management, post submission, commenting, voting, user profiles,
and feed listings.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.base import ActionHandler, ServicePack
from terrarium.packs.verified.reddit.handlers import (
    handle_reddit_best,
    handle_reddit_comment,
    handle_reddit_popular,
    handle_reddit_post_comments,
    handle_reddit_post_detail,
    handle_reddit_remove,
    handle_reddit_search,
    handle_reddit_submit,
    handle_reddit_subreddit_about,
    handle_reddit_subreddit_hot,
    handle_reddit_subreddit_new,
    handle_reddit_subreddit_top,
    handle_reddit_subreddits_search,
    handle_reddit_subscribe,
    handle_reddit_unsubscribe,
    handle_reddit_user_about,
    handle_reddit_user_submitted,
    handle_reddit_vote,
)
from terrarium.packs.verified.reddit.schemas import (
    REDDIT_COMMENT_ENTITY_SCHEMA,
    REDDIT_POST_ENTITY_SCHEMA,
    REDDIT_TOOL_DEFINITIONS,
    REDDIT_USER_ENTITY_SCHEMA,
    REDDIT_VOTE_ENTITY_SCHEMA,
    SUBREDDIT_ENTITY_SCHEMA,
)
from terrarium.packs.verified.reddit.state_machines import (
    REDDIT_COMMENT_TRANSITIONS,
    REDDIT_POST_TRANSITIONS,
    REDDIT_USER_TRANSITIONS,
    SUBREDDIT_TRANSITIONS,
)


class RedditPack(ServicePack):
    """Verified pack for Reddit-style social media services.

    Tools: reddit_subreddits_search, reddit_subreddit_about, reddit_subscribe,
    reddit_unsubscribe, reddit_submit, reddit_post_detail, reddit_subreddit_hot,
    reddit_subreddit_new, reddit_subreddit_top, reddit_search, reddit_remove,
    reddit_comment, reddit_post_comments, reddit_vote, reddit_user_about,
    reddit_user_submitted, reddit_best, reddit_popular.
    """

    pack_name: ClassVar[str] = "reddit"
    category: ClassVar[str] = "social_media"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "reddit_subreddits_search": handle_reddit_subreddits_search,
        "reddit_subreddit_about": handle_reddit_subreddit_about,
        "reddit_subscribe": handle_reddit_subscribe,
        "reddit_unsubscribe": handle_reddit_unsubscribe,
        "reddit_submit": handle_reddit_submit,
        "reddit_post_detail": handle_reddit_post_detail,
        "reddit_subreddit_hot": handle_reddit_subreddit_hot,
        "reddit_subreddit_new": handle_reddit_subreddit_new,
        "reddit_subreddit_top": handle_reddit_subreddit_top,
        "reddit_search": handle_reddit_search,
        "reddit_remove": handle_reddit_remove,
        "reddit_comment": handle_reddit_comment,
        "reddit_post_comments": handle_reddit_post_comments,
        "reddit_vote": handle_reddit_vote,
        "reddit_user_about": handle_reddit_user_about,
        "reddit_user_submitted": handle_reddit_user_submitted,
        "reddit_best": handle_reddit_best,
        "reddit_popular": handle_reddit_popular,
    }

    def get_tools(self) -> list[dict]:
        """Return the Reddit tool manifest."""
        return list(REDDIT_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (subreddit, post, comment, user, vote)."""
        return {
            "subreddit": SUBREDDIT_ENTITY_SCHEMA,
            "reddit_post": REDDIT_POST_ENTITY_SCHEMA,
            "reddit_comment": REDDIT_COMMENT_ENTITY_SCHEMA,
            "reddit_user": REDDIT_USER_ENTITY_SCHEMA,
            "reddit_vote": REDDIT_VOTE_ENTITY_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        """Return state machines for Reddit entities."""
        return {
            "reddit_post": {"transitions": REDDIT_POST_TRANSITIONS},
            "reddit_comment": {"transitions": REDDIT_COMMENT_TRANSITIONS},
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
