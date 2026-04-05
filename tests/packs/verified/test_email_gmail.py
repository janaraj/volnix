"""Tests for Gmail-aligned handlers in volnix.packs.verified.gmail."""

import pytest

from volnix.core.context import ResponseProposal
from volnix.core.types import ToolName
from volnix.packs.verified.gmail.pack import EmailPack


@pytest.fixture
def email_pack():
    return EmailPack()


@pytest.fixture
def gmail_state():
    """State with pre-existing Gmail-style messages, threads, and labels."""
    return {
        "messages": [
            {
                "id": "msg_001",
                "threadId": "thread_001",
                "labelIds": ["INBOX", "UNREAD"],
                "snippet": "Hey, how are you?",
                "subject": "Hello Bob",
                "body": "Hey, how are you?",
                "from_addr": "alice@test.com",
                "to_addr": "bob@test.com",
                "internalDate": "2026-01-01T00:00:00+00:00",
                "sizeEstimate": 18,
            },
            {
                "id": "msg_002",
                "threadId": "thread_002",
                "labelIds": ["INBOX"],
                "snippet": "Can we meet at 10am?",
                "subject": "Meeting tomorrow",
                "body": "Can we meet at 10am?",
                "from_addr": "carol@test.com",
                "to_addr": "bob@test.com",
                "internalDate": "2026-01-02T00:00:00+00:00",
                "sizeEstimate": 20,
            },
            {
                "id": "msg_003",
                "threadId": "thread_003",
                "labelIds": ["SENT"],
                "snippet": "Please find the report",
                "subject": "Report attached",
                "body": "Please find the report attached.",
                "from_addr": "bob@test.com",
                "to_addr": "dave@test.com",
                "internalDate": "2026-01-03T00:00:00+00:00",
                "sizeEstimate": 31,
            },
        ],
        "labels": [
            {
                "id": "INBOX", "name": "INBOX", "type": "system",
                "messagesTotal": 2, "messagesUnread": 1,
            },
            {
                "id": "SENT", "name": "SENT", "type": "system",
                "messagesTotal": 1, "messagesUnread": 0,
            },
            {
                "id": "TRASH", "name": "TRASH", "type": "system",
                "messagesTotal": 0, "messagesUnread": 0,
            },
            {
                "id": "label_custom", "name": "Important", "type": "user",
                "messagesTotal": 0, "messagesUnread": 0,
            },
        ],
    }


class TestSendGmailMessage:
    async def test_creates_message_and_thread(self, email_pack, gmail_state):
        """users.messages.send creates both message and thread entities."""
        proposal = await email_pack.handle_action(
            ToolName("users.messages.send"),
            {
                "to": "bob@test.com",
                "from": "alice@test.com",
                "subject": "New message",
                "body": "Hello from Gmail!",
            },
            gmail_state,
        )
        assert isinstance(proposal, ResponseProposal)
        body = proposal.response_body
        assert "id" in body
        assert "threadId" in body
        assert body["labelIds"] == ["SENT"]

        # Two deltas: message create + thread create
        assert len(proposal.proposed_state_deltas) == 2
        msg_delta = proposal.proposed_state_deltas[0]
        assert msg_delta.entity_type == "gmail_message"
        assert msg_delta.operation == "create"
        assert msg_delta.fields["labelIds"] == ["SENT"]
        assert msg_delta.fields["subject"] == "New message"
        assert msg_delta.fields["from_addr"] == "alice@test.com"
        assert msg_delta.fields["to_addr"] == "bob@test.com"
        assert msg_delta.fields["sizeEstimate"] == len("Hello from Gmail!")

        thread_delta = proposal.proposed_state_deltas[1]
        assert thread_delta.entity_type == "gmail_thread"
        assert thread_delta.operation == "create"
        assert body["threadId"] == str(thread_delta.entity_id)


class TestSearchGmailMessages:
    async def test_search_by_query(self, email_pack, gmail_state):
        """users.messages.list filters by query substring."""
        proposal = await email_pack.handle_action(
            ToolName("users.messages.list"),
            {"q": "report"},
            gmail_state,
        )
        body = proposal.response_body
        assert body["resultSizeEstimate"] == 1
        assert body["messages"][0]["id"] == "msg_003"

    async def test_search_by_label(self, email_pack, gmail_state):
        """users.messages.list filters by labelIds."""
        proposal = await email_pack.handle_action(
            ToolName("users.messages.list"),
            {"labelIds": ["SENT"]},
            gmail_state,
        )
        body = proposal.response_body
        assert body["resultSizeEstimate"] == 1
        assert body["messages"][0]["id"] == "msg_003"

    async def test_search_with_max_results(self, email_pack, gmail_state):
        """users.messages.list paginates via maxResults."""
        proposal = await email_pack.handle_action(
            ToolName("users.messages.list"),
            {"maxResults": 1},
            gmail_state,
        )
        assert len(proposal.response_body["messages"]) == 1
        assert proposal.response_body["resultSizeEstimate"] == 1

    async def test_search_no_filters_returns_all(self, email_pack, gmail_state):
        """users.messages.list with no filters returns all messages."""
        proposal = await email_pack.handle_action(
            ToolName("users.messages.list"),
            {},
            gmail_state,
        )
        assert proposal.response_body["resultSizeEstimate"] == 3

    async def test_search_returns_id_and_thread_id(self, email_pack, gmail_state):
        """users.messages.list results include id and threadId."""
        proposal = await email_pack.handle_action(
            ToolName("users.messages.list"),
            {"q": "Hello"},
            gmail_state,
        )
        for msg in proposal.response_body["messages"]:
            assert "id" in msg
            assert "threadId" in msg


