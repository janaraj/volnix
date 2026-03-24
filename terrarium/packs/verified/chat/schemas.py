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
        "creator": {"type": "string", "description": "User ID who created the channel."},
        "is_member": {
            "type": "boolean",
            "description": "Whether the calling user is a member.",
        },
        "members": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of user IDs who are members of this channel.",
        },
        "topic": {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
                "creator": {"type": "string"},
                "last_set": {"type": "integer", "description": "Unix timestamp."},
            },
        },
        "purpose": {
            "type": "object",
            "properties": {
                "value": {"type": "string"},
                "creator": {"type": "string"},
                "last_set": {"type": "integer", "description": "Unix timestamp."},
            },
        },
        "num_members": {"type": "integer", "minimum": 0},
        "created": {"type": "integer", "description": "Unix timestamp of channel creation."},
        "unlinked": {"type": "integer", "description": "Timestamp of unlink event, 0 if linked."},
        "name_normalized": {
            "type": "string",
            "description": "Lowercased, normalized version of the channel name.",
        },
        "is_shared": {"type": "boolean"},
        "is_org_shared": {"type": "boolean"},
        "is_general": {
            "type": "boolean",
            "description": "Whether this is the workspace's #general channel.",
        },
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
        "subtype": {
            "type": ["string", "null"],
            "description": "Message subtype (e.g. 'channel_join', 'bot_message').",
        },
        "thread_ts": {"type": ["string", "null"], "description": "Parent message ts for threaded replies."},
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
        "edited": {
            "type": ["object", "null"],
            "description": "Edit metadata, null if never edited.",
            "properties": {
                "user": {"type": "string"},
                "ts": {"type": "string"},
            },
        },
        "bot_id": {
            "type": ["string", "null"],
            "description": "Bot ID if posted by a bot integration.",
        },
        "app_id": {
            "type": ["string", "null"],
            "description": "App ID if posted by a Slack app.",
        },
        "blocks": {
            "type": ["array", "null"],
            "description": "Block Kit content blocks.",
            "items": {"type": "object"},
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
        "is_owner": {"type": "boolean", "description": "Whether the user is a workspace owner."},
        "is_primary_owner": {
            "type": "boolean",
            "description": "Whether the user is the primary workspace owner.",
        },
        "is_restricted": {
            "type": "boolean",
            "description": "Whether the user is a guest (multi-channel).",
        },
        "is_ultra_restricted": {
            "type": "boolean",
            "description": "Whether the user is a single-channel guest.",
        },
        "updated": {
            "type": "integer",
            "description": "Unix timestamp of the last profile update.",
        },
        "status_text": {"type": "string"},
        "status_emoji": {"type": "string"},
        "tz": {"type": "string"},
        "profile": {
            "type": "object",
            "description": "Extended profile with avatar URLs.",
            "properties": {
                "image_24": {"type": "string"},
                "image_48": {"type": "string"},
                "image_72": {"type": "string"},
            },
        },
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
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "channels": {"type": "array"},
                "response_metadata": {"type": "object"},
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
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "channel": {"type": "string"},
                "ts": {"type": "string"},
                "message": {"type": "object"},
            },
        },
    },
    {
        "name": "slack_update_message",
        "description": "Update an existing message in a channel.",
        "http_path": "/slack/v1/chat.update",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["channel_id", "ts", "text"],
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "ID of the channel containing the message.",
                },
                "ts": {
                    "type": "string",
                    "description": "Timestamp of the message to update.",
                },
                "text": {"type": "string", "description": "New message text content."},
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "channel": {"type": "string"},
                "ts": {"type": "string"},
                "text": {"type": "string"},
            },
        },
    },
    {
        "name": "slack_delete_message",
        "description": "Delete a message from a channel.",
        "http_path": "/slack/v1/chat.delete",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["channel_id", "ts"],
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "ID of the channel containing the message.",
                },
                "ts": {
                    "type": "string",
                    "description": "Timestamp of the message to delete.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "channel": {"type": "string"},
                "ts": {"type": "string"},
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
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "channel": {"type": "string"},
                "ts": {"type": "string"},
                "message": {"type": "object"},
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
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
            },
        },
    },
    {
        "name": "slack_remove_reaction",
        "description": "Remove an emoji reaction from a message.",
        "http_path": "/slack/v1/reactions.remove",
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
                    "description": "Timestamp of the message to remove reaction from.",
                },
                "reaction": {
                    "type": "string",
                    "description": "Emoji name without colons (e.g. 'thumbsup').",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
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
                "cursor": {
                    "type": "string",
                    "description": "Pagination cursor for the next page.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "messages": {"type": "array"},
                "has_more": {"type": "boolean"},
                "response_metadata": {"type": "object"},
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
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "messages": {"type": "array"},
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
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "members": {"type": "array"},
                "response_metadata": {"type": "object"},
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
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "user": {"type": "object"},
            },
        },
    },
    {
        "name": "slack_create_channel",
        "description": "Create a new channel in the workspace.",
        "http_path": "/slack/v1/conversations.create",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the channel to create.",
                },
                "is_private": {
                    "type": "boolean",
                    "description": "Whether the channel should be private.",
                    "default": False,
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "channel": {"type": "object"},
            },
        },
    },
    {
        "name": "slack_archive_channel",
        "description": "Archive a channel.",
        "http_path": "/slack/v1/conversations.archive",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["channel_id"],
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "ID of the channel to archive.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
            },
        },
    },
    {
        "name": "slack_join_channel",
        "description": "Join a channel.",
        "http_path": "/slack/v1/conversations.join",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["channel_id"],
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "ID of the channel to join.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "channel": {"type": "object"},
            },
        },
    },
    {
        "name": "slack_set_channel_topic",
        "description": "Set the topic for a channel.",
        "http_path": "/slack/v1/conversations.setTopic",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["channel_id", "topic"],
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "ID of the channel to set the topic for.",
                },
                "topic": {
                    "type": "string",
                    "description": "New topic value.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "topic": {"type": "object"},
            },
        },
    },
    {
        "name": "slack_get_channel_info",
        "description": "Get detailed information about a channel.",
        "http_path": "/slack/v1/conversations.info",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["channel_id"],
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "ID of the channel to get info for.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "channel": {"type": "object"},
            },
        },
    },
]
