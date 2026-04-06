"""Tests for volnix.packs.verified.notion -- NotionPack through pack's own handle_action."""

import pytest

from volnix.core.context import ResponseProposal
from volnix.core.types import ToolName
from volnix.packs.verified.notion.pack import NotionPack
from volnix.packs.verified.notion.schemas import (
    BLOCK_ENTITY_SCHEMA,
    COMMENT_ENTITY_SCHEMA,
    DATABASE_ENTITY_SCHEMA,
    PAGE_ENTITY_SCHEMA,
    USER_ENTITY_SCHEMA,
)
from volnix.packs.verified.notion.state_machines import (
    ARCHIVED_STATES,
    ARCHIVED_TRANSITIONS,
)
from volnix.validation.schema import SchemaValidator
from volnix.validation.state_machine import StateMachineValidator


@pytest.fixture
def notion_pack():
    return NotionPack()


@pytest.fixture
def sample_state():
    """State with pre-existing pages (3), databases (2), blocks (5), users (2), comments (2)."""
    return {
        "pages": [
            {
                "id": "page-001",
                "object": "page",
                "created_time": "2026-01-01T00:00:00+00:00",
                "last_edited_time": "2026-01-01T12:00:00+00:00",
                "created_by": {"object": "user", "id": "user-001"},
                "last_edited_by": {"object": "user", "id": "user-001"},
                "parent": {"type": "database_id", "database_id": "db-001"},
                "archived": False,
                "in_trash": False,
                "properties": {
                    "Name": {
                        "id": "title",
                        "type": "title",
                        "title": [
                            {
                                "type": "text",
                                "text": {"content": "Project Roadmap"},
                                "plain_text": "Project Roadmap",
                            }
                        ],
                    },
                    "Status": {
                        "id": "status",
                        "type": "select",
                        "select": {"name": "In Progress", "color": "blue"},
                    },
                },
                "icon": {"type": "emoji", "emoji": "\ud83d\udcca"},
                "cover": None,
                "url": "https://www.notion.so/page001",
                "public_url": None,
            },
            {
                "id": "page-002",
                "object": "page",
                "created_time": "2026-01-02T00:00:00+00:00",
                "last_edited_time": "2026-01-02T10:00:00+00:00",
                "created_by": {"object": "user", "id": "user-001"},
                "last_edited_by": {"object": "user", "id": "user-002"},
                "parent": {"type": "database_id", "database_id": "db-001"},
                "archived": False,
                "in_trash": False,
                "properties": {
                    "Name": {
                        "id": "title",
                        "type": "title",
                        "title": [
                            {
                                "type": "text",
                                "text": {"content": "Sprint Planning"},
                                "plain_text": "Sprint Planning",
                            }
                        ],
                    },
                    "Status": {
                        "id": "status",
                        "type": "select",
                        "select": {"name": "Done", "color": "green"},
                    },
                },
                "icon": None,
                "cover": None,
                "url": "https://www.notion.so/page002",
                "public_url": None,
            },
            {
                "id": "page-003",
                "object": "page",
                "created_time": "2026-01-03T00:00:00+00:00",
                "last_edited_time": "2026-01-03T08:00:00+00:00",
                "created_by": {"object": "user", "id": "user-001"},
                "last_edited_by": {"object": "user", "id": "user-001"},
                "parent": {"type": "page_id", "page_id": "page-001"},
                "archived": False,
                "in_trash": False,
                "properties": {
                    "title": {
                        "id": "title",
                        "type": "title",
                        "title": [
                            {
                                "type": "text",
                                "text": {"content": "Meeting Notes"},
                                "plain_text": "Meeting Notes",
                            }
                        ],
                    },
                },
                "icon": None,
                "cover": None,
                "url": "https://www.notion.so/page003",
                "public_url": None,
            },
        ],
        "databases": [
            {
                "id": "db-001",
                "object": "database",
                "created_time": "2025-12-01T00:00:00+00:00",
                "last_edited_time": "2026-01-01T00:00:00+00:00",
                "created_by": {"object": "user", "id": "user-001"},
                "last_edited_by": {"object": "user", "id": "user-001"},
                "title": [
                    {
                        "type": "text",
                        "text": {"content": "Tasks"},
                        "plain_text": "Tasks",
                    }
                ],
                "description": [],
                "parent": {"type": "workspace", "workspace": True},
                "archived": False,
                "in_trash": False,
                "is_inline": False,
                "properties": {
                    "Name": {"id": "title", "type": "title", "title": {}},
                    "Status": {
                        "id": "status",
                        "type": "select",
                        "select": {
                            "options": [
                                {"name": "In Progress", "color": "blue"},
                                {"name": "Done", "color": "green"},
                            ]
                        },
                    },
                },
                "url": "https://www.notion.so/db001",
                "public_url": None,
            },
            {
                "id": "db-002",
                "object": "database",
                "created_time": "2025-12-15T00:00:00+00:00",
                "last_edited_time": "2026-01-02T00:00:00+00:00",
                "created_by": {"object": "user", "id": "user-001"},
                "last_edited_by": {"object": "user", "id": "user-002"},
                "title": [
                    {
                        "type": "text",
                        "text": {"content": "Knowledge Base"},
                        "plain_text": "Knowledge Base",
                    }
                ],
                "description": [],
                "parent": {"type": "workspace", "workspace": True},
                "archived": False,
                "in_trash": False,
                "is_inline": False,
                "properties": {
                    "Name": {"id": "title", "type": "title", "title": {}},
                },
                "url": "https://www.notion.so/db002",
                "public_url": None,
            },
        ],
        "blocks": [
            {
                "id": "block-001",
                "object": "block",
                "type": "paragraph",
                "parent": {"type": "page_id", "page_id": "page-001"},
                "created_time": "2026-01-01T00:00:00+00:00",
                "last_edited_time": "2026-01-01T00:00:00+00:00",
                "created_by": {"object": "user", "id": "user-001"},
                "last_edited_by": {"object": "user", "id": "user-001"},
                "archived": False,
                "in_trash": False,
                "has_children": False,
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": "This is the project roadmap."},
                            "plain_text": "This is the project roadmap.",
                        }
                    ]
                },
            },
            {
                "id": "block-002",
                "object": "block",
                "type": "heading_1",
                "parent": {"type": "page_id", "page_id": "page-001"},
                "created_time": "2026-01-01T00:10:00+00:00",
                "last_edited_time": "2026-01-01T00:10:00+00:00",
                "created_by": {"object": "user", "id": "user-001"},
                "last_edited_by": {"object": "user", "id": "user-001"},
                "archived": False,
                "in_trash": False,
                "has_children": False,
                "heading_1": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": "Q1 Goals"},
                            "plain_text": "Q1 Goals",
                        }
                    ]
                },
            },
            {
                "id": "block-003",
                "object": "block",
                "type": "to_do",
                "parent": {"type": "page_id", "page_id": "page-001"},
                "created_time": "2026-01-01T00:20:00+00:00",
                "last_edited_time": "2026-01-01T00:20:00+00:00",
                "created_by": {"object": "user", "id": "user-001"},
                "last_edited_by": {"object": "user", "id": "user-001"},
                "archived": False,
                "in_trash": False,
                "has_children": False,
                "to_do": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": "Ship v2.0"},
                            "plain_text": "Ship v2.0",
                        }
                    ],
                    "checked": False,
                },
            },
            {
                "id": "block-004",
                "object": "block",
                "type": "paragraph",
                "parent": {"type": "page_id", "page_id": "page-002"},
                "created_time": "2026-01-02T00:00:00+00:00",
                "last_edited_time": "2026-01-02T00:00:00+00:00",
                "created_by": {"object": "user", "id": "user-002"},
                "last_edited_by": {"object": "user", "id": "user-002"},
                "archived": False,
                "in_trash": False,
                "has_children": False,
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": "Sprint starts on Monday."},
                            "plain_text": "Sprint starts on Monday.",
                        }
                    ]
                },
            },
            {
                "id": "block-005",
                "object": "block",
                "type": "paragraph",
                "parent": {"type": "block_id", "block_id": "block-001"},
                "created_time": "2026-01-01T01:00:00+00:00",
                "last_edited_time": "2026-01-01T01:00:00+00:00",
                "created_by": {"object": "user", "id": "user-001"},
                "last_edited_by": {"object": "user", "id": "user-001"},
                "archived": False,
                "in_trash": False,
                "has_children": False,
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": "Nested content here."},
                            "plain_text": "Nested content here.",
                        }
                    ]
                },
            },
        ],
        "users": [
            {
                "id": "user-001",
                "object": "user",
                "type": "person",
                "name": "Alice Engineer",
                "avatar_url": "https://example.com/alice.png",
                "person": {"email": "alice@example.com"},
            },
            {
                "id": "user-002",
                "object": "user",
                "type": "bot",
                "name": "Integration Bot",
                "avatar_url": None,
                "bot": {
                    "owner": {"type": "workspace", "workspace": True},
                    "workspace_name": "Engineering",
                },
            },
        ],
        "comments": [
            {
                "id": "comment-001",
                "object": "comment",
                "parent": {"type": "page_id", "page_id": "page-001"},
                "discussion_id": "disc-001",
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": "Looks great, ship it!"},
                        "plain_text": "Looks great, ship it!",
                    }
                ],
                "created_time": "2026-01-01T09:00:00+00:00",
                "last_edited_time": "2026-01-01T09:00:00+00:00",
                "created_by": {"object": "user", "id": "user-001"},
            },
            {
                "id": "comment-002",
                "object": "comment",
                "parent": {"type": "page_id", "page_id": "page-001"},
                "discussion_id": "disc-001",
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": "Agreed, let's finalize."},
                        "plain_text": "Agreed, let's finalize.",
                    }
                ],
                "created_time": "2026-01-01T10:00:00+00:00",
                "last_edited_time": "2026-01-01T10:00:00+00:00",
                "created_by": {"object": "user", "id": "user-002"},
            },
        ],
    }


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------


