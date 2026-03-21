"""Chat service pack (Tier 1 -- verified).

Provides the canonical tool surface for chat-category services:
send message, list channels, list messages, and create channel.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.base import ServicePack


class ChatPack(ServicePack):
    """Verified pack for chat communication services.

    Tools: chat_send_message, chat_list_channels, chat_list_messages,
    chat_create_channel.
    """

    pack_name: ClassVar[str] = "chat"
    category: ClassVar[str] = "communication"
    fidelity_tier: ClassVar[int] = 1

    def get_tools(self) -> list[dict]:
        """Return the chat tool manifest."""
        ...

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (channel, message, thread)."""
        ...

    def get_state_machines(self) -> dict:
        """Return state machines for chat entities."""
        ...

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate chat action handler."""
        ...
