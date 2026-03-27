"""Tests for terrarium.packs.verified.slack -- ChatPack through pack's own handle_action."""

import pytest

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.verified.slack.pack import ChatPack
from terrarium.packs.verified.slack.schemas import (
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
                "creator": "U001",
                "is_member": True,
                "members": ["U001", "U002", "U003"],
                "topic": {
                    "value": "Company-wide announcements",
                    "creator": "U001",
                    "last_set": 1700000000,
                },
                "purpose": {
                    "value": "General discussion",
                    "creator": "U001",
                    "last_set": 1700000000,
                },
                "num_members": 50,
                "created": 1700000000,
                "unlinked": 0,
                "name_normalized": "general",
                "is_shared": False,
                "is_org_shared": False,
                "is_general": True,
            },
            {
                "id": "C002",
                "name": "engineering",
                "is_channel": True,
                "is_private": False,
                "is_archived": False,
                "creator": "U001",
                "is_member": True,
                "members": ["U001", "U002"],
                "topic": {
                    "value": "Engineering team",
                    "creator": "U001",
                    "last_set": 1700100000,
                },
                "purpose": {
                    "value": "Engineering discussions",
                    "creator": "U001",
                    "last_set": 1700100000,
                },
                "num_members": 20,
                "created": 1700100000,
                "unlinked": 0,
                "name_normalized": "engineering",
                "is_shared": False,
                "is_org_shared": False,
                "is_general": False,
            },
            {
                "id": "C003",
                "name": "archived-project",
                "is_channel": True,
                "is_private": False,
                "is_archived": True,
                "creator": "U002",
                "is_member": False,
                "members": ["U002"],
                "topic": {"value": "", "creator": "", "last_set": 0},
                "purpose": {
                    "value": "Old project",
                    "creator": "U002",
                    "last_set": 1690000000,
                },
                "num_members": 5,
                "created": 1690000000,
                "unlinked": 0,
                "name_normalized": "archived-project",
                "is_shared": False,
                "is_org_shared": False,
                "is_general": False,
            },
        ],
        "messages": [
            {
                "ts": "1700000001.000001",
                "channel": "C001",
                "user": "U001",
                "text": "Hello everyone!",
                "type": "message",
                "subtype": None,
                "thread_ts": None,
                "reply_count": 2,
                "reactions": [{"name": "wave", "users": ["U002"], "count": 1}],
                "edited": None,
                "bot_id": None,
                "app_id": None,
                "blocks": None,
            },
            {
                "ts": "1700000002.000002",
                "channel": "C001",
                "user": "U002",
                "text": "Hey there!",
                "type": "message",
                "subtype": None,
                "thread_ts": "1700000001.000001",
                "reply_count": 0,
                "reactions": [],
                "edited": None,
                "bot_id": None,
                "app_id": None,
                "blocks": None,
            },
            {
                "ts": "1700000003.000003",
                "channel": "C001",
                "user": "U003",
                "text": "Welcome!",
                "type": "message",
                "subtype": None,
                "thread_ts": "1700000001.000001",
                "reply_count": 0,
                "reactions": [],
                "edited": None,
                "bot_id": None,
                "app_id": None,
                "blocks": None,
            },
            {
                "ts": "1700000004.000004",
                "channel": "C002",
                "user": "U001",
                "text": "Deploy is done.",
                "type": "message",
                "subtype": None,
                "thread_ts": None,
                "reply_count": 0,
                "reactions": [],
                "edited": None,
                "bot_id": None,
                "app_id": None,
                "blocks": None,
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
                "is_owner": True,
                "is_primary_owner": True,
                "is_restricted": False,
                "is_ultra_restricted": False,
                "updated": 1700000000,
                "status_text": "Working",
                "status_emoji": ":laptop:",
                "tz": "America/New_York",
                "profile": {
                    "image_24": "https://example.com/alice_24.png",
                    "image_48": "https://example.com/alice_48.png",
                    "image_72": "https://example.com/alice_72.png",
                },
            },
            {
                "id": "U002",
                "name": "bob",
                "real_name": "Bob Jones",
                "display_name": "bob",
                "email": "bob@test.com",
                "is_bot": False,
                "is_admin": False,
                "is_owner": False,
                "is_primary_owner": False,
                "is_restricted": False,
                "is_ultra_restricted": False,
                "updated": 1700000000,
                "status_text": "",
                "status_emoji": "",
                "tz": "Europe/London",
                "profile": {
                    "image_24": "https://example.com/bob_24.png",
                    "image_48": "https://example.com/bob_48.png",
                    "image_72": "https://example.com/bob_72.png",
                },
            },
            {
                "id": "U003",
                "name": "buildbot",
                "real_name": "Build Bot",
                "display_name": "buildbot",
                "email": "",
                "is_bot": True,
                "is_admin": False,
                "is_owner": False,
                "is_primary_owner": False,
                "is_restricted": False,
                "is_ultra_restricted": False,
                "updated": 1700000000,
                "status_text": "",
                "status_emoji": "",
                "tz": "UTC",
                "profile": {
                    "image_24": "",
                    "image_48": "",
                    "image_72": "",
                },
            },
        ],
    }


