"""Tests for the ``npc_chat`` Tier-1 pack.

Covers the handler-level contract:
* ``send_message`` commits an ``npc_message`` entity.
* ``send_message`` with ``feature_mention`` emits a
  ``WordOfMouthEvent`` in ``proposed_events``.
* ``send_message`` without ``feature_mention`` emits nothing (plain
  chit-chat shouldn't activate the recipient NPC).
* ``read_messages`` returns the recipient's inbox newest-first and
  respects ``limit``.
* The pack declares both ``npc_message`` and ``npc_state`` entity
  schemas (Phase 3.2).
"""

from __future__ import annotations

from typing import Any

import pytest

from volnix.core.events import WordOfMouthEvent
from volnix.core.types import ToolName
from volnix.packs.verified.npc_chat.pack import NPCChatPack

# -- fixtures ----------------------------------------------------------------


@pytest.fixture
def pack() -> NPCChatPack:
    return NPCChatPack()


@pytest.fixture
def empty_state() -> dict[str, Any]:
    return {"entities": {}, "tick": 5}


# -- pack metadata -----------------------------------------------------------


class TestPackMetadata:
    def test_declares_npc_chat_as_communication_tier_1(self, pack: NPCChatPack) -> None:
        assert pack.pack_name == "npc_chat"
        assert pack.category == "communication"
        assert pack.fidelity_tier == 1

    def test_exposes_send_and_read_tools_only(self, pack: NPCChatPack) -> None:
        names = {t["name"] for t in pack.get_tools()}
        assert names == {"npc_chat.send_message", "npc_chat.read_messages"}

    def test_declares_npc_message_and_npc_state_schemas(self, pack: NPCChatPack) -> None:
        schemas = pack.get_entity_schemas()
        assert "npc_message" in schemas
        assert "npc_state" in schemas
        # Sanity-check the Volnix extensions that other packs rely on.
        assert schemas["npc_message"].get("x-volnix-identity") == "id"
        assert schemas["npc_state"].get("x-volnix-identity") == "id"


# -- send_message ------------------------------------------------------------


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_commits_npc_message_entity(
        self, pack: NPCChatPack, empty_state: dict[str, Any]
    ) -> None:
        prop = await pack.handle_action(
            ToolName("npc_chat.send_message"),
            {
                "sender_id": "npc-1",
                "recipient_id": "npc-2",
                "content": "hey",
            },
            empty_state,
        )
        assert prop.response_body["ok"] is True
        assert prop.response_body["delivered"] is True
        assert len(prop.proposed_state_deltas) == 1
        delta = prop.proposed_state_deltas[0]
        assert delta.entity_type == "npc_message"
        assert delta.operation == "create"
        assert delta.fields["sender_id"] == "npc-1"
        assert delta.fields["recipient_id"] == "npc-2"
        assert delta.fields["content"] == "hey"

    @pytest.mark.asyncio
    async def test_feature_mention_emits_word_of_mouth_event(
        self, pack: NPCChatPack, empty_state: dict[str, Any]
    ) -> None:
        prop = await pack.handle_action(
            ToolName("npc_chat.send_message"),
            {
                "sender_id": "npc-1",
                "recipient_id": "npc-2",
                "content": "you have to try this",
                "feature_mention": "drop_flare",
                "sentiment": "positive",
            },
            empty_state,
        )
        assert len(prop.proposed_events) == 1
        event = prop.proposed_events[0]
        assert isinstance(event, WordOfMouthEvent)
        assert event.event_type == "npc.word_of_mouth"
        assert event.sender_id == "npc-1"
        assert event.recipient_id == "npc-2"
        assert event.feature_id == "drop_flare"
        assert event.sentiment == "positive"
        # intended_for on the WorldEvent's input_data drives activation
        # via AgencyEngine.notify's intended_for check — the E2E test
        # asserts the downstream effect.
        assert event.input_data.get("intended_for") == ["npc-2"]

    @pytest.mark.asyncio
    async def test_no_feature_mention_emits_no_events(
        self, pack: NPCChatPack, empty_state: dict[str, Any]
    ) -> None:
        """Plain chit-chat must not wake the recipient NPC.

        Only feature mentions are product signals; if every message
        activated the recipient, NPC-to-NPC spam would drown out the
        PMF signal.
        """
        prop = await pack.handle_action(
            ToolName("npc_chat.send_message"),
            {
                "sender_id": "npc-1",
                "recipient_id": "npc-2",
                "content": "random small talk",
            },
            empty_state,
        )
        assert prop.proposed_events == []

    @pytest.mark.asyncio
    async def test_sent_at_reads_tick_from_state(self, pack: NPCChatPack) -> None:
        prop = await pack.handle_action(
            ToolName("npc_chat.send_message"),
            {"sender_id": "a", "recipient_id": "b", "content": "x"},
            {"tick": 42, "entities": {}},
        )
        assert prop.proposed_state_deltas[0].fields["sent_at"] == 42


# -- read_messages -----------------------------------------------------------


class TestReadMessages:
    @pytest.mark.asyncio
    async def test_returns_recipient_inbox_newest_first(self, pack: NPCChatPack) -> None:
        state = {
            "entities": {
                "npc_message": [
                    {"id": "m1", "recipient_id": "npc-2", "content": "old", "sent_at": 1},
                    {"id": "m2", "recipient_id": "npc-2", "content": "new", "sent_at": 5},
                    {"id": "m3", "recipient_id": "npc-3", "content": "other", "sent_at": 4},
                ]
            }
        }
        prop = await pack.handle_action(
            ToolName("npc_chat.read_messages"),
            {"recipient_id": "npc-2"},
            state,
        )
        assert prop.response_body["count"] == 2
        ids = [m["id"] for m in prop.response_body["messages"]]
        assert ids == ["m2", "m1"]  # newest first

    @pytest.mark.asyncio
    async def test_limit_respected(self, pack: NPCChatPack) -> None:
        state = {
            "entities": {
                "npc_message": [
                    {"id": f"m{i}", "recipient_id": "npc-1", "sent_at": i} for i in range(10)
                ]
            }
        }
        prop = await pack.handle_action(
            ToolName("npc_chat.read_messages"),
            {"recipient_id": "npc-1", "limit": 3},
            state,
        )
        assert prop.response_body["count"] == 3

    @pytest.mark.asyncio
    async def test_empty_inbox(self, pack: NPCChatPack) -> None:
        prop = await pack.handle_action(
            ToolName("npc_chat.read_messages"),
            {"recipient_id": "npc-1"},
            {"entities": {}},
        )
        assert prop.response_body["count"] == 0
        assert prop.response_body["messages"] == []

    @pytest.mark.asyncio
    async def test_read_is_read_only(self, pack: NPCChatPack, empty_state: dict[str, Any]) -> None:
        prop = await pack.handle_action(
            ToolName("npc_chat.read_messages"),
            {"recipient_id": "npc-1"},
            empty_state,
        )
        assert prop.proposed_state_deltas == []
        assert prop.proposed_events == []
