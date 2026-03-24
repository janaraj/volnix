"""Entity schemas and tool definitions for the chat service pack.

Pure data -- no logic, no imports beyond stdlib.  Tool names and HTTP
paths are aligned with the official Slack MCP server conventions.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------

CHANNEL_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "name"],
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "is_channel": {"type": "boolean"},
        "is_private": {"type": "boolean"},
        "is_archived": {"type": "boolean"},
        "topic": {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
            },
        },
        "purpose": {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
            },
        },
        "num_members": {"type": "integer", "minimum": 0},
        "created": {"type": "integer", "description": "Unix timestamp of channel creation."},
    },
}

MESSAGE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "ts",
    "required": ["ts", "channel", "text"],
    "properties": {
        "ts": {"type": "string", "description": "Slack-style timestamp used as message ID."},
        "channel": {"type": "string", "x-terrarium-ref": "channel"},
        "user": {"type": "string", "x-terrarium-ref": "user"},
        "text": {"type": "string"},
        "type": {"type": "string", "enum": ["message"]},
        "thread_ts": {"type": "string", "description": "Parent message ts for threaded replies."},
        "reply_count": {"type": "integer", "minimum": 0},
        "reactions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "users": {"type": "array", "items": {"type": "string"}},
                    "count": {"type": "integer", "minimum": 0},
                },
            },
        },
    },
}

USER_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "name"],
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "real_name": {"type": "string"},
        "display_name": {"type": "string"},
        "email": {"type": "string"},
        "is_bot": {"type": "boolean"},
        "is_admin": {"type": "boolean"},
        "status_text": {"type": "string"},
        "status_emoji": {"type": "string"},
        "tz": {"type": "string"},
    },
}

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

CHAT_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "slack_list_channels",
        "description": "List public and private channels in the workspace.",
        "http_path": "/slack/v1/conversations.list",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of channels to return.",
                    "default": 100,
                },
                "cursor": {
                    "type": "string",
                    "description": "Pagination cursor for the next page.",
                },
            },
        },
    },
    {
        "name": "slack_post_message",
        "description": "Post a new message to a channel.",
        "http_path": "/slack/v1/chat.postMessage",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["channel_id", "text"],
            "properties": {
                "channel_id": {"type": "string", "description": "ID of the channel to post to."},
                "text": {"type": "string", "description": "Message text content."},
            },
        },
    },
    {
        "name": "slack_reply_to_thread",
        "description": "Reply to a message thread in a channel.",
        "http_path": "/slack/v1/chat.postMessage",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["channel_id", "thread_ts", "text"],
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "ID of the channel containing the thread.",
                },
                "thread_ts": {
                    "type": "string",
                    "description": "Timestamp of the parent message.",
                },
                "text": {"type": "string", "description": "Reply text content."},
            },
        },
    },
    {
        "name": "slack_add_reaction",
        "description": "Add an emoji reaction to a message.",
        "http_path": "/slack/v1/reactions.add",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["channel_id", "timestamp", "reaction"],
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "ID of the channel containing the message.",
                },
                "timestamp": {
                    "type": "string",
                    "description": "Timestamp of the message to react to.",
                },
                "reaction": {
                    "type": "string",
                    "description": "Emoji name without colons (e.g. 'thumbsup').",
                },
            },
        },
    },
    {
        "name": "slack_get_channel_history",
        "description": "Retrieve recent messages from a channel.",
        "http_path": "/slack/v1/conversations.history",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["channel_id"],
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "ID of the channel to fetch history for.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of messages to return.",
                    "default": 10,
                },
            },
        },
    },
    {
        "name": "slack_get_thread_replies",
        "description": "Retrieve all replies in a message thread.",
        "http_path": "/slack/v1/conversations.replies",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["channel_id", "thread_ts"],
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "ID of the channel containing the thread.",
                },
                "thread_ts": {
                    "type": "string",
                    "description": "Timestamp of the parent message.",
                },
            },
        },
    },
    {
        "name": "slack_get_users",
        "description": "List users in the workspace.",
        "http_path": "/slack/v1/users.list",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of users to return.",
                    "default": 100,
                },
                "cursor": {
                    "type": "string",
                    "description": "Pagination cursor for the next page.",
                },
            },
        },
    },
    {
        "name": "slack_get_user_profile",
        "description": "Get profile information for a specific user.",
        "http_path": "/slack/v1/users.info",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["user_id"],
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "ID of the user to look up.",
                },
            },
        },
    },
]