# ---- Metadata tests ----


class TestChatPackMetadata:
    def test_metadata(self, chat_pack):
        """pack_name, category, fidelity_tier are correct."""
        assert chat_pack.pack_name == "slack"
        assert chat_pack.category == "communication"
        assert chat_pack.fidelity_tier == 1

    def test_tools_count_and_names(self, chat_pack):
        """ChatPack exposes 16 tools with expected names."""
        tools = chat_pack.get_tools()
        assert len(tools) == 16
        tool_names = {t["name"] for t in tools}
        assert tool_names == {
            "conversations.list",
            "chat.postMessage",
            "chat.update",
            "chat.delete",
            "chat.replyToThread",
            "reactions.add",
            "reactions.remove",
            "conversations.history",
            "conversations.replies",
            "users.list",
            "users.info",
            "conversations.create",
            "conversations.archive",
            "conversations.join",
            "conversations.setTopic",
            "conversations.info",
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

    def test_channel_schema_has_p1_fields(self):
        """Channel schema includes all P1 fields."""
        props = CHANNEL_ENTITY_SCHEMA["properties"]
        for field in [
            "creator",
            "is_member",
            "members",
            "unlinked",
            "name_normalized",
            "is_shared",
            "is_org_shared",
            "is_general",
        ]:
            assert field in props, f"Missing channel field: {field}"
        # topic and purpose sub-fields
        topic_props = props["topic"]["properties"]
        assert "creator" in topic_props
        assert "last_set" in topic_props
        purpose_props = props["purpose"]["properties"]
        assert "creator" in purpose_props
        assert "last_set" in purpose_props

    def test_message_schema_has_p1_fields(self):
        """Message schema includes all P1 fields."""
        props = MESSAGE_ENTITY_SCHEMA["properties"]
        for field in ["edited", "bot_id", "app_id", "subtype", "blocks"]:
            assert field in props, f"Missing message field: {field}"

    def test_user_schema_has_p1_fields(self):
        """User schema includes all P1 fields."""
        props = USER_ENTITY_SCHEMA["properties"]
        for field in [
            "is_owner",
            "is_primary_owner",
            "is_restricted",
            "is_ultra_restricted",
            "updated",
            "profile",
        ]:
            assert field in props, f"Missing user field: {field}"
        # profile sub-fields
        profile_props = props["profile"]["properties"]
        for img in ["image_24", "image_48", "image_72"]:
            assert img in profile_props


# ---- Handler tests ----


class TestSlackListChannels:
    async def test_returns_all_channels(self, chat_pack, sample_state):
        """conversations.list returns all channels within default limit."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.list"),
            {},
            sample_state,
        )
        assert isinstance(proposal, ResponseProposal)
        assert proposal.response_body["ok"] is True
        assert len(proposal.response_body["channels"]) == 3
        assert proposal.proposed_state_deltas == []

    async def test_respects_limit(self, chat_pack, sample_state):
        """conversations.list respects the limit parameter."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.list"),
            {"limit": 1},
            sample_state,
        )
        assert len(proposal.response_body["channels"]) == 1

    async def test_empty_state(self, chat_pack):
        """conversations.list returns empty list when no channels exist."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.list"),
            {},
            {},
        )
        assert proposal.response_body["channels"] == []

    async def test_cursor_pagination(self, chat_pack, sample_state):
        """conversations.list supports cursor-based pagination."""
        # First page
        p1 = await chat_pack.handle_action(
            ToolName("conversations.list"),
            {"limit": 2},
            sample_state,
        )
        assert len(p1.response_body["channels"]) == 2
        assert "response_metadata" in p1.response_body
        next_cursor = p1.response_body["response_metadata"]["next_cursor"]
        assert next_cursor != ""

        # Second page
        p2 = await chat_pack.handle_action(
            ToolName("conversations.list"),
            {"limit": 2, "cursor": next_cursor},
            sample_state,
        )
        assert len(p2.response_body["channels"]) == 1
        assert p2.response_body["response_metadata"]["next_cursor"] == ""


class TestSlackPostMessage:
    async def test_creates_message(self, chat_pack, sample_state):
        """chat.postMessage creates a message entity and returns ts."""
        proposal = await chat_pack.handle_action(
            ToolName("chat.postMessage"),
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
        assert delta.fields["edited"] is None
        assert delta.fields["subtype"] is None

    async def test_message_ts_is_entity_id(self, chat_pack, sample_state):
        """The generated ts serves as the entity_id in the delta."""
        proposal = await chat_pack.handle_action(
            ToolName("chat.postMessage"),
            {"channel_id": "C001", "text": "test"},
            sample_state,
        )
        ts = proposal.response_body["ts"]
        delta = proposal.proposed_state_deltas[0]
        assert str(delta.entity_id) == ts


class TestSlackUpdateMessage:
    async def test_updates_message_text(self, chat_pack, sample_state):
        """chat.update updates the text and sets edited metadata."""
        proposal = await chat_pack.handle_action(
            ToolName("chat.update"),
            {
                "channel_id": "C001",
                "ts": "1700000001.000001",
                "text": "Hello everyone! (edited)",
                "user_id": "U001",
            },
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        assert proposal.response_body["channel"] == "C001"
        assert proposal.response_body["ts"] == "1700000001.000001"
        assert proposal.response_body["text"] == "Hello everyone! (edited)"

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.operation == "update"
        assert delta.entity_id == "1700000001.000001"
        assert delta.fields["text"] == "Hello everyone! (edited)"
        assert delta.fields["edited"]["user"] == "U001"
        assert "ts" in delta.fields["edited"]
        assert delta.previous_fields["text"] == "Hello everyone!"
        assert delta.previous_fields["edited"] is None

    async def test_update_nonexistent_message(self, chat_pack, sample_state):
        """Updating a nonexistent message returns an error."""
        proposal = await chat_pack.handle_action(
            ToolName("chat.update"),
            {
                "channel_id": "C001",
                "ts": "9999999999.000000",
                "text": "does not exist",
            },
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "message_not_found"
        assert proposal.proposed_state_deltas == []


class TestSlackDeleteMessage:
    async def test_deletes_message(self, chat_pack, sample_state):
        """chat.delete deletes the target message."""
        proposal = await chat_pack.handle_action(
            ToolName("chat.delete"),
            {
                "channel_id": "C002",
                "ts": "1700000004.000004",
            },
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        assert proposal.response_body["channel"] == "C002"
        assert proposal.response_body["ts"] == "1700000004.000004"

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.operation == "delete"
        assert delta.entity_id == "1700000004.000004"
        assert delta.previous_fields is not None
        assert delta.previous_fields["text"] == "Deploy is done."

    async def test_delete_nonexistent_message(self, chat_pack, sample_state):
        """Deleting a nonexistent message returns an error."""
        proposal = await chat_pack.handle_action(
            ToolName("chat.delete"),
            {
                "channel_id": "C001",
                "ts": "9999999999.000000",
            },
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "message_not_found"
        assert proposal.proposed_state_deltas == []


class TestSlackReplyToThread:
    async def test_creates_reply_and_updates_parent(self, chat_pack, sample_state):
        """chat.replyToThread creates a reply and bumps parent reply_count."""
        proposal = await chat_pack.handle_action(
            ToolName("chat.replyToThread"),
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
        assert create_delta.fields["edited"] is None

        update_delta = proposal.proposed_state_deltas[1]
        assert update_delta.operation == "update"
        assert update_delta.entity_id == "1700000001.000001"
        assert update_delta.fields["reply_count"] == 3  # was 2, now 3
        assert update_delta.previous_fields["reply_count"] == 2

    async def test_reply_to_nonexistent_thread(self, chat_pack):
        """Reply to a thread that doesn't exist still creates the reply message."""
        proposal = await chat_pack.handle_action(
            ToolName("chat.replyToThread"),
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
        """reactions.add adds a new emoji reaction to a message."""
        proposal = await chat_pack.handle_action(
            ToolName("reactions.add"),
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
            ToolName("reactions.add"),
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
            ToolName("reactions.add"),
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
            ToolName("reactions.add"),
            {
                "channel_id": "C001",
                "timestamp": "9999999999.000000",
                "reaction": "x",
            },
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "message_not_found"


class TestSlackRemoveReaction:
    async def test_removes_reaction(self, chat_pack, sample_state):
        """reactions.remove removes a user's reaction from a message."""
        proposal = await chat_pack.handle_action(
            ToolName("reactions.remove"),
            {
                "channel_id": "C001",
                "timestamp": "1700000001.000001",
                "reaction": "wave",
                "user_id": "U002",
            },
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.operation == "update"
        # wave reaction should be completely removed (was the only user)
        reaction_names = [r["name"] for r in delta.fields["reactions"]]
        assert "wave" not in reaction_names

    async def test_removes_user_from_multi_user_reaction(self, chat_pack):
        """Removing one user from a multi-user reaction keeps the reaction."""
        state = {
            "messages": [
                {
                    "ts": "100.001",
                    "channel": "C001",
                    "user": "U001",
                    "text": "hi",
                    "type": "message",
                    "reactions": [{"name": "thumbsup", "users": ["U001", "U002"], "count": 2}],
                },
            ],
        }
        proposal = await chat_pack.handle_action(
            ToolName("reactions.remove"),
            {
                "channel_id": "C001",
                "timestamp": "100.001",
                "reaction": "thumbsup",
                "user_id": "U001",
            },
            state,
        )
        assert proposal.response_body["ok"] is True
        delta = proposal.proposed_state_deltas[0]
        thumbsup = next(r for r in delta.fields["reactions"] if r["name"] == "thumbsup")
        assert thumbsup["count"] == 1
        assert thumbsup["users"] == ["U002"]

    async def test_remove_nonexistent_reaction(self, chat_pack, sample_state):
        """Removing a reaction that doesn't exist returns error."""
        proposal = await chat_pack.handle_action(
            ToolName("reactions.remove"),
            {
                "channel_id": "C001",
                "timestamp": "1700000001.000001",
                "reaction": "nonexistent",
                "user_id": "U001",
            },
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "no_reaction"

    async def test_remove_reaction_user_not_in_list(self, chat_pack, sample_state):
        """Removing a reaction the user didn't add returns error."""
        proposal = await chat_pack.handle_action(
            ToolName("reactions.remove"),
            {
                "channel_id": "C001",
                "timestamp": "1700000001.000001",
                "reaction": "wave",
                "user_id": "U999",
            },
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "no_reaction"

    async def test_remove_reaction_message_not_found(self, chat_pack, sample_state):
        """Removing a reaction from a nonexistent message returns error."""
        proposal = await chat_pack.handle_action(
            ToolName("reactions.remove"),
            {
                "channel_id": "C001",
                "timestamp": "9999999999.000000",
                "reaction": "wave",
                "user_id": "U002",
            },
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "message_not_found"


class TestSlackGetChannelHistory:
    async def test_returns_channel_messages(self, chat_pack, sample_state):
        """conversations.history returns messages for the given channel."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.history"),
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
            ToolName("conversations.history"),
            {"channel_id": "C001"},
            sample_state,
        )
        msgs = proposal.response_body["messages"]
        timestamps = [m["ts"] for m in msgs]
        assert timestamps == sorted(timestamps, reverse=True)

    async def test_respects_limit(self, chat_pack, sample_state):
        """limit parameter caps the number of returned messages."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.history"),
            {"channel_id": "C001", "limit": 1},
            sample_state,
        )
        assert len(proposal.response_body["messages"]) == 1

    async def test_has_more_flag(self, chat_pack, sample_state):
        """has_more is true when there are more messages beyond the limit."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.history"),
            {"channel_id": "C001", "limit": 2},
            sample_state,
        )
        assert proposal.response_body["has_more"] is True
        assert proposal.response_body["response_metadata"]["next_cursor"] != ""

    async def test_cursor_pagination(self, chat_pack, sample_state):
        """Channel history supports cursor-based pagination."""
        p1 = await chat_pack.handle_action(
            ToolName("conversations.history"),
            {"channel_id": "C001", "limit": 2},
            sample_state,
        )
        assert len(p1.response_body["messages"]) == 2
        next_cursor = p1.response_body["response_metadata"]["next_cursor"]

        p2 = await chat_pack.handle_action(
            ToolName("conversations.history"),
            {"channel_id": "C001", "limit": 2, "cursor": next_cursor},
            sample_state,
        )
        assert len(p2.response_body["messages"]) == 1
        assert p2.response_body["has_more"] is False


class TestSlackGetThreadReplies:
    async def test_returns_thread_messages(self, chat_pack, sample_state):
        """conversations.replies returns parent + replies for a thread."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.replies"),
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
            ToolName("conversations.replies"),
            {"channel_id": "C001", "thread_ts": "1700000001.000001"},
            sample_state,
        )
        msgs = proposal.response_body["messages"]
        timestamps = [m["ts"] for m in msgs]
        assert timestamps == sorted(timestamps)


class TestSlackGetUsers:
    async def test_returns_all_users(self, chat_pack, sample_state):
        """users.list returns all users within default limit."""
        proposal = await chat_pack.handle_action(
            ToolName("users.list"),
            {},
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        assert len(proposal.response_body["members"]) == 3
        assert proposal.proposed_state_deltas == []

    async def test_respects_limit(self, chat_pack, sample_state):
        """users.list respects the limit parameter."""
        proposal = await chat_pack.handle_action(
            ToolName("users.list"),
            {"limit": 2},
            sample_state,
        )
        assert len(proposal.response_body["members"]) == 2

    async def test_cursor_pagination(self, chat_pack, sample_state):
        """users.list supports cursor-based pagination."""
        p1 = await chat_pack.handle_action(
            ToolName("users.list"),
            {"limit": 2},
            sample_state,
        )
        assert len(p1.response_body["members"]) == 2
        next_cursor = p1.response_body["response_metadata"]["next_cursor"]
        assert next_cursor != ""

        p2 = await chat_pack.handle_action(
            ToolName("users.list"),
            {"limit": 2, "cursor": next_cursor},
            sample_state,
        )
        assert len(p2.response_body["members"]) == 1
        assert p2.response_body["response_metadata"]["next_cursor"] == ""


class TestSlackGetUserProfile:
    async def test_returns_user(self, chat_pack, sample_state):
        """users.info returns the matching user."""
        proposal = await chat_pack.handle_action(
            ToolName("users.info"),
            {"user_id": "U001"},
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        assert proposal.response_body["user"]["name"] == "alice"
        assert proposal.proposed_state_deltas == []

    async def test_user_not_found(self, chat_pack, sample_state):
        """users.info returns error for unknown user_id."""
        proposal = await chat_pack.handle_action(
            ToolName("users.info"),
            {"user_id": "UNOTEXIST"},
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "user_not_found"


class TestSlackCreateChannel:
    async def test_creates_channel(self, chat_pack, sample_state):
        """conversations.create creates a new channel entity."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.create"),
            {"name": "new-channel", "user_id": "U001"},
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        channel = proposal.response_body["channel"]
        assert channel["name"] == "new-channel"
        assert channel["is_channel"] is True
        assert channel["is_private"] is False
        assert channel["is_archived"] is False
        assert channel["creator"] == "U001"
        assert channel["members"] == ["U001"]
        assert channel["num_members"] == 1
        assert channel["is_member"] is True
        assert channel["name_normalized"] == "new-channel"

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "channel"
        assert delta.operation == "create"
        assert delta.fields["name"] == "new-channel"

    async def test_creates_private_channel(self, chat_pack, sample_state):
        """conversations.create can create a private channel."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.create"),
            {"name": "secret", "is_private": True, "user_id": "U001"},
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        assert proposal.response_body["channel"]["is_private"] is True

    async def test_duplicate_name_error(self, chat_pack, sample_state):
        """Creating a channel with an existing name returns an error."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.create"),
            {"name": "general", "user_id": "U001"},
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "name_taken"
        assert proposal.proposed_state_deltas == []


class TestSlackArchiveChannel:
    async def test_archives_channel(self, chat_pack, sample_state):
        """conversations.archive sets is_archived to True."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.archive"),
            {"channel_id": "C001"},
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.operation == "update"
        assert delta.entity_id == "C001"
        assert delta.fields["is_archived"] is True
        assert delta.previous_fields["is_archived"] is False

    async def test_archive_nonexistent_channel(self, chat_pack, sample_state):
        """Archiving a nonexistent channel returns error."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.archive"),
            {"channel_id": "C999"},
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "channel_not_found"

    async def test_archive_already_archived(self, chat_pack, sample_state):
        """Archiving an already-archived channel returns error."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.archive"),
            {"channel_id": "C003"},
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "already_archived"


class TestSlackJoinChannel:
    async def test_joins_channel(self, chat_pack, sample_state):
        """conversations.join adds user to members and increments num_members."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.join"),
            {"channel_id": "C002", "user_id": "U003"},
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        channel = proposal.response_body["channel"]
        assert "U003" in channel["members"]
        assert channel["num_members"] == 21
        assert channel["is_member"] is True

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.operation == "update"
        assert "U003" in delta.fields["members"]
        assert delta.fields["num_members"] == 21

    async def test_join_already_member(self, chat_pack, sample_state):
        """Joining a channel the user is already in returns success with no deltas."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.join"),
            {"channel_id": "C001", "user_id": "U001"},
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        assert proposal.proposed_state_deltas == []

    async def test_join_nonexistent_channel(self, chat_pack, sample_state):
        """Joining a nonexistent channel returns error."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.join"),
            {"channel_id": "C999", "user_id": "U001"},
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "channel_not_found"

    async def test_join_archived_channel(self, chat_pack, sample_state):
        """Joining an archived channel returns error."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.join"),
            {"channel_id": "C003", "user_id": "U001"},
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "is_archived"


