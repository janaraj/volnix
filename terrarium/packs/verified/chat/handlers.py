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


async def handle_slack_list_channels(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``slack_list_channels`` action.

    Returns channels from state, limited by the ``limit`` parameter.
    No state mutations.
    """
    channels = state.get("channels", [])
    limit = input_data.get("limit", 100)
    limited = channels[:limit]

    return ResponseProposal(
        response_body={
            "ok": True,
            "channels": limited,
        },
    )


async def handle_slack_post_message(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``slack_post_message`` action.

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
        "thread_ts": None,
        "reply_count": 0,
        "reactions": [],
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


async def handle_slack_reply_to_thread(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``slack_reply_to_thread`` action.

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
        "thread_ts": thread_ts,
        "reply_count": 0,
        "reactions": [],
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


async def handle_slack_add_reaction(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``slack_add_reaction`` action.

    Adds an emoji reaction to the target message. If the user already
    reacted with the same emoji, returns an ``already_reacted`` error.
    """
    channel_id = input_data["channel_id"]
    timestamp = input_data["timestamp"]
    reaction = input_data["reaction"]
    user_id = input_data.get("user_id", "unknown")

    messages = state.get("messages", [])
    target_msg: dict[str, Any] | None = None
    for msg in messages:
        if msg.get("ts") == timestamp and msg.get("channel") == channel_id:
            target_msg = msg
            break

    if target_msg is None:
        return ResponseProposal(
            response_body={
                "ok": False,
                "error": "message_not_found",
            },
        )

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
            return ResponseProposal(
                response_body={
                    "ok": False,
                    "error": "already_reacted",
                },
            )
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


async def handle_slack_get_channel_history(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``slack_get_channel_history`` action.

    Filters messages by channel, sorts by ts descending, applies limit.
    No state mutations.
    """
    channel_id = input_data["channel_id"]
    limit = input_data.get("limit", 10)
    messages = state.get("messages", [])

    filtered = [m for m in messages if m.get("channel") == channel_id]
    filtered.sort(key=lambda m: m.get("ts", ""), reverse=True)
    limited = filtered[:limit]

    return ResponseProposal(
        response_body={
            "ok": True,
            "messages": limited,
        },
    )


async def handle_slack_get_thread_replies(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``slack_get_thread_replies`` action.

    Returns all messages belonging to a thread (matching thread_ts),
    sorted by ts ascending.  No state mutations.
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


async def handle_slack_get_users(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``slack_get_users`` action.

    Returns users from state, limited by the ``limit`` parameter.
    No state mutations.
    """
    users = state.get("users", [])
    limit = input_data.get("limit", 100)
    limited = users[:limit]

    return ResponseProposal(
        response_body={
            "ok": True,
            "members": limited,
        },
    )


async def handle_slack_get_user_profile(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``slack_get_user_profile`` action.

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
        return ResponseProposal(
            response_body={
                "ok": False,
                "error": "user_not_found",
            },
        )

    return ResponseProposal(
        response_body={
            "ok": True,
            "user": target_user,
        },
    )
