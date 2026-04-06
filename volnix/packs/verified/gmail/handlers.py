"""Action handlers for the email service pack.

Each function handles one tool action, producing a ResponseProposal with
any state mutations expressed as StateDelta objects.

Handlers import ONLY from volnix.core (types, context). They NEVER
import from persistence/, engines/, or bus/.

This module contains both Gmail-aligned handlers (handle_messages_*,
handle_drafts_*, handle_labels_*) and legacy email_* handlers for
backward compatibility.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from volnix.core.context import ResponseProposal
from volnix.core.types import EntityId, StateDelta


def _new_id(prefix: str) -> str:
    """Generate a unique ID with the given prefix."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _new_email_id() -> str:
    """Generate a unique email entity ID (full UUID for collision resistance)."""
    return f"email-{uuid.uuid4().hex}"


def _new_thread_id() -> str:
    """Generate a unique thread ID (full UUID for collision resistance)."""
    return f"thread-{uuid.uuid4().hex}"


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------------------
# Gmail-aligned handlers
# ---------------------------------------------------------------------------


async def handle_messages_send(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``users.messages.send`` action.

    Creates a message entity with Gmail-style fields and a corresponding
    thread entity.  Produces two StateDelta creates (message + thread).
    """
    msg_id = _new_id("msg")
    thread_id = _new_id("thread")
    body = input_data["body"]

    message_fields: dict[str, Any] = {
        "id": msg_id,
        "threadId": thread_id,
        "labelIds": ["SENT"],
        "snippet": body[:100],
        "subject": input_data["subject"],
        "body": body,
        "from_addr": input_data.get("from", ""),
        "to_addr": input_data["to"],
        "internalDate": _now_iso(),
        "sizeEstimate": len(body),
    }

    thread_fields: dict[str, Any] = {
        "id": thread_id,
        "snippet": body[:100],
        "messages": [msg_id],
        "historyId": _new_id("history"),
    }

    msg_delta = StateDelta(
        entity_type="gmail_message",
        entity_id=EntityId(msg_id),
        operation="create",
        fields=message_fields,
    )

    thread_delta = StateDelta(
        entity_type="gmail_thread",
        entity_id=EntityId(thread_id),
        operation="create",
        fields=thread_fields,
    )

    return ResponseProposal(
        response_body={
            "id": msg_id,
            "threadId": thread_id,
            "labelIds": ["SENT"],
        },
        proposed_state_deltas=[msg_delta, thread_delta],
    )


async def handle_messages_search(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``users.messages.list`` action.

    Filters state["messages"] by query string (substring in subject, body,
    from_addr, to_addr) and by labelIds intersection.  Paginates via
    maxResults.  No state mutations.
    """
    messages = state.get("messages", [])
    q = input_data.get("q", "").lower()
    label_filter = input_data.get("labelIds")
    max_results = input_data.get("maxResults")

    results: list[dict[str, Any]] = []
    for msg in messages:
        # Query filter: substring match across subject + body + from + to
        if q:
            searchable = " ".join([
                msg.get("subject", ""),
                msg.get("body", ""),
                msg.get("from_addr", ""),
                msg.get("to_addr", ""),
            ]).lower()
            if q not in searchable:
                continue

        # Label filter: message must have at least one of the requested labels
        if label_filter:
            msg_labels = set(msg.get("labelIds", []))
            if not msg_labels.intersection(set(label_filter)):
                continue

        results.append(msg)

    # Paginate
    if max_results is not None:
        results = results[:max_results]

    return ResponseProposal(
        response_body={
            "messages": [{"id": m["id"], "threadId": m.get("threadId", "")} for m in results],
            "resultSizeEstimate": len(results),
        },
    )


async def handle_messages_get(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``users.messages.get`` action.

    Finds a message by ID and returns the full message object.
    No state mutations.
    """
    msg_id = input_data["id"]
    messages = state.get("messages", [])

    for msg in messages:
        if msg.get("id") == msg_id:
            return ResponseProposal(response_body=dict(msg))

    return ResponseProposal(
        response_body={"error": f"Message '{msg_id}' not found"},
    )


async def handle_messages_modify(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``users.messages.modify`` action.

    Adds/removes labels from a message.  Produces a StateDelta update on
    labelIds.
    """
    msg_id = input_data["id"]
    messages = state.get("messages", [])

    target: dict[str, Any] | None = None
    for msg in messages:
        if msg.get("id") == msg_id:
            target = msg
            break

    if target is None:
        return ResponseProposal(
            response_body={"error": f"Message '{msg_id}' not found"},
        )

    current_labels = set(target.get("labelIds", []))
    add_labels = input_data.get("addLabelIds", [])
    remove_labels = input_data.get("removeLabelIds", [])

    new_labels = (current_labels | set(add_labels)) - set(remove_labels)
    new_labels_list = sorted(new_labels)

    delta = StateDelta(
        entity_type="gmail_message",
        entity_id=EntityId(msg_id),
        operation="update",
        fields={"labelIds": new_labels_list},
        previous_fields={"labelIds": sorted(current_labels)},
    )

    updated_msg = {**target, "labelIds": new_labels_list}
    return ResponseProposal(
        response_body=updated_msg,
        proposed_state_deltas=[delta],
    )


async def handle_messages_trash(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``users.messages.trash`` action.

    Adds "TRASH" label and removes "INBOX" if present.  Produces a
    StateDelta update on labelIds.
    """
    msg_id = input_data["id"]
    messages = state.get("messages", [])

    target: dict[str, Any] | None = None
    for msg in messages:
        if msg.get("id") == msg_id:
            target = msg
            break

    if target is None:
        return ResponseProposal(
            response_body={"error": f"Message '{msg_id}' not found"},
        )

    current_labels = set(target.get("labelIds", []))
    new_labels = (current_labels | {"TRASH"}) - {"INBOX"}
    new_labels_list = sorted(new_labels)

    delta = StateDelta(
        entity_type="gmail_message",
        entity_id=EntityId(msg_id),
        operation="update",
        fields={"labelIds": new_labels_list},
        previous_fields={"labelIds": sorted(current_labels)},
    )

    updated_msg = {**target, "labelIds": new_labels_list}
    return ResponseProposal(
        response_body=updated_msg,
        proposed_state_deltas=[delta],
    )


async def handle_messages_delete(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``users.messages.delete`` action.

    Permanently deletes a message.  Produces a StateDelta delete.
    """
    msg_id = input_data["id"]
    messages = state.get("messages", [])

    target: dict[str, Any] | None = None
    for msg in messages:
        if msg.get("id") == msg_id:
            target = msg
            break

    if target is None:
        return ResponseProposal(
            response_body={"error": f"Message '{msg_id}' not found"},
        )

    delta = StateDelta(
        entity_type="gmail_message",
        entity_id=EntityId(msg_id),
        operation="delete",
        fields=dict(target),
    )

    return ResponseProposal(
        response_body={"deleted": True},
        proposed_state_deltas=[delta],
    )


async def handle_drafts_create(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``users.drafts.create`` action.

    Creates a draft entity.  Produces a StateDelta create on "draft" type.
    """
    draft_id = _new_id("draft")

    draft_fields: dict[str, Any] = {
        "id": draft_id,
        "to": input_data["to"],
        "subject": input_data["subject"],
        "body": input_data["body"],
    }

    delta = StateDelta(
        entity_type="gmail_draft",
        entity_id=EntityId(draft_id),
        operation="create",
        fields=draft_fields,
    )

    return ResponseProposal(
        response_body={
            "id": draft_id,
            "message": draft_fields,
        },
        proposed_state_deltas=[delta],
    )


async def handle_labels_list(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``users.labels.list`` action.

    Returns labels from state.  No state mutations.
    """
    labels = state.get("labels", [])

    return ResponseProposal(
        response_body={"labels": labels},
    )


# ---------------------------------------------------------------------------
# Legacy email_* handlers (backward compatibility)
# ---------------------------------------------------------------------------


async def handle_email_send(input_data: dict[str, Any], state: dict[str, Any]) -> ResponseProposal:
    """Handle the ``email_send`` action.

    Creates an email entity with status="delivered", generates unique
    email_id and thread_id.
    """
    email_id = _new_email_id()
    thread_id = _new_thread_id()
    timestamp = _now_iso()

    email_fields = {
        "email_id": email_id,
        "from_addr": input_data["from_addr"],
        "to_addr": input_data["to_addr"],
        "subject": input_data["subject"],
        "body": input_data["body"],
        "status": "delivered",
        "thread_id": thread_id,
        "timestamp": timestamp,
    }

    delta = StateDelta(
        entity_type="email",
        entity_id=EntityId(email_id),
        operation="create",
        fields=email_fields,
    )

    return ResponseProposal(
        response_body={
            "status": "sent",
            "email_id": email_id,
            "thread_id": thread_id,
            "timestamp": timestamp,
        },
        proposed_state_deltas=[delta],
    )


async def handle_email_list(input_data: dict[str, Any], state: dict[str, Any]) -> ResponseProposal:
    """Handle the ``email_list`` action.

    Filters state["emails"] by mailbox_owner and optional status_filter/limit.
    No state mutations.
    """
    emails = state.get("emails", [])
    mailbox_owner = input_data["mailbox_owner"]

    # Filter by owner (recipient)
    filtered = [e for e in emails if e.get("to_addr") == mailbox_owner]

    # Optional status filter
    status_filter = input_data.get("status_filter")
    if status_filter:
        filtered = [e for e in filtered if e.get("status") == status_filter]

    # Optional limit
    limit = input_data.get("limit")
    if limit is not None:
        filtered = filtered[:limit]

    return ResponseProposal(
        response_body={
            "emails": filtered,
            "count": len(filtered),
        },
    )


async def handle_email_read(input_data: dict[str, Any], state: dict[str, Any]) -> ResponseProposal:
    """Handle the ``email_read`` action.

    Finds email in state, transitions "delivered" -> "read" via StateDelta(update).
    """
    email_id = input_data["email_id"]
    emails = state.get("emails", [])

    email = None
    for e in emails:
        if e.get("email_id") == email_id:
            email = e
            break

    if email is None:
        return ResponseProposal(
            response_body={"error": f"Email '{email_id}' not found"},
        )

    deltas: list[StateDelta] = []
    old_status = email.get("status")

    # Transition delivered -> read
    if old_status == "delivered":
        deltas.append(
            StateDelta(
                entity_type="email",
                entity_id=EntityId(email_id),
                operation="update",
                fields={"status": "read"},
                previous_fields={"status": old_status},
            )
        )

    # Return email with updated status in response (not stale pre-transition state)
    response_email = {**email}
    if deltas:
        response_email["status"] = "read"
    return ResponseProposal(
        response_body={
            "email": response_email,
        },
        proposed_state_deltas=deltas,
    )


async def handle_email_search(
    input_data: dict[str, Any], state: dict[str, Any]
) -> ResponseProposal:
    """Handle the ``email_search`` action.

    Filters by query/sender/subject. No state mutations.
    """
    emails = state.get("emails", [])
    query = input_data.get("query", "").lower()
    sender = input_data.get("sender", "")
    subject_filter = input_data.get("subject", "")

    results = []
    for e in emails:
        if sender and e.get("from_addr") != sender:
            continue
        if subject_filter and subject_filter.lower() not in e.get("subject", "").lower():
            continue
        if query:
            searchable = " ".join([
                e.get("subject", ""),
                e.get("body", ""),
                e.get("from_addr", ""),
                e.get("to_addr", ""),
            ]).lower()
            if query not in searchable:
                continue
        results.append(e)

    return ResponseProposal(
        response_body={
            "results": results,
            "count": len(results),
        },
    )


async def handle_email_reply(
    input_data: dict[str, Any], state: dict[str, Any]
) -> ResponseProposal:
    """Handle the ``email_reply`` action.

    Finds original email, creates reply with in_reply_to and thread_id.
    """
    original_email_id = input_data["email_id"]
    emails = state.get("emails", [])

    original = None
    for e in emails:
        if e.get("email_id") == original_email_id:
            original = e
            break

    if original is None:
        return ResponseProposal(
            response_body={"error": f"Original email '{original_email_id}' not found"},
        )

    reply_id = _new_email_id()
    thread_id = original.get("thread_id", _new_thread_id())
    timestamp = _now_iso()

    reply_fields = {
        "email_id": reply_id,
        "from_addr": input_data["from_addr"],
        "to_addr": original["from_addr"],
        "subject": (
            original.get("subject", "")
            if original.get("subject", "").startswith("Re: ")
            else f"Re: {original.get('subject', '')}"
        ),
        "body": input_data["body"],
        "status": "delivered",
        "thread_id": thread_id,
        "in_reply_to": original_email_id,
        "timestamp": timestamp,
    }

    delta = StateDelta(
        entity_type="email",
        entity_id=EntityId(reply_id),
        operation="create",
        fields=reply_fields,
    )

    return ResponseProposal(
        response_body={
            "status": "sent",
            "email_id": reply_id,
            "thread_id": thread_id,
            "in_reply_to": original_email_id,
            "timestamp": timestamp,
        },
        proposed_state_deltas=[delta],
    )


async def handle_email_mark_read(
    input_data: dict[str, Any], state: dict[str, Any]
) -> ResponseProposal:
    """Handle the ``email_mark_read`` action.

    Batch transitions for email_ids list.
    """
    email_ids = input_data["email_ids"]
    emails = state.get("emails", [])

    # Build lookup
    email_map = {e["email_id"]: e for e in emails if "email_id" in e}

    deltas: list[StateDelta] = []
    marked: list[str] = []
    not_found: list[str] = []

    for eid in email_ids:
        email = email_map.get(eid)
        if email is None:
            not_found.append(eid)
            continue

        old_status = email.get("status")
        if old_status == "delivered":
            deltas.append(
                StateDelta(
                    entity_type="email",
                    entity_id=EntityId(eid),
                    operation="update",
                    fields={"status": "read"},
                    previous_fields={"status": old_status},
                )
            )
            marked.append(eid)
        elif old_status == "read":
            # Already read -- no-op
            marked.append(eid)
        else:
            # Other statuses -- still note them as processed
            marked.append(eid)

    return ResponseProposal(
        response_body={
            "marked": marked,
            "not_found": not_found,
        },
        proposed_state_deltas=deltas,
    )
