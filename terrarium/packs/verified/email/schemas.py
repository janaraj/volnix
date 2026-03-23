"""Entity schemas and tool definitions for the email service pack.

Pure data -- no logic, no imports beyond stdlib.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------

EMAIL_ENTITY_SCHEMA: dict = {
    "type": "object",
    "required": ["email_id", "from_addr", "to_addr", "subject", "body", "status"],
    "properties": {
        "email_id": {"type": "string"},
        "from_addr": {"type": "string"},
        "to_addr": {"type": "string"},
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["draft", "sent", "delivered", "read", "archived", "trashed"],
        },
        "thread_id": {"type": "string"},
        "in_reply_to": {"type": "string"},
        "timestamp": {"type": "string"},
        "headers": {"type": "object"},
    },
}

MAILBOX_ENTITY_SCHEMA: dict = {
    "type": "object",
    "required": ["mailbox_id", "owner"],
    "properties": {
        "mailbox_id": {"type": "string"},
        "owner": {"type": "string"},
        "display_name": {"type": "string"},
        "unread_count": {"type": "integer", "minimum": 0},
    },
}

THREAD_ENTITY_SCHEMA: dict = {
    "type": "object",
    "required": ["thread_id", "subject"],
    "properties": {
        "thread_id": {"type": "string"},
        "subject": {"type": "string"},
        "participants": {"type": "array", "items": {"type": "string"}},
        "message_count": {"type": "integer", "minimum": 0},
    },
}

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

EMAIL_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "email_send",
        "description": "Send an email message.",
        "http_path": "/email/v1/messages/send",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["from_addr", "to_addr", "subject", "body"],
            "properties": {
                "from_addr": {"type": "string", "description": "Sender email address."},
                "to_addr": {"type": "string", "description": "Recipient email address."},
                "subject": {"type": "string", "description": "Email subject line."},
                "body": {"type": "string", "description": "Email body text."},
            },
        },
    },
    {
        "name": "email_list",
        "description": "List emails in a mailbox.",
        "http_path": "/email/v1/messages",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["mailbox_owner"],
            "properties": {
                "mailbox_owner": {"type": "string", "description": "Owner of the mailbox to list."},
                "status_filter": {"type": "string", "description": "Optional status to filter by."},
                "limit": {"type": "integer", "description": "Max number of emails to return.", "minimum": 1},
            },
        },
    },
    {
        "name": "email_read",
        "description": "Read a specific email by ID.",
        "http_path": "/email/v1/messages/{email_id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["email_id"],
            "properties": {
                "email_id": {"type": "string", "description": "ID of the email to read."},
            },
        },
    },
    {
        "name": "email_search",
        "description": "Search emails by query, sender, or subject.",
        "http_path": "/email/v1/messages/search",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "query": {"type": "string", "description": "Free-text search query."},
                "sender": {"type": "string", "description": "Filter by sender address."},
                "subject": {"type": "string", "description": "Filter by subject line."},
            },
        },
    },
    {
        "name": "email_reply",
        "description": "Reply to an existing email.",
        "http_path": "/email/v1/messages/{email_id}/reply",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["email_id", "from_addr", "body"],
            "properties": {
                "email_id": {"type": "string", "description": "ID of the email to reply to."},
                "from_addr": {"type": "string", "description": "Sender email address for the reply."},
                "body": {"type": "string", "description": "Reply body text."},
            },
        },
    },
    {
        "name": "email_mark_read",
        "description": "Mark one or more emails as read.",
        "http_path": "/email/v1/messages/mark-read",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["email_ids"],
            "properties": {
                "email_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of email IDs to mark as read.",
                },
            },
        },
    },
]
