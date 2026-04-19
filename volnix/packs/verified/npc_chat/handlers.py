"""Action handlers for the ``npc_chat`` pack.

Each handler produces a ``ResponseProposal`` with the state mutation
expressed as a ``StateDelta``. Handlers import only from
``volnix.core``; no cross-engine reach-ins (same discipline as other
verified packs).

The emitter-side contract for ``WordOfMouthEvent`` is here: when the
sender's ``send_message`` call carries a ``feature_mention``, the
handler appends a ``WordOfMouthEvent`` to ``proposed_events`` so the
pipeline publishes it alongside the committed message. The recipient's
subscription (filter ``event_type == npc.word_of_mouth``) then
activates them via ``AgencyEngine.notify`` — no bus reach-in from the
handler is needed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from volnix.core.context import ResponseProposal
from volnix.core.events import WordOfMouthEvent
from volnix.core.types import ActorId, EntityId, ServiceId, StateDelta, Timestamp

# -- small helpers ------------------------------------------------------------


def _new_message_id() -> str:
    return f"npcmsg-{uuid.uuid4().hex[:12]}"


def _now_timestamp() -> Timestamp:
    now = datetime.now(UTC)
    return Timestamp(world_time=now, wall_time=now, tick=0)


def _tick_from_state(state: dict[str, Any]) -> int:
    """Extract the current logical tick from the dispatcher's state arg.

    The state dict is populated by the pipeline; if no tick is supplied
    (tests often don't), fall back to 0. Return int so the schema's
    integer type is satisfied.
    """
    tick = state.get("tick") if isinstance(state, dict) else 0
    try:
        return int(tick) if tick is not None else 0
    except (TypeError, ValueError):
        return 0


# -- npc_chat.send_message ----------------------------------------------------


async def handle_send_message(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Send an NPC-to-NPC message; emit a WordOfMouthEvent on feature_mention.

    The commit step persists the ``npc_message`` entity from the
    ``proposed_state_deltas``. The optional ``WordOfMouthEvent`` is
    appended to ``proposed_events`` so it flows through
    ``CommitStep`` (``volnix/engines/state/engine.py:320-328``) along
    with the main committed event.
    """
    sender_id = input_data.get("sender_id") or input_data.get("actor_id", "unknown")
    recipient_id = input_data["recipient_id"]
    content = input_data["content"]
    feature_mention = input_data.get("feature_mention") or None
    sentiment = input_data.get("sentiment", "neutral")

    msg_id = _new_message_id()
    sent_at = _tick_from_state(state)

    message_fields: dict[str, Any] = {
        "id": msg_id,
        "sender_id": sender_id,
        "recipient_id": recipient_id,
        "content": content,
        "feature_mention": feature_mention,
        "sentiment": sentiment,
        "sent_at": sent_at,
    }

    delta = StateDelta(
        entity_type="npc_message",
        entity_id=EntityId(msg_id),
        operation="create",
        fields=message_fields,
    )

    proposed_events: list[Any] = []
    if feature_mention:
        # Word-of-mouth fires only when the sender is telling the
        # recipient about a specific product feature. Plain social
        # chit-chat (no feature_mention) still commits a message but
        # does NOT wake the recipient — NPCs shouldn't activate on
        # every incoming ping, only on product-relevant mentions.
        proposed_events.append(
            WordOfMouthEvent(
                event_type="npc.word_of_mouth",
                timestamp=_now_timestamp(),
                actor_id=ActorId(sender_id),
                service_id=ServiceId("npc_chat"),
                action="send_message",
                input_data={"intended_for": [recipient_id]},
                sender_id=ActorId(sender_id),
                recipient_id=ActorId(recipient_id),
                feature_id=feature_mention,
                sentiment=sentiment,
            )
        )

    return ResponseProposal(
        response_body={
            "ok": True,
            "message_id": msg_id,
            "delivered": True,
        },
        proposed_state_deltas=[delta],
        proposed_events=proposed_events,
    )


# -- npc_chat.read_messages ---------------------------------------------------


async def handle_read_messages(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Read the ``limit`` most recent messages addressed to ``recipient_id``.

    Read-only. Returns ``messages`` newest-first so prompt builders can
    slice off the head cheaply. We look up entities via the standard
    ``state.entities`` shape provided by the pipeline's state snapshot;
    no direct store access.
    """
    recipient_id = input_data["recipient_id"]
    limit = int(input_data.get("limit") or 20)
    limit = max(1, min(limit, 100))

    all_messages: list[dict[str, Any]] = []
    entities = state.get("entities", {}) if isinstance(state, dict) else {}
    # ``entities`` is the pipeline-provided snapshot map;
    # ``entities["npc_message"]`` is a list[dict] of message rows.
    for msg in entities.get("npc_message", []) or []:
        if msg.get("recipient_id") == recipient_id:
            all_messages.append(msg)

    all_messages.sort(key=lambda m: m.get("sent_at", 0), reverse=True)
    messages = all_messages[:limit]

    return ResponseProposal(
        response_body={
            "messages": messages,
            "count": len(messages),
        },
        proposed_state_deltas=[],
    )
