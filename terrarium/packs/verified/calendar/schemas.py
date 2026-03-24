"""Entity schemas and tool definitions for the calendar service pack.

Pure data -- no logic, no imports beyond stdlib.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------

EVENT_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "summary", "start", "end", "status", "created", "updated"],
    "properties": {
        "id": {"type": "string"},
        "etag": {"type": "string"},
        "kind": {"type": "string", "enum": ["calendar#event"]},
        "iCalUID": {"type": "string"},
        "recurringEventId": {"type": "string"},
        "summary": {"type": "string"},
        "description": {"type": ["string", "null"]},
        "location": {"type": ["string", "null"]},
        "start": {
            "type": "object",
            "properties": {
                "dateTime": {"type": "string"},
                "date": {"type": "string"},
                "timeZone": {"type": "string"},
            },
        },
        "end": {
            "type": "object",
            "properties": {
                "dateTime": {"type": "string"},
                "date": {"type": "string"},
                "timeZone": {"type": "string"},
            },
        },
        "status": {
            "type": "string",
            "enum": ["confirmed", "tentative", "cancelled"],
        },
        "transparency": {
            "type": "string",
            "enum": ["opaque", "transparent"],
        },
        "visibility": {
            "type": "string",
            "enum": ["default", "public", "private", "confidential"],
        },
        "organizer": {
            "type": "object",
            "properties": {
                "email": {"type": "string"},
                "displayName": {"type": "string"},
            },
        },
        "attendees": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "email": {"type": "string"},
                    "displayName": {"type": "string"},
                    "responseStatus": {"type": "string"},
                    "optional": {"type": "boolean"},
                    "organizer": {"type": "boolean"},
                },
            },
        },
        "guestsCanModify": {"type": "boolean"},
        "guestsCanInviteOthers": {"type": "boolean"},
        "guestsCanSeeOtherGuests": {"type": "boolean"},
        "conferenceData": {
            "type": "object",
            "properties": {
                "conferenceId": {"type": "string"},
                "conferenceSolution": {"type": "string"},
            },
        },
        "recurrence": {
            "type": "array",
            "items": {"type": "string"},
        },
        "reminders": {
            "type": "object",
            "properties": {
                "useDefault": {"type": "boolean"},
                "overrides": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "method": {"type": "string"},
                            "minutes": {"type": "integer"},
                        },
                    },
                },
            },
        },
        "created": {"type": "string"},
        "updated": {"type": "string"},
        "calendarId": {"type": "string", "x-terrarium-ref": "calendar"},
    },
}

CALENDAR_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "summary"],
    "properties": {
        "id": {"type": "string"},
        "kind": {"type": "string", "enum": ["calendar#calendar"]},
        "etag": {"type": "string"},
        "summary": {"type": "string"},
        "description": {"type": "string"},
        "timeZone": {"type": "string"},
        "foregroundColor": {"type": "string"},
        "backgroundColor": {"type": "string"},
        "primary": {"type": "boolean"},
        "defaultReminders": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "method": {"type": "string"},
                    "minutes": {"type": "integer"},
                },
            },
        },
        "accessRole": {
            "type": "string",
            "enum": ["owner", "reader", "writer", "freeBusyReader"],
        },
    },
}

ATTENDEE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-terrarium-identity": "id",
    "required": ["id", "event_id", "email", "responseStatus"],
    "properties": {
        "id": {"type": "string"},
        "event_id": {"type": "string", "x-terrarium-ref": "event"},
        "email": {"type": "string"},
        "displayName": {"type": "string"},
        "responseStatus": {
            "type": "string",
            "enum": ["needsAction", "accepted", "declined", "tentative"],
        },
        "optional": {"type": "boolean"},
        "organizer": {"type": "boolean"},
        "comment": {"type": "string"},
        "additionalGuests": {"type": "integer", "minimum": 0},
    },
}

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

CALENDAR_TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "list_calendar_events",
        "description": "List events on a specified calendar.",
        "http_path": "/calendar/v3/calendars/{calendarId}/events",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["calendarId"],
            "properties": {
                "calendarId": {
                    "type": "string",
                    "description": "Calendar identifier.",
                },
                "timeMin": {
                    "type": "string",
                    "description": "Lower bound (inclusive) for an event's end time (ISO 8601).",
                },
                "timeMax": {
                    "type": "string",
                    "description": "Upper bound (exclusive) for an event's start time (ISO 8601).",
                },
                "maxResults": {
                    "type": "integer",
                    "description": "Maximum number of events returned.",
                    "default": 250,
                },
                "orderBy": {
                    "type": "string",
                    "description": "Order of the events returned (e.g. startTime, updated).",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "kind": {"const": "calendar#events"},
                "items": {"type": "array"},
            },
        },
    },
    {
        "name": "get_calendar_event",
        "description": "Get a specific calendar event by ID.",
        "http_path": "/calendar/v3/calendars/{calendarId}/events/{eventId}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["calendarId", "eventId"],
            "properties": {
                "calendarId": {
                    "type": "string",
                    "description": "Calendar identifier.",
                },
                "eventId": {
                    "type": "string",
                    "description": "Event identifier.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "create_calendar_event",
        "description": "Create a new calendar event.",
        "http_path": "/calendar/v3/calendars/{calendarId}/events",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["calendarId", "summary", "start", "end"],
            "properties": {
                "calendarId": {
                    "type": "string",
                    "description": "Calendar identifier.",
                },
                "summary": {
                    "type": "string",
                    "description": "Title of the event.",
                },
                "start": {
                    "type": "object",
                    "description": (
                        "Start time (object with dateTime or date, and optional timeZone)."
                    ),
                },
                "end": {
                    "type": "object",
                    "description": (
                        "End time (object with dateTime or date, and optional timeZone)."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": "Description of the event.",
                },
                "location": {
                    "type": "string",
                    "description": "Geographic location of the event.",
                },
                "attendees": {
                    "type": "array",
                    "description": (
                        "List of attendees (objects with email and optional displayName)."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string"},
                            "displayName": {"type": "string"},
                        },
                    },
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "update_calendar_event",
        "description": "Update an existing calendar event.",
        "http_path": "/calendar/v3/calendars/{calendarId}/events/{eventId}",
        "http_method": "PUT",
        "parameters": {
            "type": "object",
            "required": ["calendarId", "eventId"],
            "properties": {
                "calendarId": {
                    "type": "string",
                    "description": "Calendar identifier.",
                },
                "eventId": {
                    "type": "string",
                    "description": "Event identifier.",
                },
                "summary": {
                    "type": "string",
                    "description": "Title of the event.",
                },
                "start": {
                    "type": "object",
                    "description": (
                        "Start time (object with dateTime or date, and optional timeZone)."
                    ),
                },
                "end": {
                    "type": "object",
                    "description": (
                        "End time (object with dateTime or date, and optional timeZone)."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": "Description of the event.",
                },
                "location": {
                    "type": "string",
                    "description": "Geographic location of the event.",
                },
                "status": {
                    "type": "string",
                    "description": ("Status of the event (confirmed, tentative, cancelled)."),
                },
                "attendees": {
                    "type": "array",
                    "description": (
                        "List of attendees (objects with email and optional displayName)."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "email": {"type": "string"},
                            "displayName": {"type": "string"},
                        },
                    },
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "delete_calendar_event",
        "description": "Delete (cancel) a calendar event.",
        "http_path": "/calendar/v3/calendars/{calendarId}/events/{eventId}",
        "http_method": "DELETE",
        "parameters": {
            "type": "object",
            "required": ["calendarId", "eventId"],
            "properties": {
                "calendarId": {
                    "type": "string",
                    "description": "Calendar identifier.",
                },
                "eventId": {
                    "type": "string",
                    "description": "Event identifier.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "search_calendar_events",
        "description": "Search for calendar events matching a query string.",
        "http_path": "/calendar/v3/calendars/{calendarId}/events",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["calendarId", "q"],
            "properties": {
                "calendarId": {
                    "type": "string",
                    "description": "Calendar identifier.",
                },
                "q": {
                    "type": "string",
                    "description": "Free-text search query.",
                },
                "maxResults": {
                    "type": "integer",
                    "description": "Maximum number of events returned.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "kind": {"const": "calendar#events"},
                "items": {"type": "array"},
            },
        },
    },
    {
        "name": "list_calendars",
        "description": "List all calendars for the current user.",
        "http_path": "/calendar/v3/users/me/calendarList",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {},
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "kind": {"const": "calendar#calendarList"},
                "items": {"type": "array"},
            },
        },
    },
    {
        "name": "get_calendar",
        "description": "Get a specific calendar by ID.",
        "http_path": "/calendar/v3/calendars/{calendarId}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["calendarId"],
            "properties": {
                "calendarId": {
                    "type": "string",
                    "description": "Calendar identifier.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "rsvp_calendar_event",
        "description": "Update an attendee's RSVP response status for a calendar event.",
        "http_path": "/calendar/v3/calendars/{calendarId}/events/{eventId}/attendees/{email}",
        "http_method": "PATCH",
        "parameters": {
            "type": "object",
            "required": ["calendarId", "eventId", "email", "responseStatus"],
            "properties": {
                "calendarId": {
                    "type": "string",
                    "description": "Calendar identifier.",
                },
                "eventId": {
                    "type": "string",
                    "description": "Event identifier.",
                },
                "email": {
                    "type": "string",
                    "description": "Attendee email address.",
                },
                "responseStatus": {
                    "type": "string",
                    "description": "New response status.",
                    "enum": ["accepted", "declined", "tentative"],
                },
            },
        },
        "response_schema": {"type": "object"},
    },
]
