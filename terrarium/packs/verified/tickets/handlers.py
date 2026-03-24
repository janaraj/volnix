"""Action handlers for the tickets service pack.

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
    """Generate a unique entity ID with the given prefix."""
    return f"{prefix}-{uuid.uuid4().hex}"


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


async def handle_zendesk_tickets_create(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``zendesk_tickets_create`` action.

    Creates a ticket entity with status="new" and an initial comment
    derived from the ticket description. Produces two StateDelta creates:
    one for the ticket and one for the initial comment.
    """
    ticket_id = _new_id("ticket")
    comment_id = _new_id("comment")
    now = _now_iso()

    ticket_fields: dict[str, Any] = {
        "id": ticket_id,
        "subject": input_data["subject"],
        "description": input_data["description"],
        "status": "new",
        "requester_id": input_data["requester_id"],
        "created_at": now,
        "updated_at": now,
    }

    # Optional fields
    if "priority" in input_data:
        ticket_fields["priority"] = input_data["priority"]
    if "type" in input_data:
        ticket_fields["type"] = input_data["type"]
    if "assignee_id" in input_data:
        ticket_fields["assignee_id"] = input_data["assignee_id"]
    if "tags" in input_data:
        ticket_fields["tags"] = input_data["tags"]

    ticket_delta = StateDelta(
        entity_type="ticket",
        entity_id=EntityId(ticket_id),
        operation="create",
        fields=ticket_fields,
    )

    # Initial comment from description
    comment_fields: dict[str, Any] = {
        "id": comment_id,
        "ticket_id": ticket_id,
        "author_id": input_data["requester_id"],
        "body": input_data["description"],
        "public": True,
        "created_at": now,
    }

    comment_delta = StateDelta(
        entity_type="comment",
        entity_id=EntityId(comment_id),
        operation="create",
        fields=comment_fields,
    )

    return ResponseProposal(
        response_body={"ticket": ticket_fields},
        proposed_state_deltas=[ticket_delta, comment_delta],
    )


async def handle_zendesk_tickets_update(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``zendesk_tickets_update`` action.

    Finds the ticket by ID and applies field updates. For status changes,
    records previous_fields. Always bumps updated_at.
    """
    ticket_id = input_data["id"]
    tickets = state.get("tickets", [])

    ticket = None
    for t in tickets:
        if t.get("id") == ticket_id:
            ticket = t
            break

    if ticket is None:
        return ResponseProposal(
            response_body={"error": f"Ticket '{ticket_id}' not found"},
        )

    updated_fields: dict[str, Any] = {}
    previous_fields: dict[str, Any] = {}

    for field in ("status", "assignee_id", "priority", "tags"):
        if field in input_data:
            old_value = ticket.get(field)
            new_value = input_data[field]
            if old_value != new_value:
                updated_fields[field] = new_value
                previous_fields[field] = old_value

    now = _now_iso()
    updated_fields["updated_at"] = now

    delta = StateDelta(
        entity_type="ticket",
        entity_id=EntityId(ticket_id),
        operation="update",
        fields=updated_fields,
        previous_fields=previous_fields if previous_fields else None,
    )

    # Build response with merged ticket data
    response_ticket = {**ticket, **updated_fields}

    return ResponseProposal(
        response_body={"ticket": response_ticket},
        proposed_state_deltas=[delta],
    )


async def handle_zendesk_tickets_list(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``zendesk_tickets_list`` action.

    Filters state["tickets"] by status, assignee_id, and requester_id.
    Supports pagination via page and per_page. No state mutations.
    """
    tickets = state.get("tickets", [])

    # Apply filters
    status_filter = input_data.get("status")
    if status_filter:
        tickets = [t for t in tickets if t.get("status") == status_filter]

    assignee_filter = input_data.get("assignee_id")
    if assignee_filter:
        tickets = [t for t in tickets if t.get("assignee_id") == assignee_filter]

    requester_filter = input_data.get("requester_id")
    if requester_filter:
        tickets = [t for t in tickets if t.get("requester_id") == requester_filter]

    # Pagination
    per_page = input_data.get("per_page", 100)
    page = input_data.get("page", 1)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = tickets[start:end]

    return ResponseProposal(
        response_body={
            "tickets": paginated,
            "count": len(paginated),
            "next_page": page + 1 if end < len(tickets) else None,
        },
    )


async def handle_zendesk_tickets_show(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``zendesk_tickets_show`` action.

    Finds a single ticket by ID. No state mutations.
    """
    ticket_id = input_data["id"]
    tickets = state.get("tickets", [])

    for t in tickets:
        if t.get("id") == ticket_id:
            return ResponseProposal(
                response_body={"ticket": t},
            )

    return ResponseProposal(
        response_body={"error": f"Ticket '{ticket_id}' not found"},
    )


async def handle_zendesk_ticket_comments_create(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``zendesk_ticket_comments_create`` action.

    Creates a comment entity and updates the parent ticket's updated_at.
    Produces two StateDelta objects.
    """
    ticket_id = input_data["id"]
    tickets = state.get("tickets", [])

    # Verify ticket exists
    ticket = None
    for t in tickets:
        if t.get("id") == ticket_id:
            ticket = t
            break

    if ticket is None:
        return ResponseProposal(
            response_body={"error": f"Ticket '{ticket_id}' not found"},
        )

    comment_id = _new_id("comment")
    now = _now_iso()

    comment_fields: dict[str, Any] = {
        "id": comment_id,
        "ticket_id": ticket_id,
        "author_id": input_data["author_id"],
        "body": input_data["body"],
        "public": input_data.get("public", True),
        "created_at": now,
    }

    comment_delta = StateDelta(
        entity_type="comment",
        entity_id=EntityId(comment_id),
        operation="create",
        fields=comment_fields,
    )

    # Also update the ticket's updated_at timestamp
    ticket_delta = StateDelta(
        entity_type="ticket",
        entity_id=EntityId(ticket_id),
        operation="update",
        fields={"updated_at": now},
    )

    return ResponseProposal(
        response_body={"comment": comment_fields},
        proposed_state_deltas=[comment_delta, ticket_delta],
    )


async def handle_zendesk_ticket_comments_list(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``zendesk_ticket_comments_list`` action.

    Filters state["comments"] by ticket_id. No state mutations.
    """
    ticket_id = input_data["id"]
    comments = state.get("comments", [])

    filtered = [c for c in comments if c.get("ticket_id") == ticket_id]

    return ResponseProposal(
        response_body={
            "comments": filtered,
            "count": len(filtered),
        },
    )


async def handle_zendesk_users_list(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``zendesk_users_list`` action.

    Filters state["users"] by role. Supports pagination. No state mutations.
    """
    users = state.get("users", [])

    role_filter = input_data.get("role")
    if role_filter:
        users = [u for u in users if u.get("role") == role_filter]

    # Pagination
    per_page = input_data.get("per_page", 100)
    page = input_data.get("page", 1)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = users[start:end]

    return ResponseProposal(
        response_body={
            "users": paginated,
            "count": len(paginated),
            "next_page": page + 1 if end < len(users) else None,
        },
    )


async def handle_zendesk_users_show(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``zendesk_users_show`` action.

    Finds a single user by ID. No state mutations.
    """
    user_id = input_data["id"]
    users = state.get("users", [])

    for u in users:
        if u.get("id") == user_id:
            return ResponseProposal(
                response_body={"user": u},
            )

    return ResponseProposal(
        response_body={"error": f"User '{user_id}' not found"},
    )
