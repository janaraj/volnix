"""Calendar service pack (Tier 1 -- verified).

Provides the canonical tool surface for scheduling services:
list events, get event, create event, update event, delete event,
search events, list calendars, get calendar, RSVP event.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.base import ActionHandler, ServicePack
from terrarium.packs.verified.google_calendar.handlers import (
    handle_create_calendar_event,
    handle_delete_calendar_event,
    handle_get_calendar,
    handle_get_calendar_event,
    handle_list_calendar_events,
    handle_list_calendars,
    handle_rsvp_calendar_event,
    handle_search_calendar_events,
    handle_update_calendar_event,
)
from terrarium.packs.verified.google_calendar.schemas import (
    ATTENDEE_ENTITY_SCHEMA,
    CALENDAR_ENTITY_SCHEMA,
    CALENDAR_TOOL_DEFINITIONS,
    EVENT_ENTITY_SCHEMA,
)
from terrarium.packs.verified.google_calendar.state_machines import (
    EVENT_TRANSITIONS,
    RESPONSE_TRANSITIONS,
)


class CalendarPack(ServicePack):
    """Verified pack for calendar / scheduling services.

    Tools: events.list, events.get, events.insert, events.update,
    events.delete, events.search, calendarList.list, calendarList.get,
    events.patch.
    """

    pack_name: ClassVar[str] = "google_calendar"
    category: ClassVar[str] = "scheduling"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        "events.list": handle_list_calendar_events,
        "events.get": handle_get_calendar_event,
        "events.insert": handle_create_calendar_event,
        "events.update": handle_update_calendar_event,
        "events.delete": handle_delete_calendar_event,
        "events.search": handle_search_calendar_events,
        "calendarList.list": handle_list_calendars,
        "calendarList.get": handle_get_calendar,
        "events.patch": handle_rsvp_calendar_event,
    }

    def get_tools(self) -> list[dict]:
        """Return the calendar tool manifest."""
        return list(CALENDAR_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (event, calendar, attendee)."""
        return {
            "event": EVENT_ENTITY_SCHEMA,
            "calendar": CALENDAR_ENTITY_SCHEMA,
            "attendee": ATTENDEE_ENTITY_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        """Return state machines for calendar entities."""
        return {
            "event": {"transitions": EVENT_TRANSITIONS},
            "attendee": {"transitions": RESPONSE_TRANSITIONS},
        }

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate calendar action handler."""
        return await self.dispatch_action(action, input_data, state)
