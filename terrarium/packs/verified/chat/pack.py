"""Chat service pack (Tier 1 -- verified).

Provides the canonical tool surface for chat-category services:
list channels, post/update/delete messages, reply to threads,
add/remove reactions, retrieve channel history and thread replies,
list users, get user profiles, create/archive/join channels,
set channel topics, and get channel info.  Tool names and paths
follow the official Slack MCP server conventions.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.base import ActionHandler, ServicePack
from terrarium.packs.verified.chat.handlers import (
    handle_slack_add_reaction,
    handle_slack_archive_channel,
    handle_slack_create_channel,
    handle_slack_delete_message,
    handle_slack_get_channel_history,
    handle_slack_get_channel_info,
    handle_slack_get_thread_replies,
    handle_slack_get_user_profile,
    handle_slack_get_users,
    handle_slack_join_channel,
    handle_slack_list_channels,
    handle_slack_post_message,
    handle_slack_remove_reaction,
    handle_slack_reply_to_thread,
    handle_slack_set_channel_topic,
    handle_slack_update_message,
)
from terrarium.packs.verified.chat.schemas import (
    CHANNEL_ENTITY_SCHEMA,
    CHAT_TOOL_DEFINITIONS,
    MESSAGE_ENTITY_SCHEMA,
    USER_ENTITY_SCHEMA,
)
from terrarium.packs.verified.chat.state_machines import (
    CHANNEL_TRANSITIONS,
    MESSAGE_TRANSITIONS,
)


class ChatPack(ServicePack):
    """Verified pack for chat communication services.

    Tools: slack_list_channels, slack_post_message, slack_update_message,
    slack_delete_message, slack_reply_to_thread, slack_add_reaction,
    slack_remove_reaction, slack_get_channel_history, slack_get_thread_replies,
    slack_get_users, slack_get_user_profile, slack_create_channel,
    slack_archive_channel, slack_join_channel, slack_set_channel_topic,
    slack_get_channel_info.
    """

    pack_name: ClassVar[str] = "chat"
    category: ClassVar[str] = "communication"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "slack_list_channels": handle_slack_list_channels,
        "slack_post_message": handle_slack_post_message,
        "slack_update_message": handle_slack_update_message,
        "slack_delete_message": handle_slack_delete_message,
        "slack_reply_to_thread": handle_slack_reply_to_thread,
        "slack_add_reaction": handle_slack_add_reaction,
        "slack_remove_reaction": handle_slack_remove_reaction,
        "slack_get_channel_history": handle_slack_get_channel_history,
        "slack_get_thread_replies": handle_slack_get_thread_replies,
        "slack_get_users": handle_slack_get_users,
        "slack_get_user_profile": handle_slack_get_user_profile,
        "slack_create_channel": handle_slack_create_channel,
        "slack_archive_channel": handle_slack_archive_channel,
        "slack_join_channel": handle_slack_join_channel,
        "slack_set_channel_topic": handle_slack_set_channel_topic,
        "slack_get_channel_info": handle_slack_get_channel_info,
    }

    def get_tools(self) -> list[dict]:
        """Return the chat tool manifest."""
        return list(CHAT_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (channel, message, user)."""
        return {
            "channel": CHANNEL_ENTITY_SCHEMA,
            "message": MESSAGE_ENTITY_SCHEMA,
            "user": USER_ENTITY_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        """Return state machines for chat entities."""
        return {
            "channel": {"transitions": CHANNEL_TRANSITIONS},
            "message": {"transitions": MESSAGE_TRANSITIONS},
        }

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate chat action handler."""
        return await self.dispatch_action(action, input_data, state)
