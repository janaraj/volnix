"""Tests for volnix.packs.verified.zendesk -- TicketsPack through pack's own handle_action."""

import pytest

from volnix.core.context import ResponseProposal
from volnix.core.types import ToolName
from volnix.packs.verified.zendesk.pack import TicketsPack
from volnix.packs.verified.zendesk.schemas import ORGANIZATION_ENTITY_SCHEMA
from volnix.packs.verified.zendesk.state_machines import TICKET_STATES, TICKET_TRANSITIONS
from volnix.validation.schema import SchemaValidator
from volnix.validation.state_machine import StateMachineValidator


@pytest.fixture
def tickets_pack():
    return TicketsPack()


@pytest.fixture
def sample_state():
    """State with pre-existing tickets, comments, users, and groups."""
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
                "custom_fields": [{"id": 1, "value": "browser"}],
                "collaborator_ids": ["user-201"],
                "follower_ids": [],
                "organization_id": "org-001",
                "external_id": "ext-001",
                "brand_id": "brand-001",
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
                "html_body": "<p>I get an error when logging in.</p>",
                "public": True,
                "attachments": [],
                "created_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "id": "comment-002",
                "ticket_id": "ticket-001",
                "author_id": "user-200",
                "body": "Can you try clearing your cache?",
                "html_body": "<p>Can you try clearing your cache?</p>",
                "public": True,
                "attachments": [],
                "created_at": "2026-01-01T01:00:00+00:00",
            },
            {
                "id": "comment-003",
                "ticket_id": "ticket-002",
                "author_id": "user-101",
                "body": "Please add dark mode.",
                "html_body": "<p>Please add dark mode.</p>",
                "public": True,
                "attachments": [],
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
                "verified": True,
                "locale": "en-US",
                "created_at": "2025-06-01T00:00:00+00:00",
            },
            {
                "id": "user-101",
                "name": "Bob Requester",
                "email": "bob@example.com",
                "role": "end-user",
                "active": True,
                "verified": False,
                "created_at": "2025-06-02T00:00:00+00:00",
            },
            {
                "id": "user-200",
                "name": "Charlie Agent",
                "email": "charlie@support.com",
                "role": "agent",
                "active": True,
                "verified": True,
                "default_group_id": "group-001",
                "created_at": "2025-01-01T00:00:00+00:00",
            },
            {
                "id": "user-201",
                "name": "Dana Agent",
                "email": "dana@support.com",
                "role": "agent",
                "active": True,
                "verified": True,
                "default_group_id": "group-001",
                "created_at": "2025-01-02T00:00:00+00:00",
            },
        ],
        "groups": [
            {
                "id": "group-001",
                "name": "Support Team",
                "description": "First line support",
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
            },
            {
                "id": "group-002",
                "name": "Engineering",
                "description": "Engineering escalation",
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
            },
        ],
        "organizations": [
            {
                "id": "org-001",
                "name": "Acme Corp",
                "external_id": "ext-org-001",
                "domain_names": ["acme.com"],
                "details": "Enterprise customer",
                "notes": "",
                "group_id": "group-001",
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
            },
        ],
    }


class TestTicketsPackMetadata:
    def test_metadata(self, tickets_pack):
        """pack_name, category, fidelity_tier are correct."""
        assert tickets_pack.pack_name == "zendesk"
        assert tickets_pack.category == "work_management"
        assert tickets_pack.fidelity_tier == 1

    def test_tools_count_and_names(self, tickets_pack):
        """TicketsPack exposes 12 tools with expected names."""
        tools = tickets_pack.get_tools()
        assert len(tools) == 12
        tool_names = {t["name"] for t in tools}
        assert tool_names == {
            "tickets.list",
            "tickets.read",
            "tickets.create",
            "tickets.update",
            "tickets.delete",
            "tickets.search",
            "tickets.comments.list",
            "tickets.comment_create",
            "customers.list",
            "customers.read",
            "groups.list",
            "groups.read",
        }

    def test_entity_schemas(self, tickets_pack):
        """ticket, comment, user, group, and organization entity schemas are present."""
        schemas = tickets_pack.get_entity_schemas()
        assert "ticket" in schemas
        assert "comment" in schemas
        assert "user" in schemas
        assert "group" in schemas
        assert "organization" in schemas

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
        assert len(names) == 12
        assert "tickets.create" in names
        assert "tickets.delete" in names
        assert "tickets.search" in names
        assert "groups.list" in names
        assert "groups.read" in names

    def test_ticket_schema_has_new_fields(self, tickets_pack):
        """Ticket schema includes P1 audit fields."""
        props = tickets_pack.get_entity_schemas()["ticket"]["properties"]
        assert "custom_fields" in props
        assert "collaborator_ids" in props
        assert "follower_ids" in props
        assert "organization_id" in props
        assert "satisfaction_rating" in props
        assert "problem_id" in props
        assert "external_id" in props
        assert "brand_id" in props

    def test_comment_schema_has_new_fields(self, tickets_pack):
        """Comment schema includes P1 audit fields."""
        props = tickets_pack.get_entity_schemas()["comment"]["properties"]
        assert "html_body" in props
        assert "attachments" in props
        assert "audit_id" in props

    def test_user_schema_has_new_fields(self, tickets_pack):
        """User schema includes P1 audit fields."""
        props = tickets_pack.get_entity_schemas()["user"]["properties"]
        assert "verified" in props
        assert "external_id" in props
        assert "locale" in props
        assert "phone" in props
        assert "photo" in props
        assert "default_group_id" in props

    def test_organization_schema(self):
        """Organization schema has expected fields."""
        props = ORGANIZATION_ENTITY_SCHEMA["properties"]
        assert "id" in props
        assert "name" in props
        assert "external_id" in props
        assert "domain_names" in props
        assert "details" in props
        assert "notes" in props
        assert "group_id" in props
        assert ORGANIZATION_ENTITY_SCHEMA["x-volnix-identity"] == "id"


