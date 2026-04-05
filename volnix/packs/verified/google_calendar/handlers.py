"""Action handlers for the calendar service pack.

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
# Google Calendar-style error response helper
# ---------------------------------------------------------------------------


def _gcal_error(code: int, message: str) -> dict[str, Any]:
    """Return a Google Calendar-format error response body."""
    return {
        "error": {
            "code": code,
            "message": message,
            "errors": [
                {
                    "domain": "calendar",
                    "reason": "notFound" if code == 404 else "invalid",
                    "message": message,
                }
            ],
        }
    }


def _new_id(prefix: str) -> str:
    """Generate a unique ID with the given prefix."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).isoformat()


def _new_etag() -> str:
    """Generate a new ETag value."""
    return f'"{uuid.uuid4().hex[:16]}"'


def _get_event_datetime(event: dict[str, Any]) -> str:
    """Extract the dateTime or date string from an event's start field."""
    start = event.get("start", {})
    return start.get("dateTime", start.get("date", ""))


async def handle_create_calendar_event(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``events.insert`` action.

    Creates an event entity with status="confirmed", generates unique id.
    Also creates attendee entities for each attendee in input.attendees.
    Produces 1 event create delta + N attendee create deltas.
    """
    event_id = _new_id("evt")
    now = _now_iso()
    etag = _new_etag()

    event_fields: dict[str, Any] = {
        "id": event_id,
        "etag": etag,
        "kind": "calendar#event",
        "iCalUID": f"{event_id}@google.com",
        "summary": input_data["summary"],
        "description": input_data.get("description", ""),
        "location": input_data.get("location", ""),
        "start": input_data["start"],
        "end": input_data["end"],
        "status": "confirmed",
        "transparency": "opaque",
        "visibility": "default",
        "organizer": input_data.get("organizer", {}),
        "attendees": [],
        "guestsCanModify": False,
        "guestsCanInviteOthers": True,
        "guestsCanSeeOtherGuests": True,
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
            "comment": "",
            "additionalGuests": 0,
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
    """Handle the ``events.list`` action.

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
    """Handle the ``events.get`` action.

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
            response_body=_gcal_error(404, f"Event '{event_id}' not found"),
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
    """Handle the ``events.update`` action.

    Finds event by id and updates provided fields.  For status changes,
    includes previous_fields.  If attendees are provided, checks for
    existing attendees by event_id+email to UPDATE instead of CREATE
    (fixes attendee duplication bug).  Produces 1 event update delta +
    N attendee create/update deltas.
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
            response_body=_gcal_error(404, f"Event '{event_id}' not found"),
        )

    now = _now_iso()

    # Build the update fields
    update_fields: dict[str, Any] = {"updated": now, "etag": _new_etag()}
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

    # If attendees are provided, check for duplicates before creating
    input_attendees = input_data.get("attendees", [])
    existing_attendees = state.get("attendees", [])
    attendee_records: list[dict[str, Any]] = []

    # Build lookup of existing attendees by (event_id, email)
    existing_by_email: dict[str, dict[str, Any]] = {}
    for att in existing_attendees:
        if att.get("event_id") == event_id:
            existing_by_email[att.get("email", "")] = att

    for att in input_attendees:
        email = att["email"]
        existing_att = existing_by_email.get(email)

        if existing_att is not None:
            # UPDATE existing attendee instead of creating a duplicate
            att_id = existing_att["id"]
            att_update_fields: dict[str, Any] = {}
            att_prev_fields: dict[str, Any] = {}

            if att.get("displayName") and att["displayName"] != existing_att.get("displayName"):
                att_prev_fields["displayName"] = existing_att.get("displayName", "")
                att_update_fields["displayName"] = att["displayName"]

            # Reset responseStatus to needsAction on re-invite
            att_update_fields["responseStatus"] = "needsAction"
            att_prev_fields["responseStatus"] = existing_att.get("responseStatus", "needsAction")

            if att_update_fields:
                deltas.append(
                    StateDelta(
                        entity_type="attendee",
                        entity_id=EntityId(att_id),
                        operation="update",
                        fields=att_update_fields,
                        previous_fields=att_prev_fields if att_prev_fields else None,
                    ),
                )
            attendee_records.append({**existing_att, **att_update_fields})
        else:
            # CREATE new attendee
            att_id = _new_id("att")
            att_fields: dict[str, Any] = {
                "id": att_id,
                "event_id": event_id,
                "email": email,
                "displayName": att.get("displayName", ""),
                "responseStatus": "needsAction",
                "optional": att.get("optional", False),
                "organizer": att.get("organizer", False),
                "comment": "",
                "additionalGuests": 0,
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
    """Handle the ``events.delete`` action.

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
            response_body=_gcal_error(404, f"Event '{event_id}' not found"),
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
    """Handle the ``events.search`` action.

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
        searchable = " ".join(
            [
                e.get("summary", ""),
                e.get("description", ""),
            ]
        ).lower()
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
    """Handle the ``calendarList.list`` action.

    Returns all calendars from state.  No state mutations.
    """
    calendars = state.get("calendars", [])

    return ResponseProposal(
        response_body={
            "kind": "calendar#calendarList",
            "items": calendars,
        },
    )


async def handle_get_calendar(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``calendarList.get`` action.

    Finds a single calendar by ID. No state mutations.
    """
    calendar_id = input_data["calendarId"]
    calendars = state.get("calendars", [])

    for cal in calendars:
        if cal.get("id") == calendar_id:
            return ResponseProposal(response_body=cal)

    return ResponseProposal(
        response_body=_gcal_error(404, f"Calendar '{calendar_id}' not found"),
    )


async def handle_rsvp_calendar_event(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    """Handle the ``events.patch`` action.

    Finds the attendee by event_id + email and updates their responseStatus.
    Valid statuses: accepted, declined, tentative.
    """
    event_id = input_data["eventId"]
    email = input_data["email"]
    new_status = input_data["responseStatus"]

    # Verify event exists
    events = state.get("events", [])
    event: dict[str, Any] | None = None
    for e in events:
        if e.get("id") == event_id:
            event = e
            break

    if event is None:
        return ResponseProposal(
            response_body=_gcal_error(404, f"Event '{event_id}' not found"),
        )

    # Find the attendee
    attendees = state.get("attendees", [])
    target_att: dict[str, Any] | None = None
    for att in attendees:
        if att.get("event_id") == event_id and att.get("email") == email:
            target_att = att
            break

    if target_att is None:
        return ResponseProposal(
            response_body=_gcal_error(404, f"Attendee '{email}' not found for event '{event_id}'"),
        )

    old_status = target_att.get("responseStatus", "needsAction")

    delta = StateDelta(
        entity_type="attendee",
        entity_id=EntityId(target_att["id"]),
        operation="update",
        fields={"responseStatus": new_status},
        previous_fields={"responseStatus": old_status},
    )

    response_att = {**target_att, "responseStatus": new_status}

    return ResponseProposal(
        response_body=response_att,
        proposed_state_deltas=[delta],
    )
