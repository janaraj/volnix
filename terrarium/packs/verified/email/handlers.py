"""Action handlers for the email service pack.

Each function handles one tool action, producing a ResponseProposal with
any state mutations expressed as StateDelta objects.

Handlers import ONLY from terrarium.core (types, context). They NEVER
import from persistence/, engines/, or bus/.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from terrarium.core.context import ResponseProposal
from terrarium.core.types import EntityId, StateDelta


def _new_email_id() -> str:
    """Generate a unique email entity ID (full UUID for collision resistance)."""
    return f"email-{uuid.uuid4().hex}"


def _new_thread_id() -> str:
    """Generate a unique thread ID (full UUID for collision resistance)."""
    return f"thread-{uuid.uuid4().hex}"


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


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


async def handle_email_search(input_data: dict[str, Any], state: dict[str, Any]) -> ResponseProposal:
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


async def handle_email_reply(input_data: dict[str, Any], state: dict[str, Any]) -> ResponseProposal:
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
        "subject": original.get("subject", "") if original.get("subject", "").startswith("Re: ") else f"Re: {original.get('subject', '')}",
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


async def handle_email_mark_read(input_data: dict[str, Any], state: dict[str, Any]) -> ResponseProposal:
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