class TestSlackSetChannelTopic:
    async def test_sets_topic(self, chat_pack, sample_state):
        """conversations.setTopic updates the topic on a channel."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.setTopic"),
            {
                "channel_id": "C001",
                "topic": "New topic value",
                "user_id": "U002",
            },
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        topic = proposal.response_body["topic"]
        assert topic["value"] == "New topic value"
        assert topic["creator"] == "U002"
        assert isinstance(topic["last_set"], int)
        assert topic["last_set"] > 0

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.operation == "update"
        assert delta.entity_id == "C001"
        assert delta.fields["topic"]["value"] == "New topic value"
        assert delta.previous_fields["topic"]["value"] == "Company-wide announcements"

    async def test_set_topic_nonexistent_channel(self, chat_pack, sample_state):
        """Setting topic on a nonexistent channel returns error."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.setTopic"),
            {"channel_id": "C999", "topic": "whatever"},
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "channel_not_found"

    async def test_set_topic_archived_channel(self, chat_pack, sample_state):
        """Setting topic on an archived channel returns error."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.setTopic"),
            {"channel_id": "C003", "topic": "whatever"},
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "is_archived"


class TestSlackGetChannelInfo:
    async def test_returns_channel(self, chat_pack, sample_state):
        """conversations.info returns the matching channel."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.info"),
            {"channel_id": "C001"},
            sample_state,
        )
        assert proposal.response_body["ok"] is True
        assert proposal.response_body["channel"]["id"] == "C001"
        assert proposal.response_body["channel"]["name"] == "general"
        assert proposal.proposed_state_deltas == []

    async def test_channel_not_found(self, chat_pack, sample_state):
        """Getting info for nonexistent channel returns error."""
        proposal = await chat_pack.handle_action(
            ToolName("conversations.info"),
            {"channel_id": "C999"},
            sample_state,
        )
        assert proposal.response_body["ok"] is False
        assert proposal.response_body["error"] == "channel_not_found"


