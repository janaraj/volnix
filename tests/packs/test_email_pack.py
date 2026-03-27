"""Tests for terrarium.packs.verified.gmail — EmailPack through pack's own handle_action."""

import pytest

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.verified.gmail.pack import EmailPack
from terrarium.validation.schema import SchemaValidator
from terrarium.validation.state_machine import StateMachineValidator


@pytest.fixture
def email_pack():
    return EmailPack()


@pytest.fixture
def sample_state():
    """State with pre-existing emails for list/read/reply/search tests."""
    return {
        "emails": [
            {
                "email_id": "email-aaa111",
                "from_addr": "alice@test.com",
                "to_addr": "bob@test.com",
                "subject": "Hello Bob",
                "body": "How are you?",
                "status": "delivered",
                "thread_id": "thread-t001",
                "timestamp": "2026-01-01T00:00:00+00:00",
            },
            {
                "email_id": "email-bbb222",
                "from_addr": "carol@test.com",
                "to_addr": "bob@test.com",
                "subject": "Meeting tomorrow",
                "body": "Can we meet at 10am?",
                "status": "read",
                "thread_id": "thread-t002",
                "timestamp": "2026-01-02T00:00:00+00:00",
            },
            {
                "email_id": "email-ccc333",
                "from_addr": "dave@test.com",
                "to_addr": "alice@test.com",
                "subject": "Report attached",
                "body": "Please find the report attached.",
                "status": "delivered",
                "thread_id": "thread-t003",
                "timestamp": "2026-01-03T00:00:00+00:00",
            },
        ],
    }


class TestEmailPackMetadata:
    def test_metadata(self, email_pack):
        """pack_name, category, fidelity_tier are correct."""
        assert email_pack.pack_name == "gmail"
        assert email_pack.category == "communication"
        assert email_pack.fidelity_tier == 1

    def test_tools_count_and_names(self, email_pack):
        """EmailPack exposes 14 tools (8 Gmail + 6 legacy)."""
        tools = email_pack.get_tools()
        assert len(tools) == 14
        tool_names = {t["name"] for t in tools}
        # Gmail-aligned
        assert tool_names >= {
            "messages_search",
            "messages_get",
            "messages_send",
            "drafts_create",
            "messages_modify",
            "messages_trash",
            "messages_delete",
            "labels_list",
        }
        # Legacy (backward compat)
        assert tool_names >= {
            "email_send",
            "email_list",
            "email_read",
            "email_search",
            "email_reply",
            "email_mark_read",
        }

    def test_entity_schemas(self, email_pack):
        """Gmail-aligned and legacy entity schemas are present."""
        schemas = email_pack.get_entity_schemas()
        # Gmail-aligned (namespaced to avoid collision with chat pack)
        assert "gmail_message" in schemas
        assert "gmail_thread" in schemas
        assert "gmail_label" in schemas
        assert "gmail_draft" in schemas
        # Legacy (backward compat)
        assert "email" in schemas
        assert "mailbox" in schemas

    def test_state_machines(self, email_pack):
        """Email state machine transitions are present."""
        sms = email_pack.get_state_machines()
        assert "email" in sms
        assert "transitions" in sms["email"]
        transitions = sms["email"]["transitions"]
        assert "delivered" in transitions
        assert "read" in transitions["delivered"]