class TestNotionPackMetadata:
    def test_metadata(self, notion_pack):
        """pack_name, category, fidelity_tier are correct."""
        assert notion_pack.pack_name == "notion"
        assert notion_pack.category == "storage_documents"
        assert notion_pack.fidelity_tier == 1

    def test_tools_count_and_names(self, notion_pack):
        """NotionPack exposes 15 tools with expected names."""
        tools = notion_pack.get_tools()
        assert len(tools) == 15
        tool_names = {t["name"] for t in tools}
        assert tool_names == {
            "pages.create",
            "pages.retrieve",
            "pages.update",
            "databases.create",
            "databases.retrieve",
            "databases.query",
            "blocks.children.list",
            "blocks.children.append",
            "blocks.retrieve",
            "blocks.delete",
            "users.list",
            "users.me",
            "search",
            "comments.create",
            "comments.list",
        }

    def test_entity_schemas(self, notion_pack):
        """page, database, block, user, and comment entity schemas are present."""
        schemas = notion_pack.get_entity_schemas()
        assert "page" in schemas
        assert "database" in schemas
        assert "block" in schemas
        assert "user" in schemas
        assert "comment" in schemas

    def test_state_machines(self, notion_pack):
        """page, database, and block state machines expose archived transitions."""
        sms = notion_pack.get_state_machines()
        assert "page" in sms
        assert "database" in sms
        assert "block" in sms
        for entity_type in ("page", "database", "block"):
            assert "transitions" in sms[entity_type]
            transitions = sms[entity_type]["transitions"]
            assert "active" in transitions
            assert "archived" in transitions["active"]

    def test_get_tool_names(self, notion_pack):
        """get_tool_names() returns list of 15 name strings."""
        names = notion_pack.get_tool_names()
        assert len(names) == 15
        assert "pages.create" in names
        assert "pages.retrieve" in names
        assert "databases.query" in names
        assert "blocks.delete" in names
        assert "search" in names

    def test_page_schema_has_required_fields(self, notion_pack):
        """Page schema includes required fields and key properties."""
        schema = notion_pack.get_entity_schemas()["page"]
        assert schema["x-volnix-identity"] == "id"
        assert "id" in schema["required"]
        assert "object" in schema["required"]
        assert "parent" in schema["required"]
        assert "properties" in schema["required"]
        props = schema["properties"]
        assert "archived" in props
        assert "in_trash" in props
        assert "icon" in props
        assert "cover" in props
        assert "url" in props
        assert "public_url" in props
        assert "created_by" in props
        assert "last_edited_by" in props

    def test_database_schema_has_required_fields(self, notion_pack):
        """Database schema includes title, properties, and inline flag."""
        schema = notion_pack.get_entity_schemas()["database"]
        assert schema["x-volnix-identity"] == "id"
        assert "title" in schema["required"]
        props = schema["properties"]
        assert "title" in props
        assert "is_inline" in props
        assert "description" in props
        assert "archived" in props

    def test_block_schema_has_type_enum(self, notion_pack):
        """Block schema type field contains the expected block type enum."""
        schema = notion_pack.get_entity_schemas()["block"]
        assert schema["x-volnix-identity"] == "id"
        type_enum = schema["properties"]["type"]["enum"]
        assert "paragraph" in type_enum
        assert "heading_1" in type_enum
        assert "to_do" in type_enum
        assert "code" in type_enum
        assert "callout" in type_enum

    def test_user_schema_has_person_and_bot(self, notion_pack):
        """User schema includes person and bot sub-objects."""
        props = notion_pack.get_entity_schemas()["user"]["properties"]
        assert "person" in props
        assert "bot" in props
        assert "avatar_url" in props
        assert "type" in props
        type_enum = props["type"]["enum"]
        assert "person" in type_enum
        assert "bot" in type_enum

    def test_comment_schema_has_rich_text_and_discussion(self, notion_pack):
        """Comment schema includes rich_text, discussion_id, parent."""
        schema = notion_pack.get_entity_schemas()["comment"]
        assert schema["x-volnix-identity"] == "id"
        props = schema["properties"]
        assert "rich_text" in props
        assert "discussion_id" in props
        assert "parent" in props
        assert "created_by" in props