class TestTicketsPackActions:
    async def test_tickets_create(self, tickets_pack):
        """tickets_create creates ticket with status='new' and initial comment."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.create"),
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
        # P1: comment has html_body
        assert "html_body" in comment_delta.fields
        assert comment_delta.fields["attachments"] == []

    async def test_tickets_create_minimal(self, tickets_pack):
        """tickets_create works with only required fields."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.create"),
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
        """tickets_update changes status and records previous_fields."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.update"),
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
        """tickets_update returns Zendesk-format error for nonexistent ticket."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.update"),
            {"id": "ticket-nonexistent", "status": "open"},
            sample_state,
        )
        assert proposal.response_body["error"] == "RecordNotFound"
        assert "description" in proposal.response_body

    async def test_tickets_delete(self, tickets_pack, sample_state):
        """tickets_delete soft-deletes a ticket."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.delete"),
            {"id": "ticket-001"},
            sample_state,
        )
        assert isinstance(proposal, ResponseProposal)
        assert proposal.response_body == {}
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.operation == "delete"
        assert delta.fields["status"] == "deleted"
        assert delta.previous_fields["status"] == "new"

    async def test_tickets_delete_not_found(self, tickets_pack, sample_state):
        """tickets_delete returns Zendesk error for nonexistent ticket."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.delete"),
            {"id": "ticket-nonexistent"},
            sample_state,
        )
        assert proposal.response_body["error"] == "RecordNotFound"

    async def test_tickets_search_free_text(self, tickets_pack, sample_state):
        """tickets_search finds tickets by free text."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.search"),
            {"query": "login"},
            sample_state,
        )
        results = proposal.response_body["results"]
        assert len(results) == 1
        assert results[0]["id"] == "ticket-001"
        assert proposal.proposed_state_deltas == []

    async def test_tickets_search_structured_filter(self, tickets_pack, sample_state):
        """tickets_search supports structured filters like status:open."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.search"),
            {"query": "status:open"},
            sample_state,
        )
        results = proposal.response_body["results"]
        assert len(results) == 1
        assert results[0]["id"] == "ticket-002"

    async def test_tickets_search_mixed(self, tickets_pack, sample_state):
        """tickets_search supports mixed structured + free text."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.search"),
            {"query": "type:problem billing"},
            sample_state,
        )
        results = proposal.response_body["results"]
        assert len(results) == 1
        assert results[0]["id"] == "ticket-003"

    async def test_tickets_search_no_results(self, tickets_pack, sample_state):
        """tickets_search returns empty for non-matching query."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.search"),
            {"query": "nonexistent_xyz"},
            sample_state,
        )
        assert proposal.response_body["results"] == []
        assert proposal.response_body["count"] == 0

    async def test_tickets_list_all(self, tickets_pack, sample_state):
        """tickets_list returns all tickets when no filters given."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.list"),
            {},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 3
        assert len(body["tickets"]) == 3
        assert proposal.proposed_state_deltas == []

    async def test_tickets_list_by_status(self, tickets_pack, sample_state):
        """tickets_list filters by status."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.list"),
            {"status": "open"},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 1
        assert body["tickets"][0]["id"] == "ticket-002"

    async def test_tickets_list_by_assignee(self, tickets_pack, sample_state):
        """tickets_list filters by assignee_id."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.list"),
            {"assignee_id": "user-200"},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 2
        ids = {t["id"] for t in body["tickets"]}
        assert ids == {"ticket-001", "ticket-002"}

    async def test_tickets_list_by_requester(self, tickets_pack, sample_state):
        """tickets_list filters by requester_id."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.list"),
            {"requester_id": "user-100"},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 2
        ids = {t["id"] for t in body["tickets"]}
        assert ids == {"ticket-001", "ticket-003"}

    async def test_tickets_list_pagination(self, tickets_pack, sample_state):
        """tickets_list supports per_page and page parameters."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.list"),
            {"per_page": 2, "page": 1},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 2
        assert body["next_page"] == 2

        proposal2 = await tickets_pack.handle_action(
            ToolName("tickets.list"),
            {"per_page": 2, "page": 2},
            sample_state,
        )
        body2 = proposal2.response_body
        assert body2["count"] == 1
        assert body2["next_page"] is None

    async def test_tickets_show(self, tickets_pack, sample_state):
        """tickets_show returns ticket by ID."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.read"),
            {"id": "ticket-002"},
            sample_state,
        )
        assert proposal.response_body["ticket"]["id"] == "ticket-002"
        assert proposal.response_body["ticket"]["subject"] == "Feature request: dark mode"
        assert proposal.proposed_state_deltas == []

    async def test_tickets_show_not_found(self, tickets_pack, sample_state):
        """tickets_show returns Zendesk error for nonexistent ticket."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.read"),
            {"id": "ticket-nonexistent"},
            sample_state,
        )
        assert proposal.response_body["error"] == "RecordNotFound"
        assert "description" in proposal.response_body

    async def test_ticket_comments_create(self, tickets_pack, sample_state):
        """ticket_comments_create creates comment and updates ticket."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.comment_create"),
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
        # P1 new fields
        assert "html_body" in comment
        assert comment["attachments"] == []

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
        """ticket_comments_create supports private (internal) comments."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.comment_create"),
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
        """ticket_comments_create returns Zendesk error for nonexistent ticket."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.comment_create"),
            {
                "id": "ticket-nonexistent",
                "body": "Hello",
                "author_id": "user-100",
            },
            sample_state,
        )
        assert proposal.response_body["error"] == "RecordNotFound"

    async def test_ticket_comments_list(self, tickets_pack, sample_state):
        """ticket_comments_list returns comments for a specific ticket."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.comments.list"),
            {"id": "ticket-001"},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 2
        assert len(body["comments"]) == 2
        assert all(c["ticket_id"] == "ticket-001" for c in body["comments"])
        assert proposal.proposed_state_deltas == []

    async def test_ticket_comments_list_empty(self, tickets_pack, sample_state):
        """ticket_comments_list returns empty for ticket with no comments."""
        proposal = await tickets_pack.handle_action(
            ToolName("tickets.comments.list"),
            {"id": "ticket-003"},
            sample_state,
        )
        assert proposal.response_body["count"] == 0
        assert proposal.response_body["comments"] == []

    async def test_users_list_all(self, tickets_pack, sample_state):
        """users_list returns all users when no filter given."""
        proposal = await tickets_pack.handle_action(
            ToolName("customers.list"),
            {},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 4
        assert len(body["users"]) == 4
        assert proposal.proposed_state_deltas == []

    async def test_users_list_by_role(self, tickets_pack, sample_state):
        """users_list filters by role."""
        proposal = await tickets_pack.handle_action(
            ToolName("customers.list"),
            {"role": "agent"},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 2
        assert all(u["role"] == "agent" for u in body["users"])

    async def test_users_show(self, tickets_pack, sample_state):
        """users_show returns user by ID."""
        proposal = await tickets_pack.handle_action(
            ToolName("customers.read"),
            {"id": "user-200"},
            sample_state,
        )
        user = proposal.response_body["user"]
        assert user["id"] == "user-200"
        assert user["name"] == "Charlie Agent"
        assert proposal.proposed_state_deltas == []

    async def test_users_show_not_found(self, tickets_pack, sample_state):
        """users_show returns Zendesk error for nonexistent user."""
        proposal = await tickets_pack.handle_action(
            ToolName("customers.read"),
            {"id": "user-nonexistent"},
            sample_state,
        )
        assert proposal.response_body["error"] == "RecordNotFound"

    async def test_groups_list(self, tickets_pack, sample_state):
        """groups_list returns all groups."""
        proposal = await tickets_pack.handle_action(
            ToolName("groups.list"),
            {},
            sample_state,
        )
        body = proposal.response_body
        assert body["count"] == 2
        assert len(body["groups"]) == 2
        assert proposal.proposed_state_deltas == []

    async def test_groups_list_empty(self, tickets_pack):
        """groups_list returns empty from empty state."""
        proposal = await tickets_pack.handle_action(
            ToolName("groups.list"),
            {},
            {},
        )
        assert proposal.response_body["groups"] == []
        assert proposal.response_body["count"] == 0

    async def test_groups_show(self, tickets_pack, sample_state):
        """groups_show returns group by ID."""
        proposal = await tickets_pack.handle_action(
            ToolName("groups.read"),
            {"id": "group-001"},
            sample_state,
        )
        group = proposal.response_body["group"]
        assert group["id"] == "group-001"
        assert group["name"] == "Support Team"
        assert proposal.proposed_state_deltas == []

    async def test_groups_show_not_found(self, tickets_pack, sample_state):
        """groups_show returns Zendesk error for nonexistent group."""
        proposal = await tickets_pack.handle_action(
            ToolName("groups.read"),
            {"id": "group-nonexistent"},
            sample_state,
        )
        assert proposal.response_body["error"] == "RecordNotFound"


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

    def test_organization_schema_validates(self, tickets_pack):
        """Valid organization entity passes SchemaValidator."""
        validator = SchemaValidator()
        schemas = tickets_pack.get_entity_schemas()

        valid_org = {
            "id": "org-xyz",
            "name": "Test Org",
        }
        result = validator.validate_entity(valid_org, schemas["organization"])
        assert result.valid, f"Organization validation errors: {result.errors}"

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
