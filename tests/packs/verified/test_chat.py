"""Tests for terrarium.packs.verified.chat -- ChatPack through pack's own handle_action."""

import pytest

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.verified.chat.pack import ChatPack
from terrarium.packs.verified.chat.schemas import (
    CHANNEL_ENTITY_SCHEMA,
    MESSAGE_ENTITY_SCHEMA,
    USER_ENTITY_SCHEMA,
)


@pytest.fixture
def chat_pack():
    return ChatPack()


@pytest.fixture
def sample_state():
    """State with pre-existing channels, messages, and users."""
    return {
        "channels": [
            {
                "id": "C001",
                "name": "general",
                "is_channel": True,
                "is_private": False,
                "is_archived": False,
                "topic": {"value": "Company-wide announcements"},
                "purpose": {"value": "General discussion"},
                "num_members": 50,
                "created": 1700000000,
            },
            {
                "id": "C002",
                "name": "engineering",
                "is_channel": True,
                "is_private": False,
                "is_archived": False,
                "topic": {"value": "Engineering team"},
                "purpose": {"value": "Engineering discussions"},
                "num_members": 20,
                "created": 1700100000,
            },
            {
                "id": "C003",
                "name": "archived-project",
                "is_channel": True,
                "is_private": False,
                "is_archived": True,
                "topic": {"value": ""},
                "purpose": {"value": "Old project"},
                "num_members": 5,
                "created": 1690000000,
            },
        ],
        "messages": [
            {
                "ts": "1700000001.000001",
                "channel": "C001",
                "user": "U001",
                "text": "Hello everyone!",
                "type": "message",
                "thread_ts": None,
                "reply_count": 2,
                "reactions": [{"name": "wave", "users": ["U002"], "count": 1}],
            },
            {
                "ts": "1700000002.000002",
                "channel": "C001",
                "user": "U002",
                "text": "Hey there!",
                "type": "message",
                "thread_ts": "1700000001.000001",
                "reply_count": 0,
                "reactions": [],
            },
            {
                "ts": "1700000003.000003",
                "channel": "C001",
                "user": "U003",
                "text": "Welcome!",
                "type": "message",
                "thread_ts": "1700000001.000001",
                "reply_count": 0,
                "reactions": [],
            },
            {
                "ts": "1700000004.000004",
                "channel": "C002",
                "user": "U001",
                "text": "Deploy is done.",
                "type": "message",
                "thread_ts": None,
                "reply_count": 0,
                "reactions": [],
            },
        ],
        "users": [
            {
                "id": "U001",
                "name": "alice",
                "real_name": "Alice Smith",
                "display_name": "alice",
                "email": "alice@test.com",
                "is_bot": False,
                "is_admin": True,
                "status_text": "Working",
                "status_emoji": ":laptop:",
                "tz": "America/New_York",
            },
            {
                "id": "U002",
                "name": "bob",
                "real_name": "Bob Jones",
                "display_name": "bob",
                "email": "bob@test.com",
                "is_bot": False,
                "is_admin": False,
                "status_text": "",
                "status_emoji": "",
                "tz": "Europe/London",
            },
            {
                "id": "U003",
                "name": "buildbot",
                "real_name": "Build Bot",
                "display_name": "buildbot",
                "email": "",
                "is_bot": True,
                "is_admin": False,
                "status_text": "",
                "status_emoji": "",
                "tz": "UTC",
            },
        ],
    }


# ---- Metadata tests ----


class TestChatPackMetadata:
    def test_metadata(self, chat_pack):
        """pack_name, category, fidelity_tier are correct."""
        assert chat_pack.pack_name == "chat"
        assert chat_pack.category == "communication"
        assert chat_pack.fidelity_tier == 1

    def test_tools_count_and_names(self, chat_pack):
        """ChatPack exposes 8 tools with expected names."""
        tools = chat_pack.get_tools()
        assert len(tools) == 8
        tool_names = {t["name"] for t in tools}
        assert tool_names == {
            "slack_list_channels",
            "slack_post_message",
            "slack_reply_to_thread",
            "slack_add_reaction",
            "slack_get_channel_history",
            "slack_get_thread_replies",
            "slack_get_users",
            "slack_get_user_profile",
        }

    def test_entity_schemas(self, chat_pack):
        """channel, message, and user entity schemas are present."""
        schemas = chat_pack.get_entity_schemas()
        assert "channel" in schemas
        assert "message" in schemas
        assert "user" in schemas

    def test_state_machines_empty(self, chat_pack):
        """State machines exist but have empty transitions."""
        sms = chat_pack.get_state_machines()
        assert "channel" in sms
        assert "message" in sms
        assert sms["channel"]["transitions"] == {}
        assert sms["message"]["transitions"] == {}

    def test_channel_schema_identity(self):
        """Channel identity field is 'id'."""
        assert CHANNEL_ENTITY_SCHEMA["x-terrarium-identity"] == "id"

    def test_message_schema_identity(self):
        """Message identity field is 'ts'."""
        assert MESSAGE_ENTITY_SCHEMA["x-terrarium-identity"] == "ts"

    def test_user_schema_identity(self):
        """User identity field is 'id'."""
        assert USER_ENTITY_SCHEMA["x-terrarium-identity"] == "id"


