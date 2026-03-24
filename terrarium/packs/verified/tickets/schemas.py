"""Entity schemas and tool definitions for the tickets service pack.

Pure data -- no logic, no imports beyond stdlib.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------

TICKET_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "subject", "status", "requester_id", "created_at", "updated_at"],
    "properties": {
        "id": {"type": "string"},
        "subject": {"type": "string"},
        "description": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["new", "open", "pending", "hold", "solved", "closed"],
        },
        "priority": {
            "type": "string",
            "enum": ["urgent", "high", "normal", "low"],
        },
        "type": {
            "type": "string",
            "enum": ["problem", "incident", "question", "task"],
        },
        "assignee_id": {"type": "string", "x-terrarium-ref": "user"},
        "requester_id": {"type": "string", "x-terrarium-ref": "user"},
        "group_id": {"type": "string", "x-terrarium-ref": "group"},
        "organization_id": {"type": "string", "x-terrarium-ref": "organization"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "custom_fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": ["integer", "string"]},
                    "value": {},
                },
            },
        },
        "collaborator_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
        "follower_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
        "satisfaction_rating": {
            "type": "object",
            "properties": {
                "score": {"type": "string"},
                "comment": {"type": "string"},
            },
        },
        "problem_id": {"type": "string", "x-terrarium-ref": "ticket"},
        "external_id": {"type": "string"},
        "brand_id": {"type": "string"},
        "via": {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
            },
        },
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
        "due_at": {"type": ["string", "null"]},
    },
}

COMMENT_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "ticket_id", "author_id", "body", "created_at"],
    "properties": {
        "id": {"type": "string"},
        "ticket_id": {"type": "string", "x-terrarium-ref": "ticket"},
        "author_id": {"type": "string", "x-terrarium-ref": "user"},
        "body": {"type": "string"},
        "html_body": {"type": "string"},
        "public": {"type": "boolean", "default": True},
        "attachments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file_name": {"type": "string"},
                    "content_url": {"type": "string"},
                    "size": {"type": "integer"},
                },
            },
        },
        "audit_id": {"type": "string"},
        "created_at": {"type": "string"},
    },
}

USER_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "name", "email", "role"],
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "email": {"type": "string"},
        "role": {
            "type": "string",
            "enum": ["end-user", "agent", "admin"],
        },
        "organization_id": {"type": "string"},
        "active": {"type": "boolean"},
        "verified": {"type": "boolean"},
        "external_id": {"type": "string"},
        "locale": {"type": "string"},
        "phone": {"type": "string"},
        "photo": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
            },
        },
        "default_group_id": {"type": "string"},
        "created_at": {"type": "string"},
    },
}

GROUP_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "name"],
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "description": {"type": "string"},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
    },
}

ORGANIZATION_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "name"],
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "external_id": {"type": "string"},
        "domain_names": {
            "type": "array",
            "items": {"type": "string"},
        },
        "details": {"type": "string"},
        "notes": {"type": "string"},
        "group_id": {"type": "string", "x-terrarium-ref": "group"},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
    },
}

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TICKET_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "zendesk_tickets_list",
        "description": "List tickets, optionally filtered by status, assignee, or requester.",
        "http_path": "/api/v2/tickets",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by ticket status.",
                },
                "assignee_id": {
                    "type": "string",
                    "description": "Filter by assignee ID.",
                },
                "requester_id": {
                    "type": "string",
                    "description": "Filter by requester ID.",
                },
                "page": {
                    "type": "integer",
                    "description": "Page number for pagination.",
                },
                "per_page": {
                    "type": "integer",
                    "description": "Number of results per page.",
                    "default": 100,
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "tickets": {"type": "array"},
                "count": {"type": "integer"},
                "next_page": {"type": ["integer", "null"]},
            },
        },
    },
    {
        "name": "zendesk_tickets_show",
        "description": "Show details of a specific ticket by ID.",
        "http_path": "/api/v2/tickets/{id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The ticket ID to retrieve.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "ticket": {"type": "object"},
            },
        },
    },
    {
        "name": "zendesk_tickets_create",
        "description": "Create a new support ticket.",
        "http_path": "/api/v2/tickets",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["subject", "description", "requester_id"],
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Ticket subject line.",
                },
                "description": {
                    "type": "string",
                    "description": "Ticket description / initial comment body.",
                },
                "requester_id": {
                    "type": "string",
                    "description": "ID of the user who requested the ticket.",
                },
                "priority": {
                    "type": "string",
                    "description": "Ticket priority level.",
                    "enum": ["urgent", "high", "normal", "low"],
                },
                "type": {
                    "type": "string",
                    "description": "Ticket type.",
                    "enum": ["problem", "incident", "question", "task"],
                },
                "assignee_id": {
                    "type": "string",
                    "description": "ID of the agent assigned to the ticket.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags to apply to the ticket.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "ticket": {"type": "object"},
            },
        },
    },
    {
        "name": "zendesk_tickets_update",
        "description": "Update an existing ticket.",
        "http_path": "/api/v2/tickets/{id}",
        "http_method": "PUT",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The ticket ID to update.",
                },
                "status": {
                    "type": "string",
                    "description": "New ticket status.",
                    "enum": ["new", "open", "pending", "hold", "solved", "closed"],
                },
                "assignee_id": {
                    "type": "string",
                    "description": "New assignee ID.",
                },
                "priority": {
                    "type": "string",
                    "description": "New priority level.",
                    "enum": ["urgent", "high", "normal", "low"],
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Replacement tags for the ticket.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "ticket": {"type": "object"},
            },
        },
    },
    {
        "name": "zendesk_tickets_delete",
        "description": "Soft-delete a ticket (marks as deleted, does not destroy).",
        "http_path": "/api/v2/tickets/{id}",
        "http_method": "DELETE",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The ticket ID to delete.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "zendesk_tickets_search",
        "description": "Search tickets using Zendesk search query syntax.",
        "http_path": "/api/v2/search",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Zendesk search query string.",
                },
                "page": {
                    "type": "integer",
                    "description": "Page number for pagination.",
                },
                "per_page": {
                    "type": "integer",
                    "description": "Number of results per page.",
                    "default": 100,
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "results": {"type": "array"},
                "count": {"type": "integer"},
                "next_page": {"type": ["integer", "null"]},
            },
        },
    },
    {
        "name": "zendesk_ticket_comments_list",
        "description": "List all comments on a ticket.",
        "http_path": "/api/v2/tickets/{id}/comments",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The ticket ID whose comments to list.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "comments": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
    },
    {
        "name": "zendesk_ticket_comments_create",
        "description": "Add a comment to a ticket.",
        "http_path": "/api/v2/tickets/{id}/comments",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["id", "body", "author_id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The ticket ID to comment on.",
                },
                "body": {
                    "type": "string",
                    "description": "Comment body text.",
                },
                "author_id": {
                    "type": "string",
                    "description": "ID of the user authoring the comment.",
                },
                "public": {
                    "type": "boolean",
                    "description": "Whether the comment is public.",
                    "default": True,
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "comment": {"type": "object"},
            },
        },
    },
    {
        "name": "zendesk_users_list",
        "description": "List users, optionally filtered by role.",
        "http_path": "/api/v2/users",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "role": {
                    "type": "string",
                    "description": "Filter by user role.",
                    "enum": ["end-user", "agent", "admin"],
                },
                "page": {
                    "type": "integer",
                    "description": "Page number for pagination.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "users": {"type": "array"},
                "count": {"type": "integer"},
                "next_page": {"type": ["integer", "null"]},
            },
        },
    },
    {
        "name": "zendesk_users_show",
        "description": "Show details of a specific user by ID.",
        "http_path": "/api/v2/users/{id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The user ID to retrieve.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "user": {"type": "object"},
            },
        },
    },
    {
        "name": "zendesk_groups_list",
        "description": "List all groups.",
        "http_path": "/api/v2/groups",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "page": {
                    "type": "integer",
                    "description": "Page number for pagination.",
                },
                "per_page": {
                    "type": "integer",
                    "description": "Number of results per page.",
                    "default": 100,
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "groups": {"type": "array"},
                "count": {"type": "integer"},
                "next_page": {"type": ["integer", "null"]},
            },
        },
    },
    {
        "name": "zendesk_groups_show",
        "description": "Show details of a specific group by ID.",
        "http_path": "/api/v2/groups/{id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The group ID to retrieve.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "group": {"type": "object"},
            },
        },
    },
]
