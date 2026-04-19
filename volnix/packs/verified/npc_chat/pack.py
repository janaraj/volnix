"""NPC chat service pack (Tier 1 — verified, deterministic).

Provides NPC-to-NPC messaging with a narrow tool surface:

* ``npc_chat.send_message`` — one-way message to another NPC; emits a
  ``WordOfMouthEvent`` when ``feature_mention`` is set.
* ``npc_chat.read_messages`` — read the inbox addressed to an NPC.

Deliberately separate from ``verified/slack`` even though both are
``communication`` category: the slack pack models a shared-channel
workplace idiom (posting to ``C001`` where multiple agents listen),
whereas NPC chat is peer-to-peer. Collapsing them would mean slack's
entity shape has to carry NPC-specific fields like ``feature_mention``,
which is the wrong direction for a service meant to simulate workplace
communication.

Also owns the ``npc_state`` entity schema so the State Engine has a
registered shape to persist per-NPC state against. No tool writes to
``npc_state`` yet — that's Phase 4+ work. Declaring the schema now
lets future callers query the entity type without a pack change.
"""

from __future__ import annotations

from typing import ClassVar

from volnix.core.context import ResponseProposal
from volnix.core.types import ToolName
from volnix.packs.base import ActionHandler, ServicePack
from volnix.packs.verified.npc_chat.handlers import (
    handle_read_messages,
    handle_send_message,
)
from volnix.packs.verified.npc_chat.schemas import (
    NPC_CHAT_TOOL_DEFINITIONS,
    NPC_MESSAGE_ENTITY_SCHEMA,
    NPC_STATE_ENTITY_SCHEMA,
)


class NPCChatPack(ServicePack):
    """Deterministic Tier-1 pack for NPC-to-NPC messaging."""

    pack_name: ClassVar[str] = "npc_chat"
    category: ClassVar[str] = "communication"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "npc_chat.send_message": handle_send_message,
        "npc_chat.read_messages": handle_read_messages,
    }

    def get_tools(self) -> list[dict]:
        return list(NPC_CHAT_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        return {
            "npc_message": NPC_MESSAGE_ENTITY_SCHEMA,
            "npc_state": NPC_STATE_ENTITY_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        # Messages are immutable once committed; npc_state is free-form
        # per activation profile. No enum-constrained status fields.
        return {}

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        return await self.dispatch_action(action, input_data, state)