# ---------------------------------------------------------------------------
# Action tests
# ---------------------------------------------------------------------------


class TestNotionPackActions:
    # --- Pages ---

    async def test_pages_create_in_database(self, notion_pack):
        """pages.create creates a page under a database parent."""
        proposal = await notion_pack.handle_action(
            ToolName("pages.create"),
            {
                "parent": {"database_id": "db-001"},
                "properties": {
                    "Name": {
                        "type": "title",
                        "title": [
                            {"type": "text", "text": {"content": "New Task"}}
                        ],
                    },
                },
            },
            {},
        )
        assert isinstance(proposal, ResponseProposal)
        page = proposal.response_body
        assert page["object"] == "page"
        assert "id" in page
        assert page["parent"] == {"database_id": "db-001"}
        assert page["archived"] is False
        assert page["in_trash"] is False
        assert "created_time" in page
        assert "last_edited_time" in page
        assert "url" in page

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "page"
        assert delta.operation == "create"

    async def test_pages_create_with_children(self, notion_pack):
        """pages.create with children creates page + block deltas."""
        proposal = await notion_pack.handle_action(
            ToolName("pages.create"),
            {
                "parent": {"page_id": "page-001"},
                "properties": {
                    "title": {
                        "type": "title",
                        "title": [
                            {"type": "text", "text": {"content": "Sub Page"}}
                        ],
                    },
                },
                "children": [
                    {
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {"type": "text", "text": {"content": "Hello world"}}
                            ]
                        },
                    },
                    {
                        "type": "heading_1",
                        "heading_1": {
                            "rich_text": [
                                {"type": "text", "text": {"content": "Section 1"}}
                            ]
                        },
                    },
                ],
            },
            {},
        )
        # 1 page delta + 2 block deltas
        assert len(proposal.proposed_state_deltas) == 3
        assert proposal.proposed_state_deltas[0].entity_type == "page"
        assert proposal.proposed_state_deltas[1].entity_type == "block"
        assert proposal.proposed_state_deltas[2].entity_type == "block"
        assert proposal.proposed_state_deltas[1].fields["type"] == "paragraph"
        assert proposal.proposed_state_deltas[2].fields["type"] == "heading_1"

    async def test_pages_create_with_icon_and_cover(self, notion_pack):
        """pages.create passes icon and cover through to the page entity."""
        proposal = await notion_pack.handle_action(
            ToolName("pages.create"),
            {
                "parent": {"database_id": "db-001"},
                "properties": {},
                "icon": {"type": "emoji", "emoji": "\ud83d\ude80"},
                "cover": {
                    "type": "external",
                    "external": {"url": "https://example.com/cover.png"},
                },
            },
            {},
        )
        page = proposal.response_body
        assert page["icon"] == {"type": "emoji", "emoji": "\ud83d\ude80"}
        assert page["cover"]["external"]["url"] == "https://example.com/cover.png"

    async def test_pages_retrieve(self, notion_pack, sample_state):
        """pages.retrieve returns a page by ID."""
        proposal = await notion_pack.handle_action(
            ToolName("pages.retrieve"),
            {"page_id": "page-001"},
            sample_state,
        )
        assert proposal.response_body["id"] == "page-001"
        assert proposal.response_body["object"] == "page"
        assert proposal.proposed_state_deltas == []

    async def test_pages_retrieve_not_found(self, notion_pack, sample_state):
        """pages.retrieve returns Notion error for nonexistent page."""
        proposal = await notion_pack.handle_action(
            ToolName("pages.retrieve"),
            {"page_id": "page-nonexistent"},
            sample_state,
        )
        assert proposal.response_body["object"] == "error"
        assert proposal.response_body["status"] == 404
        assert proposal.response_body["code"] == "object_not_found"

    async def test_pages_update_properties(self, notion_pack, sample_state):
        """pages.update changes properties and records previous_fields."""
        proposal = await notion_pack.handle_action(
            ToolName("pages.update"),
            {
                "page_id": "page-001",
                "properties": {
                    "Status": {
                        "type": "select",
                        "select": {"name": "Done", "color": "green"},
                    },
                },
            },
            sample_state,
        )
        assert isinstance(proposal, ResponseProposal)
        updated_page = proposal.response_body
        assert updated_page["properties"]["Status"]["select"]["name"] == "Done"
        assert "last_edited_time" in updated_page

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.operation == "update"
        assert delta.previous_fields is not None
        assert "properties" in delta.previous_fields

    async def test_pages_update_archive(self, notion_pack, sample_state):
        """pages.update with archived=True sets archived and in_trash."""
        proposal = await notion_pack.handle_action(
            ToolName("pages.update"),
            {"page_id": "page-002", "archived": True},
            sample_state,
        )
        updated_page = proposal.response_body
        assert updated_page["archived"] is True
        assert updated_page["in_trash"] is True

        delta = proposal.proposed_state_deltas[0]
        assert delta.fields["archived"] is True
        assert delta.fields["in_trash"] is True
        assert delta.previous_fields["archived"] is False

    async def test_pages_update_icon(self, notion_pack, sample_state):
        """pages.update can change the page icon."""
        proposal = await notion_pack.handle_action(
            ToolName("pages.update"),
            {
                "page_id": "page-001",
                "icon": {"type": "emoji", "emoji": "\u2705"},
            },
            sample_state,
        )
        updated_page = proposal.response_body
        assert updated_page["icon"] == {"type": "emoji", "emoji": "\u2705"}
        delta = proposal.proposed_state_deltas[0]
        assert "icon" in delta.fields
        assert "icon" in delta.previous_fields

    async def test_pages_update_not_found(self, notion_pack, sample_state):
        """pages.update returns Notion error for nonexistent page."""
        proposal = await notion_pack.handle_action(
            ToolName("pages.update"),
            {"page_id": "page-nonexistent", "archived": True},
            sample_state,
        )
        assert proposal.response_body["object"] == "error"
        assert proposal.response_body["status"] == 404
        assert proposal.response_body["code"] == "object_not_found"

    # --- Databases ---

    async def test_databases_create(self, notion_pack):
        """databases.create creates a database under a parent page."""
        proposal = await notion_pack.handle_action(
            ToolName("databases.create"),
            {
                "parent": {"type": "page_id", "page_id": "page-001"},
                "title": [
                    {"type": "text", "text": {"content": "Bug Tracker"}}
                ],
                "properties": {
                    "Name": {"type": "title", "title": {}},
                    "Priority": {
                        "type": "select",
                        "select": {
                            "options": [
                                {"name": "High", "color": "red"},
                                {"name": "Low", "color": "gray"},
                            ]
                        },
                    },
                },
            },
            {},
        )
        assert isinstance(proposal, ResponseProposal)
        db = proposal.response_body
        assert db["object"] == "database"
        assert "id" in db
        assert db["archived"] is False
        assert db["is_inline"] is False
        assert "created_time" in db
        assert "url" in db

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "database"
        assert delta.operation == "create"

    async def test_databases_create_inline(self, notion_pack):
        """databases.create with is_inline=True sets the flag."""
        proposal = await notion_pack.handle_action(
            ToolName("databases.create"),
            {
                "parent": {"type": "page_id", "page_id": "page-001"},
                "title": [{"type": "text", "text": {"content": "Inline DB"}}],
                "properties": {"Name": {"type": "title", "title": {}}},
                "is_inline": True,
            },
            {},
        )
        assert proposal.response_body["is_inline"] is True

    async def test_databases_retrieve(self, notion_pack, sample_state):
        """databases.retrieve returns a database by ID."""
        proposal = await notion_pack.handle_action(
            ToolName("databases.retrieve"),
            {"database_id": "db-001"},
            sample_state,
        )
        assert proposal.response_body["id"] == "db-001"
        assert proposal.response_body["object"] == "database"
        assert proposal.proposed_state_deltas == []

    async def test_databases_retrieve_not_found(self, notion_pack, sample_state):
        """databases.retrieve returns Notion error for nonexistent database."""
        proposal = await notion_pack.handle_action(
            ToolName("databases.retrieve"),
            {"database_id": "db-nonexistent"},
            sample_state,
        )
        assert proposal.response_body["object"] == "error"
        assert proposal.response_body["status"] == 404
        assert proposal.response_body["code"] == "object_not_found"

    async def test_databases_query_all(self, notion_pack, sample_state):
        """databases.query returns all non-archived pages in the database."""
        proposal = await notion_pack.handle_action(
            ToolName("databases.query"),
            {"database_id": "db-001"},
            sample_state,
        )
        body = proposal.response_body
        assert body["object"] == "list"
        assert len(body["results"]) == 2
        ids = {p["id"] for p in body["results"]}
        assert ids == {"page-001", "page-002"}
        assert proposal.proposed_state_deltas == []

    async def test_databases_query_with_filter(self, notion_pack, sample_state):
        """databases.query with a select filter narrows results."""
        proposal = await notion_pack.handle_action(
            ToolName("databases.query"),
            {
                "database_id": "db-001",
                "filter": {
                    "property": "Status",
                    "select": {"equals": "In Progress"},
                },
            },
            sample_state,
        )
        results = proposal.response_body["results"]
        assert len(results) == 1
        assert results[0]["id"] == "page-001"

    async def test_databases_query_with_title_contains_filter(self, notion_pack, sample_state):
        """databases.query with a title contains filter works."""
        proposal = await notion_pack.handle_action(
            ToolName("databases.query"),
            {
                "database_id": "db-001",
                "filter": {
                    "property": "Name",
                    "title": {"contains": "Sprint"},
                },
            },
            sample_state,
        )
        results = proposal.response_body["results"]
        assert len(results) == 1
        assert results[0]["id"] == "page-002"

    async def test_databases_query_not_found(self, notion_pack, sample_state):
        """databases.query returns error for nonexistent database."""
        proposal = await notion_pack.handle_action(
            ToolName("databases.query"),
            {"database_id": "db-nonexistent"},
            sample_state,
        )
        assert proposal.response_body["object"] == "error"
        assert proposal.response_body["code"] == "object_not_found"

    async def test_databases_query_pagination(self, notion_pack, sample_state):
        """databases.query respects page_size for cursor pagination."""
        proposal = await notion_pack.handle_action(
            ToolName("databases.query"),
            {"database_id": "db-001", "page_size": 1},
            sample_state,
        )
        body = proposal.response_body
        assert len(body["results"]) == 1
        assert body["has_more"] is True
        assert body["next_cursor"] is not None

        # The cursor-based pagination uses the last returned item's ID
        # as the start_cursor for the next page (handler starts after it).
        last_returned_id = body["results"][-1]["id"]
        proposal2 = await notion_pack.handle_action(
            ToolName("databases.query"),
            {
                "database_id": "db-001",
                "page_size": 1,
                "start_cursor": last_returned_id,
            },
            sample_state,
        )
        body2 = proposal2.response_body
        assert len(body2["results"]) == 1
        assert body2["has_more"] is False
        assert body2["next_cursor"] is None
        # The two pages together should cover all database pages
        all_ids = {body["results"][0]["id"], body2["results"][0]["id"]}
        assert all_ids == {"page-001", "page-002"}

    async def test_databases_query_empty_result(self, notion_pack, sample_state):
        """databases.query for a database with no pages returns empty list."""
        proposal = await notion_pack.handle_action(
            ToolName("databases.query"),
            {"database_id": "db-002"},
            sample_state,
        )
        assert proposal.response_body["results"] == []
        assert proposal.response_body["has_more"] is False

    # --- Blocks ---

    async def test_blocks_children_list(self, notion_pack, sample_state):
        """blocks.children.list returns child blocks of a page."""
        proposal = await notion_pack.handle_action(
            ToolName("blocks.children.list"),
            {"block_id": "page-001"},
            sample_state,
        )
        body = proposal.response_body
        assert body["object"] == "list"
        # page-001 has block-001, block-002, block-003
        assert len(body["results"]) == 3
        assert proposal.proposed_state_deltas == []

    async def test_blocks_children_list_nested(self, notion_pack, sample_state):
        """blocks.children.list returns child blocks of another block."""
        proposal = await notion_pack.handle_action(
            ToolName("blocks.children.list"),
            {"block_id": "block-001"},
            sample_state,
        )
        body = proposal.response_body
        # block-001 has block-005 as child
        assert len(body["results"]) == 1
        assert body["results"][0]["id"] == "block-005"

    async def test_blocks_children_list_empty(self, notion_pack, sample_state):
        """blocks.children.list returns empty for block with no children."""
        proposal = await notion_pack.handle_action(
            ToolName("blocks.children.list"),
            {"block_id": "block-003"},
            sample_state,
        )
        assert proposal.response_body["results"] == []
        assert proposal.response_body["has_more"] is False

    async def test_blocks_children_append(self, notion_pack, sample_state):
        """blocks.children.append creates new blocks under a page."""
        proposal = await notion_pack.handle_action(
            ToolName("blocks.children.append"),
            {
                "block_id": "page-002",
                "children": [
                    {
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {"type": "text", "text": {"content": "New paragraph"}}
                            ]
                        },
                    },
                ],
            },
            sample_state,
        )
        assert isinstance(proposal, ResponseProposal)
        body = proposal.response_body
        assert body["object"] == "list"
        assert len(body["results"]) == 1
        assert body["results"][0]["type"] == "paragraph"

        # One delta for the new block (parent is a page, no has_children update)
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "block"
        assert delta.operation == "create"
        assert delta.fields["parent"]["page_id"] == "page-002"

    async def test_blocks_children_append_to_block(self, notion_pack, sample_state):
        """blocks.children.append to a block sets block_id parent and updates has_children."""
        # block-003 has has_children=False
        proposal = await notion_pack.handle_action(
            ToolName("blocks.children.append"),
            {
                "block_id": "block-003",
                "children": [
                    {
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {"type": "text", "text": {"content": "Nested"}}
                            ]
                        },
                    },
                ],
            },
            sample_state,
        )
        # 1 create delta for new block + 1 update delta for has_children
        assert len(proposal.proposed_state_deltas) == 2
        create_delta = proposal.proposed_state_deltas[0]
        update_delta = proposal.proposed_state_deltas[1]
        assert create_delta.operation == "create"
        assert create_delta.fields["parent"]["type"] == "block_id"
        assert create_delta.fields["parent"]["block_id"] == "block-003"
        assert update_delta.operation == "update"
        assert update_delta.fields["has_children"] is True
        assert update_delta.previous_fields["has_children"] is False

    async def test_blocks_retrieve(self, notion_pack, sample_state):
        """blocks.retrieve returns a block by ID."""
        proposal = await notion_pack.handle_action(
            ToolName("blocks.retrieve"),
            {"block_id": "block-002"},
            sample_state,
        )
        assert proposal.response_body["id"] == "block-002"
        assert proposal.response_body["type"] == "heading_1"
        assert proposal.proposed_state_deltas == []

    async def test_blocks_retrieve_not_found(self, notion_pack, sample_state):
        """blocks.retrieve returns Notion error for nonexistent block."""
        proposal = await notion_pack.handle_action(
            ToolName("blocks.retrieve"),
            {"block_id": "block-nonexistent"},
            sample_state,
        )
        assert proposal.response_body["object"] == "error"
        assert proposal.response_body["status"] == 404
        assert proposal.response_body["code"] == "object_not_found"

    async def test_blocks_delete(self, notion_pack, sample_state):
        """blocks.delete archives a block (soft delete)."""
        proposal = await notion_pack.handle_action(
            ToolName("blocks.delete"),
            {"block_id": "block-003"},
            sample_state,
        )
        assert isinstance(proposal, ResponseProposal)
        body = proposal.response_body
        assert body["archived"] is True
        assert body["in_trash"] is True
        assert body["id"] == "block-003"

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "block"
        assert delta.operation == "update"
        assert delta.fields["archived"] is True
        assert delta.fields["in_trash"] is True
        assert delta.previous_fields["archived"] is False
        assert delta.previous_fields["in_trash"] is False

    async def test_blocks_delete_not_found(self, notion_pack, sample_state):
        """blocks.delete returns Notion error for nonexistent block."""
        proposal = await notion_pack.handle_action(
            ToolName("blocks.delete"),
            {"block_id": "block-nonexistent"},
            sample_state,
        )
        assert proposal.response_body["object"] == "error"
        assert proposal.response_body["code"] == "object_not_found"

    # --- Users ---

    async def test_users_list(self, notion_pack, sample_state):
        """users.list returns all users in the workspace."""
        proposal = await notion_pack.handle_action(
            ToolName("users.list"),
            {},
            sample_state,
        )
        body = proposal.response_body
        assert body["object"] == "list"
        assert len(body["results"]) == 2
        assert proposal.proposed_state_deltas == []

    async def test_users_list_empty(self, notion_pack):
        """users.list returns empty list from empty state."""
        proposal = await notion_pack.handle_action(
            ToolName("users.list"),
            {},
            {},
        )
        assert proposal.response_body["results"] == []
        assert proposal.response_body["has_more"] is False

    async def test_users_me_returns_bot(self, notion_pack, sample_state):
        """users.me returns the bot user."""
        proposal = await notion_pack.handle_action(
            ToolName("users.me"),
            {},
            sample_state,
        )
        body = proposal.response_body
        assert body["type"] == "bot"
        assert body["id"] == "user-002"
        assert body["name"] == "Integration Bot"
        assert proposal.proposed_state_deltas == []

    async def test_users_me_fallback_to_first(self, notion_pack):
        """users.me falls back to first user when no bot exists."""
        state = {
            "users": [
                {
                    "id": "user-only",
                    "object": "user",
                    "type": "person",
                    "name": "Only Person",
                },
            ],
        }
        proposal = await notion_pack.handle_action(
            ToolName("users.me"),
            {},
            state,
        )
        assert proposal.response_body["id"] == "user-only"

    async def test_users_me_no_users(self, notion_pack):
        """users.me returns error when no users exist."""
        proposal = await notion_pack.handle_action(
            ToolName("users.me"),
            {},
            {},
        )
        assert proposal.response_body["object"] == "error"
        assert proposal.response_body["code"] == "object_not_found"

    # --- Search ---

    async def test_search_by_title(self, notion_pack, sample_state):
        """search finds pages and databases by title text."""
        proposal = await notion_pack.handle_action(
            ToolName("search"),
            {"query": "Roadmap"},
            sample_state,
        )
        results = proposal.response_body["results"]
        assert len(results) >= 1
        ids = {r["id"] for r in results}
        assert "page-001" in ids
        assert proposal.proposed_state_deltas == []

    async def test_search_filter_pages_only(self, notion_pack, sample_state):
        """search with filter value=page excludes databases."""
        proposal = await notion_pack.handle_action(
            ToolName("search"),
            {
                "query": "",
                "filter": {"value": "page", "property": "object"},
            },
            sample_state,
        )
        results = proposal.response_body["results"]
        for r in results:
            assert r["object"] == "page"

    async def test_search_filter_databases_only(self, notion_pack, sample_state):
        """search with filter value=database excludes pages."""
        proposal = await notion_pack.handle_action(
            ToolName("search"),
            {
                "query": "",
                "filter": {"value": "database", "property": "object"},
            },
            sample_state,
        )
        results = proposal.response_body["results"]
        assert len(results) == 2
        for r in results:
            assert r["object"] == "database"

    async def test_search_no_results(self, notion_pack, sample_state):
        """search returns empty for non-matching query."""
        proposal = await notion_pack.handle_action(
            ToolName("search"),
            {"query": "zzz_nonexistent_query_zzz"},
            sample_state,
        )
        assert proposal.response_body["results"] == []
        assert proposal.response_body["has_more"] is False

    async def test_search_case_insensitive(self, notion_pack, sample_state):
        """search is case-insensitive."""
        proposal = await notion_pack.handle_action(
            ToolName("search"),
            {"query": "knowledge base"},
            sample_state,
        )
        results = proposal.response_body["results"]
        ids = {r["id"] for r in results}
        assert "db-002" in ids

    # --- Comments ---

    async def test_comments_create_on_page(self, notion_pack, sample_state):
        """comments.create with parent.page_id creates a new discussion."""
        proposal = await notion_pack.handle_action(
            ToolName("comments.create"),
            {
                "parent": {"page_id": "page-001"},
                "rich_text": [
                    {"type": "text", "text": {"content": "New comment here"}}
                ],
            },
            sample_state,
        )
        assert isinstance(proposal, ResponseProposal)
        comment = proposal.response_body
        assert comment["object"] == "comment"
        assert "id" in comment
        assert "discussion_id" in comment
        assert comment["parent"]["page_id"] == "page-001"
        assert len(comment["rich_text"]) == 1

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "comment"
        assert delta.operation == "create"

    async def test_comments_create_in_discussion(self, notion_pack, sample_state):
        """comments.create with discussion_id adds to existing thread."""
        proposal = await notion_pack.handle_action(
            ToolName("comments.create"),
            {
                "discussion_id": "disc-001",
                "rich_text": [
                    {"type": "text", "text": {"content": "Reply in thread"}}
                ],
            },
            sample_state,
        )
        comment = proposal.response_body
        assert comment["discussion_id"] == "disc-001"
        # Should resolve the parent from the existing discussion
        assert comment["parent"]["page_id"] == "page-001"

    async def test_comments_create_requires_parent_or_discussion(self, notion_pack, sample_state):
        """comments.create without parent or discussion_id returns validation error."""
        proposal = await notion_pack.handle_action(
            ToolName("comments.create"),
            {
                "rich_text": [
                    {"type": "text", "text": {"content": "Orphan comment"}}
                ],
            },
            sample_state,
        )
        assert proposal.response_body["object"] == "error"
        assert proposal.response_body["status"] == 400
        assert proposal.response_body["code"] == "validation_error"

    async def test_comments_list(self, notion_pack, sample_state):
        """comments.list returns comments for a page."""
        proposal = await notion_pack.handle_action(
            ToolName("comments.list"),
            {"block_id": "page-001"},
            sample_state,
        )
        body = proposal.response_body
        assert body["object"] == "list"
        assert len(body["results"]) == 2
        assert proposal.proposed_state_deltas == []

    async def test_comments_list_empty(self, notion_pack, sample_state):
        """comments.list returns empty for page with no comments."""
        proposal = await notion_pack.handle_action(
            ToolName("comments.list"),
            {"block_id": "page-002"},
            sample_state,
        )
        assert proposal.response_body["results"] == []
        assert proposal.response_body["has_more"] is False


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestNotionPackValidation:
    def test_page_schema_validates(self, notion_pack):
        """Valid page entity passes SchemaValidator."""
        validator = SchemaValidator()
        schemas = notion_pack.get_entity_schemas()

        valid_page = {
            "id": "page-xyz",
            "object": "page",
            "parent": {"type": "workspace", "workspace": True},
            "properties": {},
            "created_time": "2026-01-01T00:00:00+00:00",
            "last_edited_time": "2026-01-01T00:00:00+00:00",
        }
        result = validator.validate_entity(valid_page, schemas["page"])
        assert result.valid, f"Page validation errors: {result.errors}"

    def test_database_schema_validates(self, notion_pack):
        """Valid database entity passes SchemaValidator."""
        validator = SchemaValidator()
        schemas = notion_pack.get_entity_schemas()

        valid_db = {
            "id": "db-xyz",
            "object": "database",
            "title": [{"type": "text", "text": {"content": "Test DB"}}],
            "properties": {},
            "created_time": "2026-01-01T00:00:00+00:00",
            "last_edited_time": "2026-01-01T00:00:00+00:00",
        }
        result = validator.validate_entity(valid_db, schemas["database"])
        assert result.valid, f"Database validation errors: {result.errors}"

    def test_block_schema_validates(self, notion_pack):
        """Valid block entity passes SchemaValidator."""
        validator = SchemaValidator()
        schemas = notion_pack.get_entity_schemas()

        valid_block = {
            "id": "block-xyz",
            "object": "block",
            "type": "paragraph",
            "created_time": "2026-01-01T00:00:00+00:00",
            "last_edited_time": "2026-01-01T00:00:00+00:00",
        }
        result = validator.validate_entity(valid_block, schemas["block"])
        assert result.valid, f"Block validation errors: {result.errors}"

    def test_user_schema_validates(self, notion_pack):
        """Valid user entity passes SchemaValidator."""
        validator = SchemaValidator()
        schemas = notion_pack.get_entity_schemas()

        valid_user = {
            "id": "user-xyz",
            "object": "user",
            "name": "Test User",
        }
        result = validator.validate_entity(valid_user, schemas["user"])
        assert result.valid, f"User validation errors: {result.errors}"

    def test_comment_schema_validates(self, notion_pack):
        """Valid comment entity passes SchemaValidator."""
        validator = SchemaValidator()
        schemas = notion_pack.get_entity_schemas()

        valid_comment = {
            "id": "comment-xyz",
            "object": "comment",
            "parent": {"type": "page_id", "page_id": "page-001"},
            "rich_text": [
                {"type": "text", "text": {"content": "Hello"}, "plain_text": "Hello"}
            ],
            "created_time": "2026-01-01T00:00:00+00:00",
        }
        result = validator.validate_entity(valid_comment, schemas["comment"])
        assert result.valid, f"Comment validation errors: {result.errors}"

    def test_state_machine_valid_transition_active_to_archived(self, notion_pack):
        """active -> archived is a valid transition for page/database/block."""
        sm_validator = StateMachineValidator()
        for entity_type in ("page", "database", "block"):
            sm = notion_pack.get_state_machines()[entity_type]
            result = sm_validator.validate_transition("active", "archived", sm)
            assert result.valid, f"{entity_type}: active -> archived should be valid"

    def test_state_machine_invalid_transition_archived_to_active(self, notion_pack):
        """archived -> active is NOT a valid transition (archiving is one-way)."""
        sm_validator = StateMachineValidator()
        for entity_type in ("page", "database", "block"):
            sm = notion_pack.get_state_machines()[entity_type]
            result = sm_validator.validate_transition("archived", "active", sm)
            assert not result.valid, f"{entity_type}: archived -> active should be invalid"

    def test_archived_states_complete(self):
        """ARCHIVED_STATES matches all keys in ARCHIVED_TRANSITIONS."""
        assert set(ARCHIVED_STATES) == set(ARCHIVED_TRANSITIONS.keys())

    def test_all_transitions_reference_valid_states(self):
        """Every target state in ARCHIVED_TRANSITIONS is itself a valid state."""
        valid = set(ARCHIVED_STATES)
        for source, targets in ARCHIVED_TRANSITIONS.items():
            for target in targets:
                assert target in valid, (
                    f"Transition {source} -> {target}: target is not a valid state"
                )

    def test_page_schema_identity_field(self):
        """PAGE_ENTITY_SCHEMA x-volnix-identity is 'id'."""
        assert PAGE_ENTITY_SCHEMA["x-volnix-identity"] == "id"

    def test_database_schema_identity_field(self):
        """DATABASE_ENTITY_SCHEMA x-volnix-identity is 'id'."""
        assert DATABASE_ENTITY_SCHEMA["x-volnix-identity"] == "id"

    def test_block_schema_identity_field(self):
        """BLOCK_ENTITY_SCHEMA x-volnix-identity is 'id'."""
        assert BLOCK_ENTITY_SCHEMA["x-volnix-identity"] == "id"

    def test_user_schema_identity_field(self):
        """USER_ENTITY_SCHEMA x-volnix-identity is 'id'."""
        assert USER_ENTITY_SCHEMA["x-volnix-identity"] == "id"

    def test_comment_schema_identity_field(self):
        """COMMENT_ENTITY_SCHEMA x-volnix-identity is 'id'."""
        assert COMMENT_ENTITY_SCHEMA["x-volnix-identity"] == "id"
