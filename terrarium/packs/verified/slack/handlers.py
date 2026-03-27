"""Action handlers for the chat service pack.

Each function handles one tool action, producing a ResponseProposal with
any state mutations expressed as StateDelta objects.

Handlers import ONLY from terrarium.core (types, context). They NEVER
import from persistence/, engines/, or bus/.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from terrarium.core.context import ResponseProposal
from terrarium.core.types import EntityId, StateDelta


def _new_id(prefix: str) -> str:
    """Generate a unique ID with the given prefix."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now_unix() -> int:
    """Return the current UTC time as a Unix timestamp."""
    return int(datetime.now(UTC).timestamp())


def _now_ts() -> str:
    """Generate Slack-style timestamp (unix.random6) used as message ID."""
    return f"{_now_unix()}.{uuid.uuid4().hex[:6]}"


def _error_response(error: str) -> ResponseProposal:
    """Return a standardized Slack error response."""
    return ResponseProposal(
        response_body={
            "ok": False,
            "error": error,
        },
    )


def _paginate(
    items: list[Any],
    limit: int,
    cursor: str | None,
) -> tuple[list[Any], dict[str, str]]:
    """Apply cursor-based pagination to a list of items.

    Returns:
        A tuple of (page_items, response_metadata) where response_metadata
        contains ``next_cursor`` (empty string if no more pages).
    """
    start = 0
    if cursor:
        # Cursor format: "idx:<integer>"
        try:
            start = int(cursor.split(":", 1)[1])
        except (IndexError, ValueError):
            start = 0

    page = items[start : start + limit]
    next_start = start + limit
    next_cursor = f"idx:{next_start}" if next_start < len(items) else ""

    return page, {"next_cursor": next_cursor}


def _find_channel(state: dict[str, Any], channel_id: str) -> dict[str, Any] | None:
    """Find a channel by ID in state."""
    channels: list[dict[str, Any]] = state.get("channels", [])
    for ch in channels:
        if ch.get("id") == channel_id:
            return ch
    return None


def _find_message(state: dict[str, Any], channel_id: str, ts: str) -> dict[str, Any] | None:
    """Find a message by channel_id and ts in state."""
    messages: list[dict[str, Any]] = state.get("messages", [])
    for msg in messages:
        if msg.get("ts") == ts and msg.get("channel") == channel_id:
            return msg
    return None


# ---------------------------------------------------------------------------
# List channels
# ---------------------------------------------------------------------------