class TestGetGmailMessage:
    async def test_returns_full_message(self, email_pack, gmail_state):
        """users.messages.get returns the complete message object."""
        proposal = await email_pack.handle_action(
            ToolName("users.messages.get"),
            {"id": "msg_001"},
            gmail_state,
        )
        body = proposal.response_body
        assert body["id"] == "msg_001"
        assert body["subject"] == "Hello Bob"
        assert body["from_addr"] == "alice@test.com"
        assert body["labelIds"] == ["INBOX", "UNREAD"]
        assert proposal.proposed_state_deltas == []

    async def test_message_not_found(self, email_pack, gmail_state):
        """users.messages.get returns error for unknown ID."""
        proposal = await email_pack.handle_action(
            ToolName("users.messages.get"),
            {"id": "msg_nonexistent"},
            gmail_state,
        )
        assert "error" in proposal.response_body


class TestModifyGmailMessage:
    async def test_add_and_remove_labels(self, email_pack, gmail_state):
        """users.messages.modify applies addLabelIds and removeLabelIds."""
        proposal = await email_pack.handle_action(
            ToolName("users.messages.modify"),
            {
                "id": "msg_001",
                "addLabelIds": ["STARRED"],
                "removeLabelIds": ["UNREAD"],
            },
            gmail_state,
        )
        body = proposal.response_body
        assert "STARRED" in body["labelIds"]
        assert "UNREAD" not in body["labelIds"]
        assert "INBOX" in body["labelIds"]  # untouched

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.operation == "update"
        assert delta.entity_type == "gmail_message"

    async def test_modify_not_found(self, email_pack, gmail_state):
        """users.messages.modify returns error for unknown message."""
        proposal = await email_pack.handle_action(
            ToolName("users.messages.modify"),
            {"id": "msg_nonexistent", "addLabelIds": ["STARRED"]},
            gmail_state,
        )
        assert "error" in proposal.response_body


class TestTrashGmailMessage:
    async def test_moves_to_trash(self, email_pack, gmail_state):
        """users.messages.trash adds TRASH and removes INBOX."""
        proposal = await email_pack.handle_action(
            ToolName("users.messages.trash"),
            {"id": "msg_001"},
            gmail_state,
        )
        body = proposal.response_body
        assert "TRASH" in body["labelIds"]
        assert "INBOX" not in body["labelIds"]

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.operation == "update"
        assert "INBOX" in delta.previous_fields["labelIds"]

    async def test_trash_not_found(self, email_pack, gmail_state):
        """users.messages.trash returns error for unknown message."""
        proposal = await email_pack.handle_action(
            ToolName("users.messages.trash"),
            {"id": "msg_nonexistent"},
            gmail_state,
        )
        assert "error" in proposal.response_body


class TestDeleteGmailMessage:
    async def test_permanently_deletes(self, email_pack, gmail_state):
        """users.messages.delete produces a delete delta."""
        proposal = await email_pack.handle_action(
            ToolName("users.messages.delete"),
            {"id": "msg_002"},
            gmail_state,
        )
        assert proposal.response_body["deleted"] is True
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.operation == "delete"
        assert delta.entity_type == "gmail_message"
        assert str(delta.entity_id) == "msg_002"

    async def test_delete_not_found(self, email_pack, gmail_state):
        """users.messages.delete returns error for unknown message."""
        proposal = await email_pack.handle_action(
            ToolName("users.messages.delete"),
            {"id": "msg_nonexistent"},
            gmail_state,
        )
        assert "error" in proposal.response_body


class TestCreateGmailDraft:
    async def test_creates_draft(self, email_pack, gmail_state):
        """users.drafts.create produces a draft entity create delta."""
        proposal = await email_pack.handle_action(
            ToolName("users.drafts.create"),
            {
                "to": "dave@test.com",
                "subject": "Draft subject",
                "body": "Draft body text",
            },
            gmail_state,
        )
        body = proposal.response_body
        assert "id" in body
        assert "message" in body
        assert body["message"]["to"] == "dave@test.com"
        assert body["message"]["subject"] == "Draft subject"
        assert body["message"]["body"] == "Draft body text"

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "gmail_draft"
        assert delta.operation == "create"


class TestListGmailLabels:
    async def test_returns_labels(self, email_pack, gmail_state):
        """users.labels.list returns all labels from state."""
        proposal = await email_pack.handle_action(
            ToolName("users.labels.list"),
            {},
            gmail_state,
        )
        labels = proposal.response_body["labels"]
        assert len(labels) == 4
        label_ids = {lbl["id"] for lbl in labels}
        assert "INBOX" in label_ids
        assert "SENT" in label_ids
        assert "TRASH" in label_ids
        assert "label_custom" in label_ids
        assert proposal.proposed_state_deltas == []

    async def test_empty_labels(self, email_pack):
        """users.labels.list returns empty list when no labels in state."""
        proposal = await email_pack.handle_action(
            ToolName("users.labels.list"),
            {},
            {},
        )
        assert proposal.response_body["labels"] == []


class TestLegacyHandlersStillWork:
    """Verify that legacy email_* handlers remain accessible via handle_action."""

    async def test_legacy_send(self, email_pack):
        """email_send still works through the pack."""
        proposal = await email_pack.handle_action(
            ToolName("email_send"),
            {
                "from_addr": "a@b.com",
                "to_addr": "c@d.com",
                "subject": "Legacy",
                "body": "Still works",
            },
            {},
        )
        assert proposal.response_body["status"] == "sent"
        assert "email_id" in proposal.response_body

    async def test_legacy_list(self, email_pack):
        """email_list still works through the pack."""
        proposal = await email_pack.handle_action(
            ToolName("email_list"),
            {"mailbox_owner": "nobody@test.com"},
            {"emails": []},
        )
        assert proposal.response_body["count"] == 0
