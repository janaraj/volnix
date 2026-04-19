"""Entity schemas and tool definitions for the npc_chat pack.

Pure data — no imports beyond stdlib. Provides:

* ``npc_message`` — a one-way message from one NPC to another.
* ``npc_state`` — the per-NPC persistent state envelope the
  ``consumer_user`` activation profile (and future NPC profiles)
  writes to.

Shapes are intentionally narrow and stable. NPCs don't hold rich
threaded conversations or edit history — they ping each other and
move on. Adding reply/threading later is additive via a separate
tool; keeping it out of Phase 3 keeps the surface reviewable.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------

# A single NPC-to-NPC message. Immutable once committed; a reply is a
# new message, not an edit. ``feature_mention`` is the critical field —
# a non-empty value is what triggers ``WordOfMouthEvent`` emission in
# the handler below, wiring feature discovery through social graph.

NPC_MESSAGE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "sender_id", "recipient_id", "content", "sent_at"],
    "properties": {
        "id": {
            "type": "string",
            "description": "Unique message identifier (``npcmsg-<uuid>``).",
        },
        "sender_id": {
            "type": "string",
            "description": "Actor id of the NPC who sent the message.",
            "x-volnix-ref": "actor",
        },
        "recipient_id": {
            "type": "string",
            "description": "Actor id of the NPC who receives the message.",
            "x-volnix-ref": "actor",
        },
        "content": {
            "type": "string",
            "description": "The message body.",
        },
        "feature_mention": {
            "type": ["string", "null"],
            "description": (
                "Optional product feature the sender is mentioning. When "
                "non-null, the pack emits a ``WordOfMouthEvent`` so the "
                "recipient NPC's subscription (filter.event_type = "
                "``npc.word_of_mouth``) activates them."
            ),
        },
        "sentiment": {
            "type": "string",
            "enum": ["positive", "neutral", "negative"],
            "description": (
                "Sender's sentiment toward ``feature_mention``. Carried "
                "through to the emitted ``WordOfMouthEvent`` so the "
                "receiving NPC's prompt can reflect tone."
            ),
        },
        "sent_at": {
            "type": "integer",
            "description": "Logical tick at which the message was sent.",
        },
    },
}


# Per-NPC persistent state. One entity per Active NPC, keyed by
# ``actor_id``. The ``state`` field is free-form because each activation
# profile declares its own state_schema; we don't try to narrow it here
# (that validation belongs to the profile, and the per-profile schema
# is already enforced by ``ActivationProfile.state_schema``).

NPC_STATE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "actor_id", "activation_profile_name", "state"],
    "properties": {
        "id": {
            "type": "string",
            "description": "Entity id (matches ``actor_id`` for easy lookup).",
        },
        "actor_id": {
            "type": "string",
            "description": "The Active NPC this state belongs to.",
            "x-volnix-ref": "actor",
        },
        "activation_profile_name": {
            "type": "string",
            "description": (
                "Which activation profile this state conforms to. "
                "Lets a reader resolve the JSON Schema that validates "
                "the ``state`` dict."
            ),
        },
        "state": {
            "type": "object",
            "description": (
                "Free-form per-profile state (awareness, interest, "
                "satisfaction, usage_count, etc.). Schema is defined by "
                "the referenced activation profile, not here."
            ),
        },
        "last_updated_tick": {
            "type": ["integer", "null"],
            "description": "Last logical tick at which this state was committed.",
        },
    },
}


# ---------------------------------------------------------------------------
# Tool definitions (manifest)
# ---------------------------------------------------------------------------

NPC_CHAT_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "npc_chat.send_message",
        "description": (
            "Send a one-way message from one NPC to another. Optionally "
            "mention a product feature — when ``feature_mention`` is set, "
            "the pack emits a ``WordOfMouthEvent`` that activates the "
            "recipient NPC via their subscription filter."
        ),
        "http_path": "/npc_chat/v1/send_message",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["recipient_id", "content"],
            "properties": {
                "recipient_id": {
                    "type": "string",
                    "description": "Actor id of the NPC receiving this message.",
                },
                "content": {
                    "type": "string",
                    "description": "The message body.",
                },
                "feature_mention": {
                    "type": ["string", "null"],
                    "description": (
                        "Optional: a product feature the sender is telling the recipient about."
                    ),
                },
                "sentiment": {
                    "type": "string",
                    "enum": ["positive", "neutral", "negative"],
                    "description": "Sender's sentiment toward the mentioned feature.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "message_id": {"type": "string"},
                "delivered": {"type": "boolean"},
            },
        },
    },
    {
        "name": "npc_chat.read_messages",
        "description": (
            "Read the messages this NPC has received. Returns the most "
            "recent ``limit`` entries, newest first."
        ),
        "http_path": "/npc_chat/v1/read_messages",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["recipient_id"],
            "properties": {
                "recipient_id": {
                    "type": "string",
                    "description": "Actor id whose inbox to read (usually self).",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Maximum number of messages to return.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "messages": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
    },
]