async def handle_channels_list(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``channels_list`` action.

    Returns channels from state with cursor-based pagination.
    No state mutations.
    """
    channels = state.get("channels", [])
    limit = input_data.get("limit", 100)
    cursor = input_data.get("cursor")

    page, response_metadata = _paginate(channels, limit, cursor)

    return ResponseProposal(
        response_body={
            "ok": True,
            "channels": page,
            "response_metadata": response_metadata,
        },
    )


# ---------------------------------------------------------------------------
# Post message
# ---------------------------------------------------------------------------


async def handle_chat_postMessage(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``chat_postMessage`` action.

    Creates a new message entity in the target channel.
    """
    channel_id = input_data["channel_id"]
    text = input_data["text"]
    ts = _now_ts()

    message_fields: dict[str, Any] = {
        "ts": ts,
        "channel": channel_id,
        "user": input_data.get("user_id", "unknown"),
        "text": text,
        "type": "message",
        "subtype": None,
        "thread_ts": None,
        "reply_count": 0,
        "reactions": [],
        "edited": None,
        "bot_id": None,
        "app_id": None,
        "blocks": None,
    }

    delta = StateDelta(
        entity_type="message",
        entity_id=EntityId(ts),
        operation="create",
        fields=message_fields,
    )

    return ResponseProposal(
        response_body={
            "ok": True,
            "channel": channel_id,
            "ts": ts,
            "message": message_fields,
        },
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# Update message
# ---------------------------------------------------------------------------


async def handle_chat_update(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``chat_update`` action.

    Finds a message by channel_id + ts, updates the text field,
    and sets the ``edited`` metadata.
    """
    channel_id = input_data["channel_id"]
    ts = input_data["ts"]
    new_text = input_data["text"]
    user_id = input_data.get("user_id", "unknown")

    target_msg = _find_message(state, channel_id, ts)
    if target_msg is None:
        return _error_response("message_not_found")

    edit_ts = _now_ts()
    edited = {"user": user_id, "ts": edit_ts}

    delta = StateDelta(
        entity_type="message",
        entity_id=EntityId(ts),
        operation="update",
        fields={"text": new_text, "edited": edited},
        previous_fields={
            "text": target_msg.get("text", ""),
            "edited": target_msg.get("edited"),
        },
    )

    return ResponseProposal(
        response_body={
            "ok": True,
            "channel": channel_id,
            "ts": ts,
            "text": new_text,
        },
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# Delete message
# ---------------------------------------------------------------------------


async def handle_chat_delete(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``chat_delete`` action.

    Finds a message by channel_id + ts and deletes it.
    """
    channel_id = input_data["channel_id"]
    ts = input_data["ts"]

    target_msg = _find_message(state, channel_id, ts)
    if target_msg is None:
        return _error_response("message_not_found")

    delta = StateDelta(
        entity_type="message",
        entity_id=EntityId(ts),
        operation="delete",
        fields={},
        previous_fields=dict(target_msg),
    )

    return ResponseProposal(
        response_body={
            "ok": True,
            "channel": channel_id,
            "ts": ts,
        },
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# Reply to thread
# ---------------------------------------------------------------------------


async def handle_chat_replyToThread(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``chat_replyToThread`` action.

    Creates a threaded reply and increments the parent message's reply_count.
    Produces two deltas: one create for the reply, one update for the parent.
    """
    channel_id = input_data["channel_id"]
    thread_ts = input_data["thread_ts"]
    text = input_data["text"]
    ts = _now_ts()

    reply_fields: dict[str, Any] = {
        "ts": ts,
        "channel": channel_id,
        "user": input_data.get("user_id", "unknown"),
        "text": text,
        "type": "message",
        "subtype": None,
        "thread_ts": thread_ts,
        "reply_count": 0,
        "reactions": [],
        "edited": None,
        "bot_id": None,
        "app_id": None,
        "blocks": None,
    }

    deltas: list[StateDelta] = [
        StateDelta(
            entity_type="message",
            entity_id=EntityId(ts),
            operation="create",
            fields=reply_fields,
        ),
    ]

    # Find the parent message and bump its reply_count.
    messages = state.get("messages", [])
    for msg in messages:
        if msg.get("ts") == thread_ts:
            old_count = msg.get("reply_count", 0)
            deltas.append(
                StateDelta(
                    entity_type="message",
                    entity_id=EntityId(thread_ts),
                    operation="update",
                    fields={"reply_count": old_count + 1},
                    previous_fields={"reply_count": old_count},
                )
            )
            break

    return ResponseProposal(
        response_body={
            "ok": True,
            "channel": channel_id,
            "ts": ts,
            "message": reply_fields,
        },
        proposed_state_deltas=deltas,
    )


# ---------------------------------------------------------------------------
# Add reaction
# ---------------------------------------------------------------------------


async def handle_reactions_add(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``reactions_add`` action.

    Adds an emoji reaction to the target message. If the user already
    reacted with the same emoji, returns an ``already_reacted`` error.
    """
    channel_id = input_data["channel_id"]
    timestamp = input_data["timestamp"]
    reaction = input_data["reaction"]
    user_id = input_data.get("user_id", "unknown")

    target_msg = _find_message(state, channel_id, timestamp)
    if target_msg is None:
        return _error_response("message_not_found")

    # Deep-copy reactions so we don't mutate the original state.
    reactions: list[dict[str, Any]] = [dict(r) for r in target_msg.get("reactions", [])]

    # Check for existing reaction from this user.
    existing: dict[str, Any] | None = None
    for r in reactions:
        if r.get("name") == reaction:
            existing = r
            break

    if existing is not None:
        if user_id in existing.get("users", []):
            return _error_response("already_reacted")
        existing["users"] = [*existing.get("users", []), user_id]
        existing["count"] = existing.get("count", 0) + 1
    else:
        reactions.append(
            {
                "name": reaction,
                "users": [user_id],
                "count": 1,
            }
        )

    delta = StateDelta(
        entity_type="message",
        entity_id=EntityId(timestamp),
        operation="update",
        fields={"reactions": reactions},
        previous_fields={"reactions": target_msg.get("reactions", [])},
    )

    return ResponseProposal(
        response_body={
            "ok": True,
        },
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# Remove reaction
# ---------------------------------------------------------------------------


async def handle_reactions_remove(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``reactions_remove`` action.

    Removes an emoji reaction from the target message. Returns an error
    if the reaction or user is not found.
    """
    channel_id = input_data["channel_id"]
    timestamp = input_data["timestamp"]
    reaction = input_data["reaction"]
    user_id = input_data.get("user_id", "unknown")

    target_msg = _find_message(state, channel_id, timestamp)
    if target_msg is None:
        return _error_response("message_not_found")

    # Deep-copy reactions so we don't mutate the original state.
    reactions: list[dict[str, Any]] = [dict(r) for r in target_msg.get("reactions", [])]

    # Find the reaction entry.
    existing: dict[str, Any] | None = None
    existing_idx: int = -1
    for idx, r in enumerate(reactions):
        if r.get("name") == reaction:
            existing = r
            existing_idx = idx
            break

    if existing is None:
        return _error_response("no_reaction")

    users = list(existing.get("users", []))
    if user_id not in users:
        return _error_response("no_reaction")

    users.remove(user_id)
    if len(users) == 0:
        # Remove the reaction entry entirely.
        reactions.pop(existing_idx)
    else:
        existing["users"] = users
        existing["count"] = len(users)

    delta = StateDelta(
        entity_type="message",
        entity_id=EntityId(timestamp),
        operation="update",
        fields={"reactions": reactions},
        previous_fields={"reactions": target_msg.get("reactions", [])},
    )

    return ResponseProposal(
        response_body={
            "ok": True,
        },
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# Get channel history
# ---------------------------------------------------------------------------


async def handle_conversations_history(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``conversations_history`` action.

    Filters messages by channel, sorts by ts descending, applies
    cursor-based pagination. No state mutations.
    """
    channel_id = input_data["channel_id"]
    limit = input_data.get("limit", 10)
    cursor = input_data.get("cursor")
    messages = state.get("messages", [])

    filtered = [m for m in messages if m.get("channel") == channel_id]
    filtered.sort(key=lambda m: m.get("ts", ""), reverse=True)

    page, response_metadata = _paginate(filtered, limit, cursor)

    return ResponseProposal(
        response_body={
            "ok": True,
            "messages": page,
            "has_more": response_metadata["next_cursor"] != "",
            "response_metadata": response_metadata,
        },
    )


# ---------------------------------------------------------------------------
# Get thread replies
# ---------------------------------------------------------------------------


async def handle_conversations_replies(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``conversations_replies`` action.

    Returns all messages belonging to a thread (matching thread_ts),
    sorted by ts ascending. No state mutations.
    """
    thread_ts = input_data["thread_ts"]
    messages = state.get("messages", [])

    # Include the parent message (ts == thread_ts) and all replies.
    replies = [m for m in messages if m.get("thread_ts") == thread_ts or m.get("ts") == thread_ts]
    replies.sort(key=lambda m: m.get("ts", ""))

    return ResponseProposal(
        response_body={
            "ok": True,
            "messages": replies,
        },
    )


# ---------------------------------------------------------------------------
# Get users
# ---------------------------------------------------------------------------


async def handle_users_list(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``users_list`` action.

    Returns users from state with cursor-based pagination.
    No state mutations.
    """
    users = state.get("users", [])
    limit = input_data.get("limit", 100)
    cursor = input_data.get("cursor")

    page, response_metadata = _paginate(users, limit, cursor)

    return ResponseProposal(
        response_body={
            "ok": True,
            "members": page,
            "response_metadata": response_metadata,
        },
    )


# ---------------------------------------------------------------------------
# Get user profile
# ---------------------------------------------------------------------------


async def handle_users_profile_get(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``users_profile_get`` action.

    Finds a user by ID in state and returns their profile.
    """
    user_id = input_data["user_id"]
    users = state.get("users", [])

    target_user: dict[str, Any] | None = None
    for u in users:
        if u.get("id") == user_id:
            target_user = u
            break

    if target_user is None:
        return _error_response("user_not_found")

    return ResponseProposal(
        response_body={
            "ok": True,
            "user": target_user,
        },
    )


# ---------------------------------------------------------------------------
# Create channel
# ---------------------------------------------------------------------------


async def handle_conversations_create(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``conversations_create`` action.

    Creates a new channel entity with the caller as creator and initial member.
    """
    name = input_data["name"]
    is_private = input_data.get("is_private", False)
    user_id = input_data.get("user_id", "unknown")
    now = _now_unix()

    # Check for duplicate channel name.
    for ch in state.get("channels", []):
        if ch.get("name") == name:
            return _error_response("name_taken")

    channel_id = _new_id("C")
    channel_fields: dict[str, Any] = {
        "id": channel_id,
        "name": name,
        "is_channel": True,
        "is_private": is_private,
        "is_archived": False,
        "creator": user_id,
        "is_member": True,
        "members": [user_id],
        "topic": {"value": "", "creator": "", "last_set": 0},
        "purpose": {"value": "", "creator": "", "last_set": 0},
        "num_members": 1,
        "created": now,
        "unlinked": 0,
        "name_normalized": name.lower(),
        "is_shared": False,
        "is_org_shared": False,
        "is_general": False,
    }

    delta = StateDelta(
        entity_type="channel",
        entity_id=EntityId(channel_id),
        operation="create",
        fields=channel_fields,
    )

    return ResponseProposal(
        response_body={
            "ok": True,
            "channel": channel_fields,
        },
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# Archive channel
# ---------------------------------------------------------------------------


async def handle_conversations_archive(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``conversations_archive`` action.

    Sets is_archived=True on the target channel.
    """
    channel_id = input_data["channel_id"]
    target_channel = _find_channel(state, channel_id)

    if target_channel is None:
        return _error_response("channel_not_found")

    if target_channel.get("is_archived"):
        return _error_response("already_archived")

    delta = StateDelta(
        entity_type="channel",
        entity_id=EntityId(channel_id),
        operation="update",
        fields={"is_archived": True},
        previous_fields={"is_archived": False},
    )

    return ResponseProposal(
        response_body={
            "ok": True,
        },
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# Join channel
# ---------------------------------------------------------------------------


async def handle_conversations_join(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``conversations_join`` action.

    Adds the user to the channel's members array and increments num_members.
    """
    channel_id = input_data["channel_id"]
    user_id = input_data.get("user_id", "unknown")
    target_channel = _find_channel(state, channel_id)

    if target_channel is None:
        return _error_response("channel_not_found")

    if target_channel.get("is_archived"):
        return _error_response("is_archived")

    members = list(target_channel.get("members", []))
    old_num = target_channel.get("num_members", len(members))

    if user_id in members:
        # Already a member -- Slack returns success with the channel.
        return ResponseProposal(
            response_body={
                "ok": True,
                "channel": target_channel,
            },
        )

    new_members = [*members, user_id]
    new_num = old_num + 1

    delta = StateDelta(
        entity_type="channel",
        entity_id=EntityId(channel_id),
        operation="update",
        fields={
            "members": new_members,
            "num_members": new_num,
            "is_member": True,
        },
        previous_fields={
            "members": members,
            "num_members": old_num,
            "is_member": target_channel.get("is_member", False),
        },
    )

    updated_channel = dict(target_channel)
    updated_channel["members"] = new_members
    updated_channel["num_members"] = new_num
    updated_channel["is_member"] = True

    return ResponseProposal(
        response_body={
            "ok": True,
            "channel": updated_channel,
        },
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# Set channel topic
# ---------------------------------------------------------------------------


async def handle_conversations_setTopic(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``conversations_setTopic`` action.

    Updates the topic value, creator, and last_set timestamp on a channel.
    """
    channel_id = input_data["channel_id"]
    new_topic = input_data["topic"]
    user_id = input_data.get("user_id", "unknown")
    now = _now_unix()

    target_channel = _find_channel(state, channel_id)
    if target_channel is None:
        return _error_response("channel_not_found")

    if target_channel.get("is_archived"):
        return _error_response("is_archived")

    old_topic = target_channel.get("topic", {"value": "", "creator": "", "last_set": 0})
    new_topic_obj = {
        "value": new_topic,
        "creator": user_id,
        "last_set": now,
    }

    delta = StateDelta(
        entity_type="channel",
        entity_id=EntityId(channel_id),
        operation="update",
        fields={"topic": new_topic_obj},
        previous_fields={"topic": old_topic},
    )

    return ResponseProposal(
        response_body={
            "ok": True,
            "topic": new_topic_obj,
        },
        proposed_state_deltas=[delta],
    )


# ---------------------------------------------------------------------------
# Get channel info
# ---------------------------------------------------------------------------


async def handle_conversations_info(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``conversations_info`` action.

    Returns detailed information about a single channel.
    """
    channel_id = input_data["channel_id"]
    target_channel = _find_channel(state, channel_id)

    if target_channel is None:
        return _error_response("channel_not_found")

    return ResponseProposal(
        response_body={
            "ok": True,
            "channel": target_channel,
        },
    )
