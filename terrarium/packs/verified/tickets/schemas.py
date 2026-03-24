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
        "tags": {"type": "array", "items": {"type": "string"}},
        "via": {
            "type": "object",
            "properties": {
                "channel": {"type": "string"},
            },
        },
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
        "due_at": {"type": "string"},
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
        "public": {"type": "boolean", "default": True},
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
    },
]