# ---- Handler tests ----


class TestSlackListChannels:
    async def test_returns_all_channels(self, chat_pack, sample_state):
        """slack_list_channels returns all channels within default limit."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_list_channels"),
            {},
            sample_state,
        )
        assert isinstance(proposal, ResponseProposal)
        assert proposal.response_body["ok"] is True
        assert len(proposal.response_body["channels"]) == 3
        assert proposal.proposed_state_deltas == []

    async def test_respects_limit(self, chat_pack, sample_state):
        """slack_list_channels respects the limit parameter."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_list_channels"),
            {"limit": 1},
            sample_state,
        )
        assert len(proposal.response_body["channels"]) == 1

    async def test_empty_state(self, chat_pack):
        """slack_list_channels returns empty list when no channels exist."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_list_channels"),
            {},
            {},
        )
        assert proposal.response_body["channels"] == []


class TestSlackPostMessage:
    async def test_creates_message(self, chat_pack, sample_state):
        """slack_post_message creates a message entity and returns ts."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_post_message"),
            {"channel_id": "C001", "text": "New message"},
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        assert proposal.response_body["channel"] == "C001"
        assert "ts" in proposal.response_body
        assert len(proposal.proposed_state_deltas) == 1

        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "message"
        assert delta.operation == "create"
        assert delta.fields["text"] == "New message"
        assert delta.fields["channel"] == "C001"
        assert delta.fields["reply_count"] == 0
        assert delta.fields["reactions"] == []

    async def test_message_ts_is_entity_id(self, chat_pack, sample_state):
        """The generated ts serves as the entity_id in the delta."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_post_message"),
            {"channel_id": "C001", "text": "test"},
            sample_state,
        )
        ts = proposal.response_body["ts"]
        delta = proposal.proposed_state_deltas[0]
        assert str(delta.entity_id) == ts


class TestSlackReplyToThread:
    async def test_creates_reply_and_updates_parent(self, chat_pack, sample_state):
        """slack_reply_to_thread creates a reply and bumps parent reply_count."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_reply_to_thread"),
            {
                "channel_id": "C001",
                "thread_ts": "1700000001.000001",
                "text": "Thread reply",
            },
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        assert proposal.response_body["message"]["thread_ts"] == "1700000001.000001"

        # Should have TWO deltas: create reply + update parent
        assert len(proposal.proposed_state_deltas) == 2

        create_delta = proposal.proposed_state_deltas[0]
        assert create_delta.operation == "create"
        assert create_delta.fields["thread_ts"] == "1700000001.000001"

        update_delta = proposal.proposed_state_deltas[1]
        assert update_delta.operation == "update"
        assert update_delta.entity_id == "1700000001.000001"
        assert update_delta.fields["reply_count"] == 3  # was 2, now 3
        assert update_delta.previous_fields["reply_count"] == 2

    async def test_reply_to_nonexistent_thread(self, chat_pack):
        """Reply to a thread that doesn't exist still creates the reply message."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_reply_to_thread"),
            {
                "channel_id": "C001",
                "thread_ts": "9999999999.000000",
                "text": "orphaned reply",
            },
            {"messages": []},
        )
        assert proposal.response_body["ok"] is True
        # Only one delta (create reply); no parent to update
        assert len(proposal.proposed_state_deltas) == 1
        assert proposal.proposed_state_deltas[0].operation == "create"


class TestSlackAddReaction:
    async def test_adds_new_reaction(self, chat_pack, sample_state):
        """slack_add_reaction adds a new emoji reaction to a message."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_add_reaction"),
            {
                "channel_id": "C001",
                "timestamp": "1700000001.000001",
                "reaction": "thumbsup",
                "user_id": "U001",
            },
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.operation == "update"
        # Should have original 'wave' plus new 'thumbsup'
        reactions = delta.fields["reactions"]
        reaction_names = [r["name"] for r in reactions]
        assert "wave" in reaction_names
        assert "thumbsup" in reaction_names

    async def test_adds_user_to_existing_reaction(self, chat_pack, sample_state):
        """Adding same emoji from different user increments count."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_add_reaction"),
            {
                "channel_id": "C001",
                "timestamp": "1700000001.000001",
                "reaction": "wave",
                "user_id": "U003",
            },
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        delta = proposal.proposed_state_deltas[0]
        wave_reaction = next(r for r in delta.fields["reactions"] if r["name"] == "wave")
        assert wave_reaction["count"] == 2
        assert "U002" in wave_reaction["users"]
        assert "U003" in wave_reaction["users"]

    async def test_already_reacted_error(self, chat_pack, sample_state):
        """Adding same reaction from same user returns error."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_add_reaction"),
            {
                "channel_id": "C001",
                "timestamp": "1700000001.000001",
                "reaction": "wave",
                "user_id": "U002",
            },
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "already_reacted"
        assert proposal.proposed_state_deltas == []

    async def test_message_not_found(self, chat_pack, sample_state):
        """Reacting to nonexistent message returns error."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_add_reaction"),
            {
                "channel_id": "C001",
                "timestamp": "9999999999.000000",
                "reaction": "x",
            },
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "message_not_found"


class TestSlackGetChannelHistory:
    async def test_returns_channel_messages(self, chat_pack, sample_state):
        """slack_get_channel_history returns messages for the given channel."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_get_channel_history"),
            {"channel_id": "C001"},
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        msgs = proposal.response_body["messages"]
        # C001 has 3 messages in sample_state
        assert len(msgs) == 3
        assert proposal.proposed_state_deltas == []

    async def test_sorted_descending(self, chat_pack, sample_state):
        """Messages are returned sorted by ts descending (newest first)."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_get_channel_history"),
            {"channel_id": "C001"},
            sample_state,
        )
        msgs = proposal.response_body["messages"]
        timestamps = [m["ts"] for m in msgs]
        assert timestamps == sorted(timestamps, reverse=True)

    async def test_respects_limit(self, chat_pack, sample_state):
        """limit parameter caps the number of returned messages."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_get_channel_history"),
            {"channel_id": "C001", "limit": 1},
            sample_state,
        )
        assert len(proposal.response_body["messages"]) == 1