class TestResponseFormatConsistency:
    """P2: Verify all responses follow Slack's ok/error format."""

    async def test_all_success_responses_have_ok_true(self, chat_pack, sample_state):
        """All successful tool calls return ok: true."""
        success_calls = [
            ("conversations.list", {}),
            ("conversations.history", {"channel_id": "C001"}),
            ("conversations.replies", {"channel_id": "C001", "thread_ts": "1700000001.000001"}),
            ("users.list", {}),
            ("users.info", {"user_id": "U001"}),
            ("chat.postMessage", {"channel_id": "C001", "text": "hi"}),
            ("conversations.info", {"channel_id": "C001"}),
        ]
        for tool_name, params in success_calls:
            proposal = await chat_pack.handle_action(ToolName(tool_name), params, sample_state)
            assert proposal.response_body["ok"] is True, f"{tool_name} did not return ok: true"

    async def test_all_error_responses_have_ok_false_and_error(self, chat_pack, sample_state):
        """All error responses return ok: false and an error string."""
        error_calls = [
            ("reactions.add", {"channel_id": "C001", "timestamp": "xxx", "reaction": "x"}),
            ("reactions.remove", {"channel_id": "C001", "timestamp": "xxx", "reaction": "x"}),
            ("users.info", {"user_id": "NOTEXIST"}),
            ("chat.update", {"channel_id": "C001", "ts": "xxx", "text": "t"}),
            ("chat.delete", {"channel_id": "C001", "ts": "xxx"}),
            ("conversations.archive", {"channel_id": "C999"}),
            ("conversations.join", {"channel_id": "C999"}),
            ("conversations.setTopic", {"channel_id": "C999", "topic": "t"}),
            ("conversations.info", {"channel_id": "C999"}),
        ]
        for tool_name, params in error_calls:
            proposal = await chat_pack.handle_action(ToolName(tool_name), params, sample_state)
            assert proposal.response_body["ok"] is False, f"{tool_name} did not return ok: false"
            assert "error" in proposal.response_body, f"{tool_name} missing 'error' key in response"
            assert isinstance(proposal.response_body["error"], str), (
                f"{tool_name} error is not a string"
            )

    async def test_pagination_responses_have_response_metadata(self, chat_pack, sample_state):
        """Paginated endpoints include response_metadata with next_cursor."""
        paginated_calls = [
            ("conversations.list", {"limit": 1}),
            ("conversations.history", {"channel_id": "C001", "limit": 1}),
            ("users.list", {"limit": 1}),
        ]
        for tool_name, params in paginated_calls:
            proposal = await chat_pack.handle_action(ToolName(tool_name), params, sample_state)
            body = proposal.response_body
            assert "response_metadata" in body, f"{tool_name} missing response_metadata"
            assert "next_cursor" in body["response_metadata"], (
                f"{tool_name} missing next_cursor in response_metadata"
            )
