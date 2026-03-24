"""Entity schemas and tool definitions for the email service pack.

Gmail-aligned schemas and tool definitions following google_workspace_mcp
naming conventions.  Legacy email_* schemas are kept for backward
compatibility.

Pure data -- no logic, no imports beyond stdlib.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Gmail-aligned entity schemas
# ---------------------------------------------------------------------------

MESSAGE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "threadId", "labelIds", "snippet", "subject", "body"],
    "properties": {
        "id": {"type": "string"},
        "threadId": {"type": "string", "x-terrarium-ref": "gmail_thread"},
        "labelIds": {"type": "array", "items": {"type": "string"}},
        "snippet": {"type": "string"},
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "from_addr": {"type": "string"},
        "to_addr": {"type": "string"},
        "internalDate": {"type": "string"},
        "sizeEstimate": {"type": "integer"},
    },
}

THREAD_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "snippet"],
    "properties": {
        "id": {"type": "string"},
        "snippet": {"type": "string"},
        "messages": {"type": "array", "items": {"type": "string"}},
        "historyId": {"type": "string"},
    },
}

LABEL_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "name"],
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "type": {"type": "string", "enum": ["system", "user"]},
        "messagesTotal": {"type": "integer"},
        "messagesUnread": {"type": "integer"},
    },
}

DRAFT_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id"],
    "properties": {
        "id": {"type": "string"},
        "to": {"type": "string"},
        "subject": {"type": "string"},
        "body": {"type": "string"},
    },
}

# ---------------------------------------------------------------------------
# Legacy entity schemas (backward compatibility)
# ---------------------------------------------------------------------------

EMAIL_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "email_id",
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
    "x-terrarium-identity": "mailbox_id",
    "required": ["mailbox_id", "owner"],
    "properties": {
        "mailbox_id": {"type": "string"},
        "owner": {"type": "string"},
        "display_name": {"type": "string"},
        "unread_count": {"type": "integer", "minimum": 0},
    },
}

# ---------------------------------------------------------------------------
# Gmail-aligned tool definitions (google_workspace_mcp names)
# ---------------------------------------------------------------------------

EMAIL_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "search_gmail_messages",
        "description": "Search Gmail messages by query",
        "http_path": "/gmail/v1/messages",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "properties": {
                "q": {
                    "type": "string",
                    "description": "Gmail search query",
                },
                "labelIds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by label IDs",
                },
                "maxResults": {
                    "type": "integer",
                    "description": "Max messages to return",
                    "minimum": 1,
                },
            },
        },
    },
    {
        "name": "get_gmail_message",
        "description": "Get a Gmail message by ID",
        "http_path": "/gmail/v1/messages/{id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "string", "description": "Message ID"},
            },
        },
    },
    {
        "name": "send_gmail_message",
        "description": "Send a Gmail message",
        "http_path": "/gmail/v1/messages/send",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["to", "subject", "body"],
            "properties": {
                "to": {"type": "string", "description": "Recipient email"},
                "from": {"type": "string", "description": "Sender email"},
                "subject": {"type": "string", "description": "Subject line"},
                "body": {"type": "string", "description": "Message body"},
            },
        },
    },
    {
        "name": "create_gmail_draft",
        "description": "Create a Gmail draft",
        "http_path": "/gmail/v1/drafts",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["to", "subject", "body"],
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
        },
    },
    {
        "name": "modify_gmail_message",
        "description": "Modify Gmail message labels",
        "http_path": "/gmail/v1/messages/{id}/modify",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "string"},
                "addLabelIds": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "removeLabelIds": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
    },
    {
        "name": "trash_gmail_message",
        "description": "Move a Gmail message to trash",
        "http_path": "/gmail/v1/messages/{id}/trash",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "string", "description": "Message ID"},
            },
        },
    },
    {
        "name": "delete_gmail_message",
        "description": "Permanently delete a Gmail message",
        "http_path": "/gmail/v1/messages/{id}",
        "http_method": "DELETE",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {"type": "string", "description": "Message ID"},
            },
        },
    },
    {
        "name": "list_gmail_labels",
        "description": "List all Gmail labels",
        "http_path": "/gmail/v1/labels",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
]

# ---------------------------------------------------------------------------
# Legacy tool definitions (backward compatibility)
# ---------------------------------------------------------------------------

LEGACY_EMAIL_TOOL_DEFINITIONS: list[dict] = [
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
                "mailbox_owner": {
                    "type": "string",
                    "description": "Owner of the mailbox to list.",
                },
                "status_filter": {
                    "type": "string",
                    "description": "Optional status to filter by.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of emails to return.",
                    "minimum": 1,
                },
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
                "email_id": {
                    "type": "string",
                    "description": "ID of the email to reply to.",
                },
                "from_addr": {
                    "type": "string",
                    "description": "Sender email address for the reply.",
                },
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