class TestSlackGetThreadReplies:
    async def test_returns_thread_messages(self, chat_pack, sample_state):
        """slack_get_thread_replies returns parent + replies for a thread."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_get_thread_replies"),
            {"channel_id": "C001", "thread_ts": "1700000001.000001"},
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        msgs = proposal.response_body["messages"]
        # Parent + 2 replies = 3 messages
        assert len(msgs) == 3
        assert proposal.proposed_state_deltas == []

    async def test_sorted_ascending(self, chat_pack, sample_state):
        """Thread replies are sorted by ts ascending (oldest first)."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_get_thread_replies"),
            {"channel_id": "C001", "thread_ts": "1700000001.000001"},
            sample_state,
        )
        msgs = proposal.response_body["messages"]
        timestamps = [m["ts"] for m in msgs]
        assert timestamps == sorted(timestamps)


class TestSlackGetUsers:
    async def test_returns_all_users(self, chat_pack, sample_state):
        """slack_get_users returns all users within default limit."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_get_users"),
            {},
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        assert len(proposal.response_body["members"]) == 3
        assert proposal.proposed_state_deltas == []

    async def test_respects_limit(self, chat_pack, sample_state):
        """slack_get_users respects the limit parameter."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_get_users"),
            {"limit": 2},
            sample_state,
        )
        assert len(proposal.response_body["members"]) == 2


class TestSlackGetUserProfile:
    async def test_returns_user(self, chat_pack, sample_state):
        """slack_get_user_profile returns the matching user."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_get_user_profile"),
            {"user_id": "U001"},
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        assert proposal.response_body["user"]["name"] == "alice"
        assert proposal.proposed_state_deltas == []

    async def test_user_not_found(self, chat_pack, sample_state):
        """slack_get_user_profile returns error for unknown user_id."""
        proposal = await chat_pack.handle_action(
            ToolName("slack_get_user_profile"),
            {"user_id": "UNOTEXIST"},
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "user_not_found"
