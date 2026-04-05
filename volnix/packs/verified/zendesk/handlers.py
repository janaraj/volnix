"""Action handlers for the tickets service pack.

Each function handles one tool action, producing a ResponseProposal with
any state mutations expressed as StateDelta objects.

Handlers import ONLY from volnix.core (types, context). They NEVER
import from persistence/, engines/, or bus/.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from volnix.core.context import ResponseProposal
from volnix.core.types import EntityId, StateDelta

# ---------------------------------------------------------------------------
# Zendesk-style error response helper
# ---------------------------------------------------------------------------


def _zd_error(error: str, description: str) -> dict[str, Any]:
    """Return a Zendesk-format error response body."""
    return {
        "error": error,
        "description": description,
    }


def _new_id(prefix: str) -> str:
    """Generate a unique entity ID with the given prefix."""
    return f"{prefix}-{uuid.uuid4().hex}"


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


async def handle_tickets_create(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``tickets_create`` action.

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
        "html_body": f"<p>{input_data['description']}</p>",
        "public": True,
        "attachments": [],
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


async def handle_tickets_update(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``tickets_update`` action.

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
            response_body=_zd_error("RecordNotFound", f"Ticket '{ticket_id}' not found"),
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


async def handle_tickets_delete(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``tickets_delete`` action.

    Soft-deletes a ticket by marking it with status="deleted".
    Zendesk does not truly destroy tickets on DELETE -- they become
    recoverable soft-deletes. We model this as a status update.
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
            response_body=_zd_error("RecordNotFound", f"Ticket '{ticket_id}' not found"),
        )

    now = _now_iso()
    old_status = ticket.get("status", "new")

    delta = StateDelta(
        entity_type="ticket",
        entity_id=EntityId(ticket_id),
        operation="delete",
        fields={"status": "deleted", "updated_at": now},
        previous_fields={"status": old_status},
    )

    return ResponseProposal(
        response_body={},
        proposed_state_deltas=[delta],
    )


async def handle_tickets_search(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``tickets_search`` action.

    Searches tickets by matching the query string (case-insensitive)
    against subject, description, and tags. Supports basic Zendesk
    search syntax: ``status:open``, ``priority:urgent``, ``assignee_id:X``,
    ``requester_id:X``, ``type:problem``, and free-text fallback.
    Paginates with per_page/page.
    """
    query = input_data["query"]
    tickets = list(state.get("tickets", []))

    # Parse structured filters from query.
    # Supports OR: "status:new OR status:open" → match any value.
    # Multiple values for the same key are collected into a set.
    filters: dict[str, set[str]] = {}
    free_text_parts: list[str] = []
    for token in query.split():
        if token.upper() in ("OR", "AND", "NOT"):
            continue  # Strip boolean operators
        if ":" in token:
            key, value = token.split(":", 1)
            filters.setdefault(key, set()).add(value)
        else:
            free_text_parts.append(token)

    free_text = " ".join(free_text_parts).lower()

    # Apply structured filters (multi-value uses "in")
    if "status" in filters:
        tickets = [t for t in tickets if t.get("status") in filters["status"]]
    if "priority" in filters:
        tickets = [t for t in tickets if t.get("priority") in filters["priority"]]
    if "assignee_id" in filters:
        tickets = [t for t in tickets if t.get("assignee_id") in filters["assignee_id"]]
    if "requester_id" in filters:
        tickets = [t for t in tickets if t.get("requester_id") in filters["requester_id"]]
    if "type" in filters:
        tickets = [t for t in tickets if t.get("type") in filters["type"]]

    # Apply free-text search if present
    if free_text:
        results = []
        for t in tickets:
            searchable = " ".join(
                [
                    t.get("subject", ""),
                    t.get("description", ""),
                    " ".join(t.get("tags", [])),
                ]
            ).lower()
            if free_text in searchable:
                results.append(t)
        tickets = results

    # Pagination
    per_page = input_data.get("per_page", 100)
    page = input_data.get("page", 1)
    if page is None:
        page = 1
    start = (page - 1) * per_page
    end = start + per_page
    paginated = tickets[start:end]

    return ResponseProposal(
        response_body={
            "results": paginated,
            "count": len(paginated),
            "next_page": page + 1 if end < len(tickets) else None,
        },
    )


async def handle_tickets_list(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``tickets_list`` action.

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


async def handle_tickets_show(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``tickets_show`` action.

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
        response_body=_zd_error("RecordNotFound", f"Ticket '{ticket_id}' not found"),
    )


async def handle_ticket_comments_create(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``ticket_comments_create`` action.

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
            response_body=_zd_error("RecordNotFound", f"Ticket '{ticket_id}' not found"),
        )

    comment_id = _new_id("comment")
    now = _now_iso()

    body = input_data["body"]
    comment_fields: dict[str, Any] = {
        "id": comment_id,
        "ticket_id": ticket_id,
        "author_id": input_data["author_id"],
        "body": body,
        "html_body": f"<p>{body}</p>",
        "public": input_data.get("public", True),
        "attachments": [],
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


async def handle_ticket_comments_list(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``ticket_comments_list`` action.

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


async def handle_users_list(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``users_list`` action.

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


async def handle_users_show(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``users_show`` action.

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
        response_body=_zd_error("RecordNotFound", f"User '{user_id}' not found"),
    )


async def handle_groups_list(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``groups_list`` action.

    Returns all groups from state["groups"]. Supports pagination. No state mutations.
    """
    groups = list(state.get("groups", []))

    # Pagination
    per_page = input_data.get("per_page", 100)
    page = input_data.get("page", 1)
    if page is None:
        page = 1
    start = (page - 1) * per_page
    end = start + per_page
    paginated = groups[start:end]

    return ResponseProposal(
        response_body={
            "groups": paginated,
            "count": len(paginated),
            "next_page": page + 1 if end < len(groups) else None,
        },
    )


async def handle_groups_show(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``groups_show`` action.

    Finds a single group by ID. No state mutations.
    """
    group_id = input_data["id"]
    groups = state.get("groups", [])

    for g in groups:
        if g.get("id") == group_id:
            return ResponseProposal(
                response_body={"group": g},
            )

    return ResponseProposal(
        response_body=_zd_error("RecordNotFound", f"Group '{group_id}' not found"),
    )
