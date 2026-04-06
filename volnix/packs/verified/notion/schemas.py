"""Entity schemas and tool definitions for the Notion service pack.

Pure data -- no logic, no imports beyond stdlib.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------

PAGE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "object", "parent", "properties", "created_time", "last_edited_time"],
    "properties": {
        "id": {"type": "string"},
        "object": {"type": "string", "enum": ["page"]},
        "created_time": {"type": "string"},
        "last_edited_time": {"type": "string"},
        "created_by": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "id": {"type": "string"},
            },
        },
        "last_edited_by": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "id": {"type": "string"},
            },
        },
        "parent": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["database_id", "page_id", "workspace"]},
                "database_id": {"type": "string"},
                "page_id": {"type": "string"},
                "workspace": {"type": "boolean"},
            },
        },
        "archived": {"type": "boolean", "default": False},
        "in_trash": {"type": "boolean", "default": False},
        "properties": {"type": "object"},
        "icon": {
            "type": ["object", "null"],
            "properties": {
                "type": {"type": "string"},
                "emoji": {"type": "string"},
            },
        },
        "cover": {
            "type": ["object", "null"],
            "properties": {
                "type": {"type": "string"},
                "external": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                },
            },
        },
        "url": {"type": "string"},
        "public_url": {"type": ["string", "null"]},
    },
}

DATABASE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "object", "title", "properties", "created_time", "last_edited_time"],
    "properties": {
        "id": {"type": "string"},
        "object": {"type": "string", "enum": ["database"]},
        "created_time": {"type": "string"},
        "last_edited_time": {"type": "string"},
        "created_by": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "id": {"type": "string"},
            },
        },
        "last_edited_by": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "id": {"type": "string"},
            },
        },
        "title": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "text": {
                        "type": "object",
                        "properties": {"content": {"type": "string"}},
                    },
                    "plain_text": {"type": "string"},
                },
            },
        },
        "description": {
            "type": "array",
            "items": {"type": "object"},
        },
        "parent": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["page_id", "workspace"]},
                "page_id": {"type": "string"},
                "workspace": {"type": "boolean"},
            },
        },
        "archived": {"type": "boolean", "default": False},
        "in_trash": {"type": "boolean", "default": False},
        "is_inline": {"type": "boolean", "default": False},
        "properties": {"type": "object"},
        "icon": {"type": ["object", "null"]},
        "cover": {"type": ["object", "null"]},
        "url": {"type": "string"},
        "public_url": {"type": ["string", "null"]},
    },
}

BLOCK_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "object", "type", "created_time", "last_edited_time"],
    "properties": {
        "id": {"type": "string"},
        "object": {"type": "string", "enum": ["block"]},
        "type": {
            "type": "string",
            "enum": [
                "paragraph",
                "heading_1",
                "heading_2",
                "heading_3",
                "bulleted_list_item",
                "numbered_list_item",
                "to_do",
                "toggle",
                "child_page",
                "child_database",
                "code",
                "embed",
                "image",
                "video",
                "file",
                "pdf",
                "bookmark",
                "callout",
                "quote",
                "divider",
                "table_of_contents",
                "column",
                "column_list",
                "synced_block",
                "template",
                "table",
                "table_row",
            ],
        },
        "parent": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["page_id", "block_id"]},
                "page_id": {"type": "string"},
                "block_id": {"type": "string"},
            },
        },
        "created_time": {"type": "string"},
        "last_edited_time": {"type": "string"},
        "created_by": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "id": {"type": "string"},
            },
        },
        "last_edited_by": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "id": {"type": "string"},
            },
        },
        "archived": {"type": "boolean", "default": False},
        "in_trash": {"type": "boolean", "default": False},
        "has_children": {"type": "boolean", "default": False},
    },
}

USER_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "object", "name"],
    "properties": {
        "id": {"type": "string"},
        "object": {"type": "string", "enum": ["user"]},
        "type": {
            "type": "string",
            "enum": ["person", "bot"],
        },
        "name": {"type": "string"},
        "avatar_url": {"type": ["string", "null"]},
        "person": {
            "type": "object",
            "properties": {
                "email": {"type": "string"},
            },
        },
        "bot": {
            "type": "object",
            "properties": {
                "owner": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "workspace": {"type": "boolean"},
                    },
                },
                "workspace_name": {"type": "string"},
            },
        },
    },
}

COMMENT_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "object", "parent", "rich_text", "created_time"],
    "properties": {
        "id": {"type": "string"},
        "object": {"type": "string", "enum": ["comment"]},
        "parent": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["page_id", "block_id"]},
                "page_id": {"type": "string"},
                "block_id": {"type": "string"},
            },
        },
        "discussion_id": {"type": "string"},
        "rich_text": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "text": {
                        "type": "object",
                        "properties": {"content": {"type": "string"}},
                    },
                    "plain_text": {"type": "string"},
                },
            },
        },
        "created_time": {"type": "string"},
        "last_edited_time": {"type": "string"},
        "created_by": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "id": {"type": "string"},
            },
        },
    },
}

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

NOTION_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "pages.create",
        "pack": "notion",
        "description": "Create a new page in a database or as a child of another page.",
        "http_path": "/v1/pages",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["parent", "properties"],
            "properties": {
                "parent": {
                    "type": "object",
                    "description": "Parent object. Must contain either database_id or page_id.",
                    "properties": {
                        "database_id": {
                            "type": "string",
                            "description": "ID of the parent database.",
                        },
                        "page_id": {
                            "type": "string",
                            "description": "ID of the parent page.",
                        },
                    },
                },
                "properties": {
                    "type": "object",
                    "description": "Property values for the page. Keys are property names.",
                },
                "children": {
                    "type": "array",
                    "description": "Block objects to append as page content.",
                    "items": {"type": "object"},
                },
                "icon": {
                    "type": "object",
                    "description": "Page icon (emoji or external URL).",
                    "properties": {
                        "type": {"type": "string", "enum": ["emoji", "external"]},
                        "emoji": {"type": "string"},
                        "external": {
                            "type": "object",
                            "properties": {"url": {"type": "string"}},
                        },
                    },
                },
                "cover": {
                    "type": "object",
                    "description": "Page cover image.",
                    "properties": {
                        "type": {"type": "string", "enum": ["external"]},
                        "external": {
                            "type": "object",
                            "properties": {"url": {"type": "string"}},
                        },
                    },
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "id": {"type": "string"},
            },
        },
    },
    {
        "name": "pages.retrieve",
        "pack": "notion",
        "description": "Retrieve a page by its ID.",
        "http_path": "/v1/pages/{page_id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["page_id"],
            "properties": {
                "page_id": {
                    "type": "string",
                    "description": "The ID of the page to retrieve.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "id": {"type": "string"},
            },
        },
    },
    {
        "name": "pages.update",
        "pack": "notion",
        "description": "Update page properties, icon, cover, or archive status.",
        "http_path": "/v1/pages/{page_id}",
        "http_method": "PATCH",
        "parameters": {
            "type": "object",
            "required": ["page_id"],
            "properties": {
                "page_id": {
                    "type": "string",
                    "description": "The ID of the page to update.",
                },
                "properties": {
                    "type": "object",
                    "description": "Property values to update.",
                },
                "archived": {
                    "type": "boolean",
                    "description": "Set to true to archive the page.",
                },
                "icon": {
                    "type": "object",
                    "description": "Updated page icon.",
                    "properties": {
                        "type": {"type": "string"},
                        "emoji": {"type": "string"},
                    },
                },
                "cover": {
                    "type": "object",
                    "description": "Updated page cover image.",
                    "properties": {
                        "type": {"type": "string"},
                        "external": {
                            "type": "object",
                            "properties": {"url": {"type": "string"}},
                        },
                    },
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "id": {"type": "string"},
            },
        },
    },
    {
        "name": "databases.create",
        "pack": "notion",
        "description": "Create a new database as a child of a page.",
        "http_path": "/v1/databases",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["parent", "title", "properties"],
            "properties": {
                "parent": {
                    "type": "object",
                    "description": "Parent page for the database.",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["page_id"],
                        },
                        "page_id": {
                            "type": "string",
                            "description": "ID of the parent page.",
                        },
                    },
                },
                "title": {
                    "type": "array",
                    "description": "Rich text array for the database title.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "text": {
                                "type": "object",
                                "properties": {"content": {"type": "string"}},
                            },
                        },
                    },
                },
                "properties": {
                    "type": "object",
                    "description": "Property schema definitions for the database.",
                },
                "is_inline": {
                    "type": "boolean",
                    "description": "Whether the database is inline.",
                },
                "icon": {
                    "type": "object",
                    "description": "Database icon.",
                    "properties": {
                        "type": {"type": "string"},
                        "emoji": {"type": "string"},
                    },
                },
                "cover": {
                    "type": "object",
                    "description": "Database cover image.",
                    "properties": {
                        "type": {"type": "string"},
                        "external": {
                            "type": "object",
                            "properties": {"url": {"type": "string"}},
                        },
                    },
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "id": {"type": "string"},
            },
        },
    },
    {
        "name": "databases.retrieve",
        "pack": "notion",
        "description": "Retrieve a database by its ID.",
        "http_path": "/v1/databases/{database_id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["database_id"],
            "properties": {
                "database_id": {
                    "type": "string",
                    "description": "The ID of the database to retrieve.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "id": {"type": "string"},
            },
        },
    },
    {
        "name": "databases.query",
        "pack": "notion",
        "description": "Query a database with optional filters and sorts.",
        "http_path": "/v1/databases/{database_id}/query",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["database_id"],
            "properties": {
                "database_id": {
                    "type": "string",
                    "description": "The ID of the database to query.",
                },
                "filter": {
                    "type": "object",
                    "description": (
                        "Filter conditions. Supports property filters"
                        " and compound (and/or) filters."
                    ),
                    "properties": {
                        "and": {
                            "type": "array",
                            "description": "Array of filters combined with AND.",
                            "items": {"type": "object"},
                        },
                        "or": {
                            "type": "array",
                            "description": "Array of filters combined with OR.",
                            "items": {"type": "object"},
                        },
                        "property": {
                            "type": "string",
                            "description": "Property name to filter on.",
                        },
                        "title": {"type": "object"},
                        "rich_text": {"type": "object"},
                        "number": {"type": "object"},
                        "checkbox": {"type": "object"},
                        "select": {"type": "object"},
                        "multi_select": {"type": "object"},
                        "date": {"type": "object"},
                        "status": {"type": "object"},
                    },
                },
                "sorts": {
                    "type": "array",
                    "description": "Sort criteria.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "property": {"type": "string"},
                            "timestamp": {
                                "type": "string",
                                "enum": ["created_time", "last_edited_time"],
                            },
                            "direction": {
                                "type": "string",
                                "enum": ["ascending", "descending"],
                            },
                        },
                    },
                },
                "start_cursor": {
                    "type": "string",
                    "description": "Cursor for pagination.",
                },
                "page_size": {
                    "type": "integer",
                    "description": "Number of results per page (max 100).",
                    "default": 100,
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "object": {"type": "string", "enum": ["list"]},
                "results": {"type": "array"},
                "has_more": {"type": "boolean"},
                "next_cursor": {"type": ["string", "null"]},
            },
        },
    },
    {
        "name": "blocks.children.list",
        "pack": "notion",
        "description": "List all child blocks of a given block or page.",
        "http_path": "/v1/blocks/{block_id}/children",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["block_id"],
            "properties": {
                "block_id": {
                    "type": "string",
                    "description": "The ID of the block or page whose children to list.",
                },
                "start_cursor": {
                    "type": "string",
                    "description": "Cursor for pagination.",
                },
                "page_size": {
                    "type": "integer",
                    "description": "Number of results per page (max 100).",
                    "default": 100,
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "object": {"type": "string", "enum": ["list"]},
                "results": {"type": "array"},
                "has_more": {"type": "boolean"},
                "next_cursor": {"type": ["string", "null"]},
            },
        },
    },
    {
        "name": "blocks.children.append",
        "pack": "notion",
        "description": "Append new child blocks to a given block or page.",
        "http_path": "/v1/blocks/{block_id}/children",
        "http_method": "PATCH",
        "parameters": {
            "type": "object",
            "required": ["block_id", "children"],
            "properties": {
                "block_id": {
                    "type": "string",
                    "description": "The ID of the block or page to append children to.",
                },
                "children": {
                    "type": "array",
                    "description": "Array of block objects to append.",
                    "items": {"type": "object"},
                },
                "after": {
                    "type": "string",
                    "description": "ID of the block to append after.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "object": {"type": "string", "enum": ["list"]},
                "results": {"type": "array"},
            },
        },
    },
    {
        "name": "blocks.retrieve",
        "pack": "notion",
        "description": "Retrieve a block by its ID.",
        "http_path": "/v1/blocks/{block_id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["block_id"],
            "properties": {
                "block_id": {
                    "type": "string",
                    "description": "The ID of the block to retrieve.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "id": {"type": "string"},
            },
        },
    },
    {
        "name": "blocks.delete",
        "pack": "notion",
        "description": "Archive (soft-delete) a block by setting archived to true.",
        "http_path": "/v1/blocks/{block_id}",
        "http_method": "DELETE",
        "parameters": {
            "type": "object",
            "required": ["block_id"],
            "properties": {
                "block_id": {
                    "type": "string",
                    "description": "The ID of the block to delete.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "id": {"type": "string"},
            },
        },
    },
    {
        "name": "users.list",
        "pack": "notion",
        "description": "List all users in the workspace.",
        "http_path": "/v1/users",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "start_cursor": {
                    "type": "string",
                    "description": "Cursor for pagination.",
                },
                "page_size": {
                    "type": "integer",
                    "description": "Number of results per page (max 100).",
                    "default": 100,
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "object": {"type": "string", "enum": ["list"]},
                "results": {"type": "array"},
                "has_more": {"type": "boolean"},
                "next_cursor": {"type": ["string", "null"]},
            },
        },
    },
    {
        "name": "users.me",
        "pack": "notion",
        "description": "Retrieve the bot user associated with the current token.",
        "http_path": "/v1/users/me",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {},
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "id": {"type": "string"},
            },
        },
    },
    {
        "name": "search",
        "pack": "notion",
        "description": "Search pages and databases by title.",
        "http_path": "/v1/search",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search for in page and database titles.",
                },
                "filter": {
                    "type": "object",
                    "description": "Filter results by object type.",
                    "properties": {
                        "value": {
                            "type": "string",
                            "enum": ["page", "database"],
                            "description": "Object type to filter by.",
                        },
                        "property": {
                            "type": "string",
                            "enum": ["object"],
                            "description": "Must be 'object'.",
                        },
                    },
                },
                "sort": {
                    "type": "object",
                    "description": "Sort order for results.",
                    "properties": {
                        "direction": {
                            "type": "string",
                            "enum": ["ascending", "descending"],
                        },
                        "timestamp": {
                            "type": "string",
                            "enum": ["last_edited_time"],
                        },
                    },
                },
                "start_cursor": {
                    "type": "string",
                    "description": "Cursor for pagination.",
                },
                "page_size": {
                    "type": "integer",
                    "description": "Number of results per page (max 100).",
                    "default": 100,
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "object": {"type": "string", "enum": ["list"]},
                "results": {"type": "array"},
                "has_more": {"type": "boolean"},
                "next_cursor": {"type": ["string", "null"]},
            },
        },
    },
    {
        "name": "comments.create",
        "pack": "notion",
        "description": "Create a comment on a page or in an existing discussion thread.",
        "http_path": "/v1/comments",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["rich_text"],
            "properties": {
                "parent": {
                    "type": "object",
                    "description": (
                        "Parent page for a new discussion. Provide either parent or discussion_id."
                    ),
                    "properties": {
                        "page_id": {
                            "type": "string",
                            "description": "The ID of the parent page.",
                        },
                    },
                },
                "discussion_id": {
                    "type": "string",
                    "description": "ID of an existing discussion thread to add a comment to.",
                },
                "rich_text": {
                    "type": "array",
                    "description": "Rich text content for the comment.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "text": {
                                "type": "object",
                                "properties": {"content": {"type": "string"}},
                            },
                        },
                    },
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "id": {"type": "string"},
            },
        },
    },
    {
        "name": "comments.list",
        "pack": "notion",
        "description": "List comments on a page or block.",
        "http_path": "/v1/comments",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["block_id"],
            "properties": {
                "block_id": {
                    "type": "string",
                    "description": "The ID of the page or block whose comments to list.",
                },
                "start_cursor": {
                    "type": "string",
                    "description": "Cursor for pagination.",
                },
                "page_size": {
                    "type": "integer",
                    "description": "Number of results per page (max 100).",
                    "default": 100,
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "object": {"type": "string", "enum": ["list"]},
                "results": {"type": "array"},
                "has_more": {"type": "boolean"},
                "next_cursor": {"type": ["string", "null"]},
            },
        },
    },
]
