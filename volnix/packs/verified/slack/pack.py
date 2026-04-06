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

from volnix.core.context import ResponseProposal
from volnix.core.types import ToolName
from volnix.packs.base import ActionHandler, ServicePack
from volnix.packs.verified.slack.handlers import (
    handle_reactions_add,
    handle_conversations_archive,
    handle_conversations_create,
    handle_chat_delete,
    handle_conversations_history,
    handle_conversations_info,
    handle_conversations_replies,
    handle_users_profile_get,
    handle_users_list,
    handle_conversations_join,
    handle_channels_list,
    handle_chat_postMessage,
    handle_reactions_remove,
    handle_chat_replyToThread,
    handle_conversations_setTopic,
    handle_chat_update,
)
from volnix.packs.verified.slack.schemas import (
    CHANNEL_ENTITY_SCHEMA,
    CHAT_TOOL_DEFINITIONS,
    MESSAGE_ENTITY_SCHEMA,
    USER_ENTITY_SCHEMA,
)
from volnix.packs.verified.slack.state_machines import (
    CHANNEL_TRANSITIONS,
    MESSAGE_TRANSITIONS,
)


class ChatPack(ServicePack):
    """Verified pack for chat communication services.

    Tools: conversations.list, chat.postMessage, chat.update,
    chat.delete, chat.replyToThread, reactions.add,
    reactions.remove, conversations.history, conversations.replies,
    users.list, users.info, conversations.create,
    conversations.archive, conversations.join, conversations.setTopic,
    conversations.info.
    """

    pack_name: ClassVar[str] = "slack"
    category: ClassVar[str] = "communication"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "conversations.list": handle_channels_list,
        "chat.postMessage": handle_chat_postMessage,
        "chat.update": handle_chat_update,
        "chat.delete": handle_chat_delete,
        "chat.replyToThread": handle_chat_replyToThread,
        "reactions.add": handle_reactions_add,
        "reactions.remove": handle_reactions_remove,
        "conversations.history": handle_conversations_history,
        "conversations.replies": handle_conversations_replies,
        "users.list": handle_users_list,
        "users.info": handle_users_profile_get,
        "conversations.create": handle_conversations_create,
        "conversations.archive": handle_conversations_archive,
        "conversations.join": handle_conversations_join,
        "conversations.setTopic": handle_conversations_setTopic,
        "conversations.info": handle_conversations_info,
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