class TestEmailPackActions:
    @pytest.mark.asyncio
    async def test_send(self, email_pack):
        """email_send creates entity with status='delivered'."""
        proposal = await email_pack.handle_action(
            ToolName("email_send"),
            {
                "from_addr": "alice@test.com",
                "to_addr": "bob@test.com",
                "subject": "Test",
                "body": "Hello!",
            },
            {},
        )
        assert isinstance(proposal, ResponseProposal)
        assert proposal.response_body["status"] == "sent"
        assert "email_id" in proposal.response_body
        assert "thread_id" in proposal.response_body
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "email"
        assert delta.operation == "create"
        assert delta.fields["status"] == "delivered"

    @pytest.mark.asyncio
    async def test_list(self, email_pack, sample_state):
        """email_list returns filtered emails from state."""
        proposal = await email_pack.handle_action(
            ToolName("email_list"),
            {"mailbox_owner": "bob@test.com"},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 2  # Two emails addressed to bob
        assert len(body["emails"]) == 2

    @pytest.mark.asyncio
    async def test_read(self, email_pack, sample_state):
        """email_read transitions delivered -> read."""
        proposal = await email_pack.handle_action(
            ToolName("email_read"),
            {"email_id": "email-aaa111"},
            sample_state,
        )
        assert "email" in proposal.response_body
        # Should have a state delta for delivered -> read
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.operation == "update"
        assert delta.fields["status"] == "read"
        assert delta.previous_fields["status"] == "delivered"

    @pytest.mark.asyncio
    async def test_reply(self, email_pack, sample_state):
        """email_reply creates reply with thread_id and in_reply_to."""
        proposal = await email_pack.handle_action(
            ToolName("email_reply"),
            {
                "email_id": "email-aaa111",
                "from_addr": "bob@test.com",
                "body": "I'm doing well, thanks!",
            },
            sample_state,
        )
        body = proposal.response_body
        assert body["status"] == "sent"
        assert body["in_reply_to"] == "email-aaa111"
        assert body["thread_id"] == "thread-t001"
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.fields["in_reply_to"] == "email-aaa111"
        assert delta.fields["thread_id"] == "thread-t001"

    @pytest.mark.asyncio
    async def test_search(self, email_pack, sample_state):
        """email_search filters by query/sender/subject."""
        # Search by sender
        proposal = await email_pack.handle_action(
            ToolName("email_search"),
            {"sender": "alice@test.com"},
            sample_state,
        )
        assert proposal.response_body["count"] == 1
        assert proposal.response_body["results"][0]["from_addr"] == "alice@test.com"

        # Search by subject
        proposal2 = await email_pack.handle_action(
            ToolName("email_search"),
            {"subject": "Meeting"},
            sample_state,
        )
        assert proposal2.response_body["count"] == 1

        # Search by query
        proposal3 = await email_pack.handle_action(
            ToolName("email_search"),
            {"query": "report"},
            sample_state,
        )
        assert proposal3.response_body["count"] == 1

    @pytest.mark.asyncio
    async def test_mark_read(self, email_pack, sample_state):
        """email_mark_read batch transitions delivered emails."""
        proposal = await email_pack.handle_action(
            ToolName("email_mark_read"),
            {"email_ids": ["email-aaa111", "email-ccc333"]},
            sample_state,
        )
        body = proposal.response_body
        # aaa111 is to bob, ccc333 is to alice — both delivered
        # But ccc333 is in state, so mark_read processes it
        assert "email-aaa111" in body["marked"]
        # Check deltas were created for delivered emails
        assert len(proposal.proposed_state_deltas) >= 1


class TestEmailPackValidation:
    def test_schemas_validate(self, email_pack):
        """Entity data matching the schemas passes SchemaValidator."""
        validator = SchemaValidator()
        schemas = email_pack.get_entity_schemas()

        # Valid legacy email entity
        valid_email = {
            "email_id": "email-xyz",
            "from_addr": "a@b.com",
            "to_addr": "c@d.com",
            "subject": "Hi",
            "body": "Hello",
            "status": "delivered",
        }
        result = validator.validate_entity(valid_email, schemas["email"])
        assert result.valid, f"Email validation errors: {result.errors}"

        # Valid mailbox entity
        valid_mailbox = {"mailbox_id": "mb-1", "owner": "test@test.com"}
        result2 = validator.validate_entity(valid_mailbox, schemas["mailbox"])
        assert result2.valid, f"Mailbox validation errors: {result2.errors}"

        # Valid Gmail-aligned thread entity
        valid_thread = {"id": "t-1", "snippet": "Thread snippet"}
        result3 = validator.validate_entity(valid_thread, schemas["gmail_thread"])
        assert result3.valid, f"Thread validation errors: {result3.errors}"

        # Valid Gmail-aligned message entity
        valid_message = {
            "id": "msg-1",
            "threadId": "t-1",
            "labelIds": ["INBOX"],
            "snippet": "Hello...",
            "subject": "Hi",
            "body": "Hello",
        }
        result4 = validator.validate_entity(valid_message, schemas["gmail_message"])
        assert result4.valid, f"Message validation errors: {result4.errors}"

        # Valid label entity
        valid_label = {"id": "INBOX", "name": "INBOX"}
        result5 = validator.validate_entity(valid_label, schemas["gmail_label"])
        assert result5.valid, f"Label validation errors: {result5.errors}"

        # Valid draft entity
        valid_draft = {"id": "draft-1"}
        result6 = validator.validate_entity(valid_draft, schemas["gmail_draft"])
        assert result6.valid, f"Draft validation errors: {result6.errors}"

    def test_state_machines_validate(self, email_pack):
        """Valid transitions pass StateMachineValidator."""
        sm_validator = StateMachineValidator()
        sm = email_pack.get_state_machines()["email"]

        # delivered -> read is valid
        result = sm_validator.validate_transition("delivered", "read", sm)
        assert result.valid

        # read -> archived is valid
        result2 = sm_validator.validate_transition("read", "archived", sm)
        assert result2.valid

        # read -> delivered is NOT valid
        result3 = sm_validator.validate_transition("read", "delivered", sm)
        assert not result3.valid
