"""Tests for terrarium.packs.verified.tickets — TicketsPack through pack's own handle_action."""

import pytest

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.verified.tickets.pack import TicketsPack
from terrarium.packs.verified.tickets.state_machines import TICKET_STATES, TICKET_TRANSITIONS
from terrarium.validation.schema import SchemaValidator
from terrarium.validation.state_machine import StateMachineValidator


@pytest.fixture
def tickets_pack():
    return TicketsPack()


@pytest.fixture
def sample_state():
    """State with pre-existing tickets, comments, and users for read/list/filter tests."""
    return {
        "tickets": [
            {
                "id": "ticket-001",
                "subject": "Cannot login",
                "description": "I get an error when logging in.",
                "status": "new",
                "priority": "high",
                "type": "problem",
                "requester_id": "user-100",
                "assignee_id": "user-200",
                "tags": ["login", "auth"],
                "created_at": "2026-01-01T00:00:00+00:00",
                "updated_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": "ticket-002",
                "subject": "Feature request: dark mode",
                "description": "Please add dark mode.",
                "status": "open",
                "priority": "normal",
                "type": "question",
                "requester_id": "user-101",
                "assignee_id": "user-200",
                "tags": ["feature-request"],
                "created_at": "2026-01-02T00:00:00+00:00",
                "updated_at": "2026-01-02T12:00:00+00:00",
            },
            {
                "id": "ticket-003",
                "subject": "Billing issue",
                "description": "I was double charged.",
                "status": "pending",
                "priority": "urgent",
                "type": "problem",
                "requester_id": "user-100",
                "assignee_id": "user-201",
                "tags": ["billing"],
                "created_at": "2026-01-03T00:00:00+00:00",
                "updated_at": "2026-01-03T00:00:00+00:00",
            },
        ],
        "comments": [
            {
                "id": "comment-001",
                "ticket_id": "ticket-001",
                "author_id": "user-100",
                "body": "I get an error when logging in.",
                "public": True,
                "created_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": "comment-002",
                "ticket_id": "ticket-001",
                "author_id": "user-200",
                "body": "Can you try clearing your cache?",
                "public": True,
                "created_at": "2026-01-01T01:00:00+00:00",
            },
            {
                "id": "comment-003",
                "ticket_id": "ticket-002",
                "author_id": "user-101",
                "body": "Please add dark mode.",
                "public": True,
                "created_at": "2026-01-02T00:00:00+00:00",
            },
        ],
        "users": [
            {
                "id": "user-100",
                "name": "Alice Requester",
                "email": "alice@example.com",
                "role": "end-user",
                "active": True,
                "created_at": "2025-06-01T00:00:00+00:00",
            },
            {
                "id": "user-101",
                "name": "Bob Requester",
                "email": "bob@example.com",
                "role": "end-user",
                "active": True,
                "created_at": "2025-06-02T00:00:00+00:00",
            },
            {
                "id": "user-200",
                "name": "Charlie Agent",
                "email": "charlie@support.com",
                "role": "agent",
                "active": True,
                "created_at": "2025-01-01T00:00:00+00:00",
            },
            {
                "id": "user-201",
                "name": "Dana Agent",
                "email": "dana@support.com",
                "role": "agent",
                "active": True,
                "created_at": "2025-01-02T00:00:00+00:00",
            },
        ],
    }


class TestTicketsPackMetadata:
    def test_metadata(self, tickets_pack):
        """pack_name, category, fidelity_tier are correct."""
        assert tickets_pack.pack_name == "tickets"
        assert tickets_pack.category == "work_management"
        assert tickets_pack.fidelity_tier == 1

    def test_tools_count_and_names(self, tickets_pack):
        """TicketsPack exposes 8 tools with expected names."""
        tools = tickets_pack.get_tools()
        assert len(tools) == 8
        tool_names = {t["name"] for t in tools}
        assert tool_names == {
            "zendesk_tickets_list",
            "zendesk_tickets_show",
            "zendesk_tickets_create",
            "zendesk_tickets_update",
            "zendesk_ticket_comments_list",
            "zendesk_ticket_comments_create",
            "zendesk_users_list",
            "zendesk_users_show",
        }

    def test_entity_schemas(self, tickets_pack):
        """ticket, comment, user, and group entity schemas are present."""
        schemas = tickets_pack.get_entity_schemas()
        assert "ticket" in schemas
        assert "comment" in schemas
        assert "user" in schemas
        assert "group" in schemas

    def test_state_machines(self, tickets_pack):
        """Ticket state machine transitions are present."""
        sms = tickets_pack.get_state_machines()
        assert "ticket" in sms
        assert "transitions" in sms["ticket"]
        transitions = sms["ticket"]["transitions"]
        assert "new" in transitions
        assert "open" in transitions["new"]

    def test_get_tool_names(self, tickets_pack):
        """get_tool_names() returns list of name strings."""
        names = tickets_pack.get_tool_names()
        assert len(names) == 8
        assert "zendesk_tickets_create" in names


