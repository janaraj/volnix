"""Action handlers for the calendar service pack.

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


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _get_event_datetime(event: dict[str, Any]) -> str:
    """Extract the dateTime or date string from an event's start field."""
    start = event.get("start", {})
    return start.get("dateTime", start.get("date", ""))


async def handle_create_calendar_event(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``create_calendar_event`` action.

    Creates an event entity with status="confirmed", generates unique id.
    Also creates attendee entities for each attendee in input.attendees.
    Produces 1 event create delta + N attendee create deltas.
    """
    event_id = _new_id("evt")
    now = _now_iso()

    event_fields: dict[str, Any] = {
        "id": event_id,
        "summary": input_data["summary"],
        "description": input_data.get("description", ""),
        "location": input_data.get("location", ""),
        "start": input_data["start"],
        "end": input_data["end"],
        "status": "confirmed",
        "organizer": input_data.get("organizer", {}),
        "attendees": [],
        "recurrence": [],
        "reminders": {"useDefault": True, "overrides": []},
        "created": now,
        "updated": now,
        "calendarId": input_data["calendarId"],
    }

    deltas: list[StateDelta] = [
        StateDelta(
            entity_type="event",
            entity_id=EntityId(event_id),
            operation="create",
            fields=event_fields,
        ),
    ]

    # Create attendee entities for each attendee in input
    input_attendees = input_data.get("attendees", [])
    attendee_records: list[dict[str, Any]] = []
    for att in input_attendees:
        att_id = _new_id("att")
        att_fields: dict[str, Any] = {
            "id": att_id,
            "event_id": event_id,
            "email": att["email"],
            "displayName": att.get("displayName", ""),
            "responseStatus": "needsAction",
            "optional": att.get("optional", False),
            "organizer": att.get("organizer", False),
        }
        deltas.append(
            StateDelta(
                entity_type="attendee",
                entity_id=EntityId(att_id),
                operation="create",
                fields=att_fields,
            ),
        )
        attendee_records.append(att_fields)

    # Embed attendees in the event for the response
    event_fields["attendees"] = attendee_records

    return ResponseProposal(
        response_body=event_fields,
        proposed_state_deltas=deltas,
    )


async def handle_list_calendar_events(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``list_calendar_events`` action.

    Filters state["events"] by calendarId, optional timeMin/timeMax, and
    paginates via maxResults.  No state mutations.
    """
    events = state.get("events", [])
    calendar_id = input_data["calendarId"]

    # Filter by calendarId
    filtered = [e for e in events if e.get("calendarId") == calendar_id]

    # Optional time range filtering (ISO string comparison)
    time_min = input_data.get("timeMin")
    if time_min:
        filtered = [e for e in filtered if _get_event_datetime(e) >= time_min]

    time_max = input_data.get("timeMax")
    if time_max:
        filtered = [e for e in filtered if _get_event_datetime(e) < time_max]

    # Paginate via maxResults
    max_results = input_data.get("maxResults", 250)
    limited = filtered[:max_results]

    return ResponseProposal(
        response_body={
            "kind": "calendar#events",
            "items": limited,
        },
    )


async def handle_get_calendar_event(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``get_calendar_event`` action.

    Finds event by id and attaches attendees from state["attendees"].
    No state mutations.
    """
    event_id = input_data["eventId"]
    events = state.get("events", [])

    event: dict[str, Any] | None = None
    for e in events:
        if e.get("id") == event_id:
            event = e
            break

    if event is None:
        return ResponseProposal(
            response_body={"error": f"Event '{event_id}' not found"},
        )

    # Attach attendees from state
    attendees = state.get("attendees", [])
    event_attendees = [a for a in attendees if a.get("event_id") == event_id]

    response_event = {**event, "attendees": event_attendees}

    return ResponseProposal(
        response_body=response_event,
    )


async def handle_update_calendar_event(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``update_calendar_event`` action.

    Finds event by id and updates provided fields.  For status changes,
    includes previous_fields.  If attendees are provided, creates new
    attendee entities.  Produces 1 event update delta + N attendee create deltas.
    """
    event_id = input_data["eventId"]
    events = state.get("events", [])

    event: dict[str, Any] | None = None
    for e in events:
        if e.get("id") == event_id:
            event = e
            break

    if event is None:
        return ResponseProposal(
            response_body={"error": f"Event '{event_id}' not found"},
        )

    now = _now_iso()

    # Build the update fields
    update_fields: dict[str, Any] = {"updated": now}
    previous_fields: dict[str, Any] = {}

    updatable_keys = ["summary", "description", "location", "start", "end", "status"]
    for key in updatable_keys:
        if key in input_data:
            update_fields[key] = input_data[key]
            if key in event:
                previous_fields[key] = event[key]

    deltas: list[StateDelta] = [
        StateDelta(
            entity_type="event",
            entity_id=EntityId(event_id),
            operation="update",
            fields=update_fields,
            previous_fields=previous_fields if previous_fields else None,
        ),
    ]

    # If attendees are provided, create new attendee entities
    input_attendees = input_data.get("attendees", [])
    attendee_records: list[dict[str, Any]] = []
    for att in input_attendees:
        att_id = _new_id("att")
        att_fields: dict[str, Any] = {
            "id": att_id,
            "event_id": event_id,
            "email": att["email"],
            "displayName": att.get("displayName", ""),
            "responseStatus": "needsAction",
            "optional": att.get("optional", False),
            "organizer": att.get("organizer", False),
        }
        deltas.append(
            StateDelta(
                entity_type="attendee",
                entity_id=EntityId(att_id),
                operation="create",
                fields=att_fields,
            ),
        )
        attendee_records.append(att_fields)

    # Build response with updated fields
    response_event = {**event, **update_fields}
    if attendee_records:
        response_event["attendees"] = attendee_records

    return ResponseProposal(
        response_body=response_event,
        proposed_state_deltas=deltas,
    )


async def handle_delete_calendar_event(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``delete_calendar_event`` action.

    Sets event status to "cancelled" via update (Google Calendar keeps
    cancelled events rather than truly deleting them).
    """
    event_id = input_data["eventId"]
    events = state.get("events", [])

    event: dict[str, Any] | None = None
    for e in events:
        if e.get("id") == event_id:
            event = e
            break

    if event is None:
        return ResponseProposal(
            response_body={"error": f"Event '{event_id}' not found"},
        )

    now = _now_iso()
    old_status = event.get("status", "confirmed")

    delta = StateDelta(
        entity_type="event",
        entity_id=EntityId(event_id),
        operation="update",
        fields={"status": "cancelled", "updated": now},
        previous_fields={"status": old_status},
    )

    response_event = {**event, "status": "cancelled", "updated": now}

    return ResponseProposal(
        response_body=response_event,
        proposed_state_deltas=[delta],
    )


async def handle_search_calendar_events(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``search_calendar_events`` action.

    Filters events where q appears in summary or description (case-insensitive).
    Paginates via maxResults.  No state mutations.
    """
    events = state.get("events", [])
    calendar_id = input_data["calendarId"]
    query = input_data["q"].lower()

    # Filter by calendarId first, then by query
    filtered = [e for e in events if e.get("calendarId") == calendar_id]
    results = []
    for e in filtered:
        searchable = " ".join([
            e.get("summary", ""),
            e.get("description", ""),
        ]).lower()
        if query in searchable:
            results.append(e)

    # Paginate via maxResults
    max_results = input_data.get("maxResults", 250)
    limited = results[:max_results]

    return ResponseProposal(
        response_body={
            "kind": "calendar#events",
            "items": limited,
        },
    )


async def handle_list_calendars(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``list_calendars`` action.

    Returns all calendars from state.  No state mutations.
    """
    calendars = state.get("calendars", [])

    return ResponseProposal(
        response_body={
            "kind": "calendar#calendarList",
            "items": calendars,
        },
    )