class TestTicketsPackActions:
    async def test_tickets_create(self, tickets_pack):
        """zendesk_tickets_create creates ticket with status='new' and initial comment."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_tickets_create"),
            {
                "subject": "My printer is on fire",
                "description": "Literally flames coming out.",
                "requester_id": "user-100",
                "priority": "urgent",
                "type": "problem",
                "assignee_id": "user-200",
                "tags": ["printer", "fire"],
            },
            {},
        )
        assert isinstance(proposal, ResponseProposal)
        ticket = proposal.response_body["ticket"]
        assert ticket["subject"] == "My printer is on fire"
        assert ticket["status"] == "new"
        assert ticket["priority"] == "urgent"
        assert ticket["requester_id"] == "user-100"
        assert ticket["assignee_id"] == "user-200"
        assert ticket["tags"] == ["printer", "fire"]
        assert "id" in ticket
        assert "created_at" in ticket
        assert "updated_at" in ticket

        # Two deltas: one for ticket, one for initial comment
        assert len(proposal.proposed_state_deltas) == 2
        ticket_delta = proposal.proposed_state_deltas[0]
        comment_delta = proposal.proposed_state_deltas[1]
        assert ticket_delta.entity_type == "ticket"
        assert ticket_delta.operation == "create"
        assert comment_delta.entity_type == "comment"
        assert comment_delta.operation == "create"
        assert comment_delta.fields["body"] == "Literally flames coming out."
        assert comment_delta.fields["ticket_id"] == ticket_delta.fields["id"]

    async def test_tickets_create_minimal(self, tickets_pack):
        """zendesk_tickets_create works with only required fields."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_tickets_create"),
            {
                "subject": "Simple question",
                "description": "How do I reset my password?",
                "requester_id": "user-101",
            },
            {},
        )
        ticket = proposal.response_body["ticket"]
        assert ticket["status"] == "new"
        assert "priority" not in ticket
        assert "assignee_id" not in ticket
        assert len(proposal.proposed_state_deltas) == 2

    async def test_tickets_update_status(self, tickets_pack, sample_state):
        """zendesk_tickets_update changes status and records previous_fields."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_tickets_update"),
            {"id": "ticket-001", "status": "open"},
            sample_state,
        )
        assert isinstance(proposal, ResponseProposal)
        ticket = proposal.response_body["ticket"]
        assert ticket["status"] == "open"

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.operation == "update"
        assert delta.fields["status"] == "open"
        assert delta.previous_fields is not None
        assert delta.previous_fields["status"] == "new"
        assert "updated_at" in delta.fields

    async def test_tickets_update_not_found(self, tickets_pack, sample_state):
        """zendesk_tickets_update returns error for nonexistent ticket."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_tickets_update"),
            {"id": "ticket-nonexistent", "status": "open"},
            sample_state,
        )
        assert "error" in proposal.response_body

    async def test_tickets_list_all(self, tickets_pack, sample_state):
        """zendesk_tickets_list returns all tickets when no filters given."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_tickets_list"),
            {},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 3
        assert len(body["tickets"]) == 3
        assert proposal.proposed_state_deltas == []

    async def test_tickets_list_by_status(self, tickets_pack, sample_state):
        """zendesk_tickets_list filters by status."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_tickets_list"),
            {"status": "open"},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 1
        assert body["tickets"][0]["id"] == "ticket-002"

    async def test_tickets_list_by_assignee(self, tickets_pack, sample_state):
        """zendesk_tickets_list filters by assignee_id."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_tickets_list"),
            {"assignee_id": "user-200"},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 2
        ids = {t["id"] for t in body["tickets"]}
        assert ids == {"ticket-001", "ticket-002"}

    async def test_tickets_list_by_requester(self, tickets_pack, sample_state):
        """zendesk_tickets_list filters by requester_id."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_tickets_list"),
            {"requester_id": "user-100"},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 2
        ids = {t["id"] for t in body["tickets"]}
        assert ids == {"ticket-001", "ticket-003"}

    async def test_tickets_list_pagination(self, tickets_pack, sample_state):
        """zendesk_tickets_list supports per_page and page parameters."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_tickets_list"),
            {"per_page": 2, "page": 1},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 2
        assert body["next_page"] == 2

        proposal2 = await tickets_pack.handle_action(
            ToolName("zendesk_tickets_list"),
            {"per_page": 2, "page": 2},
            sample_state,
        )
        body2 = proposal2.response_body
        assert body2["count"] == 1
        assert body2["next_page"] is None

    async def test_tickets_show(self, tickets_pack, sample_state):
        """zendesk_tickets_show returns ticket by ID."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_tickets_show"),
            {"id": "ticket-002"},
            sample_state,
        )
        assert proposal.response_body["ticket"]["id"] == "ticket-002"
        assert proposal.response_body["ticket"]["subject"] == "Feature request: dark mode"
        assert proposal.proposed_state_deltas == []

    async def test_tickets_show_not_found(self, tickets_pack, sample_state):
        """zendesk_tickets_show returns error for nonexistent ticket."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_tickets_show"),
            {"id": "ticket-nonexistent"},
            sample_state,
        )
        assert "error" in proposal.response_body

    async def test_ticket_comments_create(self, tickets_pack, sample_state):
        """zendesk_ticket_comments_create creates comment and updates ticket."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_ticket_comments_create"),
            {
                "id": "ticket-001",
                "body": "I tried clearing my cache but it still fails.",
                "author_id": "user-100",
                "public": True,
            },
            sample_state,
        )
        assert isinstance(proposal, ResponseProposal)
        comment = proposal.response_body["comment"]
        assert comment["body"] == "I tried clearing my cache but it still fails."
        assert comment["ticket_id"] == "ticket-001"
        assert comment["author_id"] == "user-100"
        assert comment["public"] is True
        assert "id" in comment
        assert "created_at" in comment

        # Two deltas: one for comment create, one for ticket updated_at
        assert len(proposal.proposed_state_deltas) == 2
        comment_delta = proposal.proposed_state_deltas[0]
        ticket_delta = proposal.proposed_state_deltas[1]
        assert comment_delta.entity_type == "comment"
        assert comment_delta.operation == "create"
        assert ticket_delta.entity_type == "ticket"
        assert ticket_delta.operation == "update"
        assert "updated_at" in ticket_delta.fields

    async def test_ticket_comments_create_private(self, tickets_pack, sample_state):
        """zendesk_ticket_comments_create supports private (internal) comments."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_ticket_comments_create"),
            {
                "id": "ticket-001",
                "body": "Internal note: escalate to tier 2.",
                "author_id": "user-200",
                "public": False,
            },
            sample_state,
        )
        comment = proposal.response_body["comment"]
        assert comment["public"] is False

    async def test_ticket_comments_create_not_found(self, tickets_pack, sample_state):
        """zendesk_ticket_comments_create returns error for nonexistent ticket."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_ticket_comments_create"),
            {
                "id": "ticket-nonexistent",
                "body": "Hello",
                "author_id": "user-100",
            },
            sample_state,
        )
        assert "error" in proposal.response_body

    async def test_ticket_comments_list(self, tickets_pack, sample_state):
        """zendesk_ticket_comments_list returns comments for a specific ticket."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_ticket_comments_list"),
            {"id": "ticket-001"},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 2
        assert len(body["comments"]) == 2
        assert all(c["ticket_id"] == "ticket-001" for c in body["comments"])
        assert proposal.proposed_state_deltas == []

    async def test_ticket_comments_list_empty(self, tickets_pack, sample_state):
        """zendesk_ticket_comments_list returns empty for ticket with no comments."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_ticket_comments_list"),
            {"id": "ticket-003"},
            sample_state,
        )
        assert proposal.response_body["count"] == 0
        assert proposal.response_body["comments"] == []

    async def test_users_list_all(self, tickets_pack, sample_state):
        """zendesk_users_list returns all users when no filter given."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_users_list"),
            {},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 4
        assert len(body["users"]) == 4
        assert proposal.proposed_state_deltas == []

    async def test_users_list_by_role(self, tickets_pack, sample_state):
        """zendesk_users_list filters by role."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_users_list"),
            {"role": "agent"},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 2
        assert all(u["role"] == "agent" for u in body["users"])

    async def test_users_show(self, tickets_pack, sample_state):
        """zendesk_users_show returns user by ID."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_users_show"),
            {"id": "user-200"},
            sample_state,
        )
        user = proposal.response_body["user"]
        assert user["id"] == "user-200"
        assert user["name"] == "Charlie Agent"
        assert proposal.proposed_state_deltas == []

    async def test_users_show_not_found(self, tickets_pack, sample_state):
        """zendesk_users_show returns error for nonexistent user."""
        proposal = await tickets_pack.handle_action(
            ToolName("zendesk_users_show"),
            {"id": "user-nonexistent"},
            sample_state,
        )
        assert "error" in proposal.response_body


class TestTicketsPackValidation:
    def test_ticket_schema_validates(self, tickets_pack):
        """Valid ticket entity passes SchemaValidator."""
        validator = SchemaValidator()
        schemas = tickets_pack.get_entity_schemas()

        valid_ticket = {
            "id": "ticket-xyz",
            "subject": "Test ticket",
            "description": "A test.",
            "status": "new",
            "requester_id": "user-001",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
        result = validator.validate_entity(valid_ticket, schemas["ticket"])
        assert result.valid, f"Ticket validation errors: {result.errors}"

    def test_comment_schema_validates(self, tickets_pack):
        """Valid comment entity passes SchemaValidator."""
        validator = SchemaValidator()
        schemas = tickets_pack.get_entity_schemas()

        valid_comment = {
            "id": "comment-xyz",
            "ticket_id": "ticket-001",
            "author_id": "user-001",
            "body": "A comment.",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        result = validator.validate_entity(valid_comment, schemas["comment"])
        assert result.valid, f"Comment validation errors: {result.errors}"

    def test_user_schema_validates(self, tickets_pack):
        """Valid user entity passes SchemaValidator."""
        validator = SchemaValidator()
        schemas = tickets_pack.get_entity_schemas()

        valid_user = {
            "id": "user-xyz",
            "name": "Test User",
            "email": "test@example.com",
            "role": "agent",
        }
        result = validator.validate_entity(valid_user, schemas["user"])
        assert result.valid, f"User validation errors: {result.errors}"

    def test_group_schema_validates(self, tickets_pack):
        """Valid group entity passes SchemaValidator."""
        validator = SchemaValidator()
        schemas = tickets_pack.get_entity_schemas()

        valid_group = {
            "id": "group-xyz",
            "name": "Support Team",
        }
        result = validator.validate_entity(valid_group, schemas["group"])
        assert result.valid, f"Group validation errors: {result.errors}"

    def test_state_machine_valid_transitions(self, tickets_pack):
        """Valid ticket transitions pass StateMachineValidator."""
        sm_validator = StateMachineValidator()
        sm = tickets_pack.get_state_machines()["ticket"]

        # new -> open is valid
        result = sm_validator.validate_transition("new", "open", sm)
        assert result.valid

        # open -> solved is valid
        result2 = sm_validator.validate_transition("open", "solved", sm)
        assert result2.valid

        # solved -> closed is valid
        result3 = sm_validator.validate_transition("solved", "closed", sm)
        assert result3.valid

    def test_state_machine_invalid_transitions(self, tickets_pack):
        """Invalid ticket transitions are rejected by StateMachineValidator."""
        sm_validator = StateMachineValidator()
        sm = tickets_pack.get_state_machines()["ticket"]

        # closed -> solved is NOT valid (closed has no transitions)
        result = sm_validator.validate_transition("closed", "solved", sm)
        assert not result.valid

        # new -> closed is NOT valid
        result2 = sm_validator.validate_transition("new", "closed", sm)
        assert not result2.valid

    def test_ticket_states_complete(self):
        """TICKET_STATES matches all keys in TICKET_TRANSITIONS."""
        assert set(TICKET_STATES) == set(TICKET_TRANSITIONS.keys())

    def test_all_transitions_reference_valid_states(self):
        """Every target state in TICKET_TRANSITIONS is itself a valid state."""
        valid = set(TICKET_STATES)
        for source, targets in TICKET_TRANSITIONS.items():
            for target in targets:
                assert target in valid, (
                    f"Transition {source} -> {target}: target is not a valid state"
                )
