"""Tests for volnix.packs.verified.google_calendar -- CalendarPack through pack's own handle_action."""

import pytest

from volnix.core.context import ResponseProposal
from volnix.core.types import ToolName
from volnix.packs.verified.google_calendar.pack import CalendarPack
from volnix.packs.verified.google_calendar.schemas import (
    ATTENDEE_ENTITY_SCHEMA,
    CALENDAR_ENTITY_SCHEMA,
    EVENT_ENTITY_SCHEMA,
)


@pytest.fixture
def calendar_pack():
    return CalendarPack()


@pytest.fixture
def sample_state():
    """State with pre-existing calendars, events, and attendees."""
    return {
        "calendars": [
            {
                "id": "cal_primary",
                "kind": "calendar#calendar",
                "etag": '"abc123"',
                "summary": "Primary Calendar",
                "description": "Main work calendar",
                "timeZone": "America/New_York",
                "foregroundColor": "#000000",
                "backgroundColor": "#9fe1e7",
                "primary": True,
                "defaultReminders": [{"method": "popup", "minutes": 10}],
                "accessRole": "owner",
            },
            {
                "id": "cal_team",
                "kind": "calendar#calendar",
                "etag": '"def456"',
                "summary": "Team Calendar",
                "description": "Shared team calendar",
                "timeZone": "America/New_York",
                "primary": False,
                "accessRole": "writer",
            },
        ],
        "events": [
            {
                "id": "evt_001",
                "etag": '"evt001tag"',
                "kind": "calendar#event",
                "iCalUID": "evt_001@google.com",
                "summary": "Sprint Planning",
                "description": "Bi-weekly sprint planning meeting",
                "location": "Conference Room A",
                "start": {"dateTime": "2026-03-25T09:00:00-04:00"},
                "end": {"dateTime": "2026-03-25T10:00:00-04:00"},
                "status": "confirmed",
                "transparency": "opaque",
                "visibility": "default",
                "organizer": {"email": "alice@test.com", "displayName": "Alice"},
                "attendees": [],
                "guestsCanModify": False,
                "guestsCanInviteOthers": True,
                "guestsCanSeeOtherGuests": True,
                "recurrence": [],
                "reminders": {"useDefault": True, "overrides": []},
                "created": "2026-03-20T12:00:00+00:00",
                "updated": "2026-03-20T12:00:00+00:00",
                "calendarId": "cal_primary",
            },
            {
                "id": "evt_002",
                "etag": '"evt002tag"',
                "kind": "calendar#event",
                "iCalUID": "evt_002@google.com",
                "summary": "Lunch with Bob",
                "description": "Casual lunch",
                "location": "Cafeteria",
                "start": {"dateTime": "2026-03-25T12:00:00-04:00"},
                "end": {"dateTime": "2026-03-25T13:00:00-04:00"},
                "status": "tentative",
                "transparency": "transparent",
                "visibility": "default",
                "organizer": {"email": "alice@test.com"},
                "attendees": [],
                "recurrence": [],
                "reminders": {"useDefault": True, "overrides": []},
                "created": "2026-03-21T10:00:00+00:00",
                "updated": "2026-03-21T10:00:00+00:00",
                "calendarId": "cal_primary",
            },
            {
                "id": "evt_003",
                "summary": "Team Standup",
                "description": "Daily standup",
                "location": "",
                "start": {"dateTime": "2026-03-26T09:00:00-04:00"},
                "end": {"dateTime": "2026-03-26T09:15:00-04:00"},
                "status": "confirmed",
                "organizer": {"email": "bob@test.com"},
                "attendees": [],
                "recurrence": [],
                "reminders": {"useDefault": True, "overrides": []},
                "created": "2026-03-22T08:00:00+00:00",
                "updated": "2026-03-22T08:00:00+00:00",
                "calendarId": "cal_team",
            },
        ],
        "attendees": [
            {
                "id": "att_001",
                "event_id": "evt_001",
                "email": "bob@test.com",
                "displayName": "Bob",
                "responseStatus": "accepted",
                "optional": False,
                "organizer": False,
                "comment": "",
                "additionalGuests": 0,
            },
            {
                "id": "att_002",
                "event_id": "evt_001",
                "email": "carol@test.com",
                "displayName": "Carol",
                "responseStatus": "needsAction",
                "optional": True,
                "organizer": False,
                "comment": "",
                "additionalGuests": 0,
            },
        ],
    }


# ---- Metadata tests ----


class TestCalendarPackMetadata:
    def test_metadata(self, calendar_pack):
        """pack_name, category, fidelity_tier are correct."""
        assert calendar_pack.pack_name == "google_calendar"
        assert calendar_pack.category == "scheduling"
        assert calendar_pack.fidelity_tier == 1

    def test_tools_count_and_names(self, calendar_pack):
        """CalendarPack exposes 9 tools with expected names."""
        tools = calendar_pack.get_tools()
        assert len(tools) == 9
        tool_names = {t["name"] for t in tools}
        assert tool_names == {
            "events.list",
            "events.get",
            "events.insert",
            "events.update",
            "events.delete",
            "events.search",
            "calendarList.list",
            "calendarList.get",
            "events.patch",
        }

    def test_entity_schemas(self, calendar_pack):
        """event, calendar, and attendee entity schemas are present."""
        schemas = calendar_pack.get_entity_schemas()
        assert "event" in schemas
        assert "calendar" in schemas
        assert "attendee" in schemas

    def test_state_machines(self, calendar_pack):
        """State machines for event and attendee are present."""
        sms = calendar_pack.get_state_machines()
        assert "event" in sms
        assert "attendee" in sms
        assert "cancelled" in sms["event"]["transitions"]["tentative"]
        assert "accepted" in sms["attendee"]["transitions"]["needsAction"]

    def test_event_schema_identity(self):
        """Event identity field is 'id'."""
        assert EVENT_ENTITY_SCHEMA["x-volnix-identity"] == "id"

    def test_calendar_schema_identity(self):
        """Calendar identity field is 'id'."""
        assert CALENDAR_ENTITY_SCHEMA["x-volnix-identity"] == "id"

    def test_attendee_schema_identity(self):
        """Attendee identity field is 'id'."""
        assert ATTENDEE_ENTITY_SCHEMA["x-volnix-identity"] == "id"

    def test_event_schema_has_new_fields(self):
        """Event schema includes P1 audit fields."""
        props = EVENT_ENTITY_SCHEMA["properties"]
        assert "etag" in props
        assert "kind" in props
        assert "iCalUID" in props
        assert "recurringEventId" in props
        assert "transparency" in props
        assert "visibility" in props
        assert "guestsCanModify" in props
        assert "guestsCanInviteOthers" in props
        assert "guestsCanSeeOtherGuests" in props
        assert "conferenceData" in props

    def test_calendar_schema_has_new_fields(self):
        """Calendar schema includes P1 audit fields."""
        props = CALENDAR_ENTITY_SCHEMA["properties"]
        assert "kind" in props
        assert "etag" in props
        assert "foregroundColor" in props
        assert "backgroundColor" in props
        assert "primary" in props
        assert "defaultReminders" in props

    def test_attendee_schema_has_new_fields(self):
        """Attendee schema includes P1 audit fields."""
        props = ATTENDEE_ENTITY_SCHEMA["properties"]
        assert "comment" in props
        assert "additionalGuests" in props


# ---- Handler tests ----


class TestListCalendarEvents:
    async def test_returns_events_for_calendar(self, calendar_pack, sample_state):
        """list_calendar_events returns events for the given calendarId."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.list"),
            {"calendarId": "cal_primary"},
            sample_state,
        )
        assert isinstance(proposal, ResponseProposal)
        assert proposal.response_body["kind"] == "calendar#events"
        assert len(proposal.response_body["items"]) == 2
        assert proposal.proposed_state_deltas == []

    async def test_filters_by_time_range(self, calendar_pack, sample_state):
        """list_calendar_events filters by timeMin and timeMax."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.list"),
            {
                "calendarId": "cal_primary",
                "timeMin": "2026-03-25T11:00:00-04:00",
            },
            sample_state,
        )
        # Only the lunch event (12:00) should match
        assert len(proposal.response_body["items"]) == 1
        assert proposal.response_body["items"][0]["id"] == "evt_002"

    async def test_respects_max_results(self, calendar_pack, sample_state):
        """list_calendar_events respects maxResults."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.list"),
            {"calendarId": "cal_primary", "maxResults": 1},
            sample_state,
        )
        assert len(proposal.response_body["items"]) == 1

    async def test_empty_calendar(self, calendar_pack):
        """list_calendar_events returns empty list for unknown calendar."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.list"),
            {"calendarId": "cal_nonexistent"},
            {"events": []},
        )
        assert proposal.response_body["items"] == []


class TestGetCalendarEvent:
    async def test_returns_event_with_attendees(self, calendar_pack, sample_state):
        """get_calendar_event returns the event with embedded attendees."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.get"),
            {"calendarId": "cal_primary", "eventId": "evt_001"},
            sample_state,
        )
        assert proposal.response_body["id"] == "evt_001"
        assert proposal.response_body["summary"] == "Sprint Planning"
        # Should have 2 attendees from state
        assert len(proposal.response_body["attendees"]) == 2
        assert proposal.proposed_state_deltas == []

    async def test_event_not_found(self, calendar_pack, sample_state):
        """get_calendar_event returns Google-format error for unknown eventId."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.get"),
            {"calendarId": "cal_primary", "eventId": "evt_missing"},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert proposal.response_body["error"]["code"] == 404
        assert "errors" in proposal.response_body["error"]


class TestCreateCalendarEvent:
    async def test_creates_event_with_attendees(self, calendar_pack, sample_state):
        """create_calendar_event creates event + attendee entities."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.insert"),
            {
                "calendarId": "cal_primary",
                "summary": "Design Review",
                "start": {"dateTime": "2026-03-27T14:00:00-04:00"},
                "end": {"dateTime": "2026-03-27T15:00:00-04:00"},
                "description": "Review new designs",
                "location": "Room B",
                "attendees": [
                    {"email": "dave@test.com", "displayName": "Dave"},
                    {"email": "eve@test.com"},
                ],
            },
            sample_state,
        )
        assert isinstance(proposal, ResponseProposal)
        body = proposal.response_body

        # Event fields
        assert body["summary"] == "Design Review"
        assert body["status"] == "confirmed"
        assert body["calendarId"] == "cal_primary"
        assert body["id"].startswith("evt_")
        assert body["created"] != ""
        assert body["updated"] != ""
        # P1 new fields
        assert "etag" in body
        assert body["kind"] == "calendar#event"
        assert "iCalUID" in body
        assert body["transparency"] == "opaque"
        assert body["visibility"] == "default"
        assert body["guestsCanModify"] is False
        assert body["guestsCanInviteOthers"] is True

        # Attendees embedded in response
        assert len(body["attendees"]) == 2
        assert body["attendees"][0]["email"] == "dave@test.com"
        assert body["attendees"][0]["responseStatus"] == "needsAction"
        assert body["attendees"][1]["email"] == "eve@test.com"
        # P1 new attendee fields
        assert body["attendees"][0]["comment"] == ""
        assert body["attendees"][0]["additionalGuests"] == 0

        # 1 event create + 2 attendee creates = 3 deltas
        assert len(proposal.proposed_state_deltas) == 3

        event_delta = proposal.proposed_state_deltas[0]
        assert event_delta.entity_type == "event"
        assert event_delta.operation == "create"

        att_delta_1 = proposal.proposed_state_deltas[1]
        assert att_delta_1.entity_type == "attendee"
        assert att_delta_1.operation == "create"
        assert att_delta_1.fields["email"] == "dave@test.com"
        assert att_delta_1.fields["event_id"] == body["id"]

        att_delta_2 = proposal.proposed_state_deltas[2]
        assert att_delta_2.entity_type == "attendee"
        assert att_delta_2.fields["email"] == "eve@test.com"

    async def test_creates_event_without_attendees(self, calendar_pack, sample_state):
        """create_calendar_event works with no attendees."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.insert"),
            {
                "calendarId": "cal_primary",
                "summary": "Solo Focus Time",
                "start": {"dateTime": "2026-03-27T10:00:00-04:00"},
                "end": {"dateTime": "2026-03-27T12:00:00-04:00"},
            },
            sample_state,
        )
        assert proposal.response_body["summary"] == "Solo Focus Time"
        assert proposal.response_body["attendees"] == []
        # Only 1 delta for the event itself
        assert len(proposal.proposed_state_deltas) == 1
        assert proposal.proposed_state_deltas[0].entity_type == "event"


class TestUpdateCalendarEvent:
    async def test_updates_event_fields(self, calendar_pack, sample_state):
        """update_calendar_event updates specified fields."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.update"),
            {
                "calendarId": "cal_primary",
                "eventId": "evt_001",
                "summary": "Sprint Planning v2",
                "location": "Conference Room B",
            },
            sample_state,
        )
        body = proposal.response_body
        assert body["summary"] == "Sprint Planning v2"
        assert body["location"] == "Conference Room B"
        # updated timestamp should be refreshed
        assert body["updated"] != "2026-03-20T12:00:00+00:00"
        # P1: etag should be refreshed
        assert "etag" in body

        assert len(proposal.proposed_state_deltas) >= 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "event"
        assert delta.operation == "update"
        assert delta.fields["summary"] == "Sprint Planning v2"
        assert delta.previous_fields["summary"] == "Sprint Planning"

    async def test_updates_status_with_previous(self, calendar_pack, sample_state):
        """update_calendar_event records previous status on change."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.update"),
            {
                "calendarId": "cal_primary",
                "eventId": "evt_002",
                "status": "confirmed",
            },
            sample_state,
        )
        delta = proposal.proposed_state_deltas[0]
        assert delta.fields["status"] == "confirmed"
        assert delta.previous_fields["status"] == "tentative"

    async def test_update_with_new_attendees(self, calendar_pack, sample_state):
        """update_calendar_event creates new attendee entities for new emails."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.update"),
            {
                "calendarId": "cal_primary",
                "eventId": "evt_001",
                "attendees": [{"email": "frank@test.com"}],
            },
            sample_state,
        )
        # 1 event update + 1 attendee create = 2 deltas
        assert len(proposal.proposed_state_deltas) == 2
        att_delta = proposal.proposed_state_deltas[1]
        assert att_delta.entity_type == "attendee"
        assert att_delta.operation == "create"
        assert att_delta.fields["email"] == "frank@test.com"

    async def test_update_existing_attendee_no_duplicate(self, calendar_pack, sample_state):
        """P2 fix: update_calendar_event updates existing attendee instead of creating duplicate."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.update"),
            {
                "calendarId": "cal_primary",
                "eventId": "evt_001",
                "attendees": [{"email": "bob@test.com", "displayName": "Robert"}],
            },
            sample_state,
        )
        # 1 event update + 1 attendee UPDATE (not create) = 2 deltas
        assert len(proposal.proposed_state_deltas) == 2
        att_delta = proposal.proposed_state_deltas[1]
        assert att_delta.entity_type == "attendee"
        assert att_delta.operation == "update"
        assert att_delta.entity_id == "att_001"
        assert att_delta.fields["responseStatus"] == "needsAction"
        assert att_delta.previous_fields["responseStatus"] == "accepted"

    async def test_update_mixed_new_and_existing_attendees(self, calendar_pack, sample_state):
        """update_calendar_event handles mix of new and existing attendees correctly."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.update"),
            {
                "calendarId": "cal_primary",
                "eventId": "evt_001",
                "attendees": [
                    {"email": "bob@test.com"},  # existing
                    {"email": "new_person@test.com"},  # new
                ],
            },
            sample_state,
        )
        # 1 event update + 1 attendee update + 1 attendee create = 3 deltas
        assert len(proposal.proposed_state_deltas) == 3
        att_update = proposal.proposed_state_deltas[1]
        assert att_update.operation == "update"
        att_create = proposal.proposed_state_deltas[2]
        assert att_create.operation == "create"
        assert att_create.fields["email"] == "new_person@test.com"

    async def test_update_event_not_found(self, calendar_pack, sample_state):
        """update_calendar_event returns Google-format error for unknown eventId."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.update"),
            {
                "calendarId": "cal_primary",
                "eventId": "evt_missing",
                "summary": "Nope",
            },
            sample_state,
        )
        assert "error" in proposal.response_body
        assert proposal.response_body["error"]["code"] == 404


class TestDeleteCalendarEvent:
    async def test_sets_status_cancelled(self, calendar_pack, sample_state):
        """delete_calendar_event sets status to cancelled, not a real delete."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.delete"),
            {"calendarId": "cal_primary", "eventId": "evt_001"},
            sample_state,
        )
        body = proposal.response_body
        assert body["status"] == "cancelled"
        assert body["id"] == "evt_001"

        # Single update delta, NOT a delete operation
        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.operation == "update"
        assert delta.fields["status"] == "cancelled"
        assert delta.previous_fields["status"] == "confirmed"

    async def test_delete_event_not_found(self, calendar_pack, sample_state):
        """delete_calendar_event returns Google-format error for unknown eventId."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.delete"),
            {"calendarId": "cal_primary", "eventId": "evt_gone"},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert proposal.response_body["error"]["code"] == 404


class TestSearchCalendarEvents:
    async def test_search_by_summary(self, calendar_pack, sample_state):
        """search_calendar_events finds events matching summary."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.search"),
            {"calendarId": "cal_primary", "q": "sprint"},
            sample_state,
        )
        items = proposal.response_body["items"]
        assert len(items) == 1
        assert items[0]["id"] == "evt_001"
        assert proposal.proposed_state_deltas == []

    async def test_search_by_description(self, calendar_pack, sample_state):
        """search_calendar_events finds events matching description."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.search"),
            {"calendarId": "cal_primary", "q": "casual"},
            sample_state,
        )
        items = proposal.response_body["items"]
        assert len(items) == 1
        assert items[0]["id"] == "evt_002"

    async def test_search_case_insensitive(self, calendar_pack, sample_state):
        """search_calendar_events is case-insensitive."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.search"),
            {"calendarId": "cal_primary", "q": "SPRINT"},
            sample_state,
        )
        assert len(proposal.response_body["items"]) == 1

    async def test_search_no_results(self, calendar_pack, sample_state):
        """search_calendar_events returns empty for non-matching query."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.search"),
            {"calendarId": "cal_primary", "q": "nonexistent_xyz"},
            sample_state,
        )
        assert proposal.response_body["items"] == []


class TestListCalendars:
    async def test_returns_all_calendars(self, calendar_pack, sample_state):
        """list_calendars returns all calendars from state."""
        proposal = await calendar_pack.handle_action(
            ToolName("calendarList.list"),
            {},
            sample_state,
        )
        assert proposal.response_body["kind"] == "calendar#calendarList"
        assert len(proposal.response_body["items"]) == 2
        assert proposal.proposed_state_deltas == []

    async def test_empty_state(self, calendar_pack):
        """list_calendars returns empty list when no calendars exist."""
        proposal = await calendar_pack.handle_action(
            ToolName("calendarList.list"),
            {},
            {},
        )
        assert proposal.response_body["items"] == []


class TestGetCalendar:
    async def test_returns_calendar_by_id(self, calendar_pack, sample_state):
        """get_calendar returns the correct calendar."""
        proposal = await calendar_pack.handle_action(
            ToolName("calendarList.get"),
            {"calendarId": "cal_primary"},
            sample_state,
        )
        assert proposal.response_body["id"] == "cal_primary"
        assert proposal.response_body["summary"] == "Primary Calendar"
        assert proposal.proposed_state_deltas == []

    async def test_calendar_not_found(self, calendar_pack, sample_state):
        """get_calendar returns Google-format error for unknown calendarId."""
        proposal = await calendar_pack.handle_action(
            ToolName("calendarList.get"),
            {"calendarId": "cal_nonexistent"},
            sample_state,
        )
        assert "error" in proposal.response_body
        assert proposal.response_body["error"]["code"] == 404


class TestRsvpCalendarEvent:
    async def test_accept_rsvp(self, calendar_pack, sample_state):
        """rsvp_calendar_event can accept an invitation."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.patch"),
            {
                "calendarId": "cal_primary",
                "eventId": "evt_001",
                "email": "carol@test.com",
                "responseStatus": "accepted",
            },
            sample_state,
        )
        assert proposal.response_body["responseStatus"] == "accepted"
        assert proposal.response_body["email"] == "carol@test.com"

        assert len(proposal.proposed_state_deltas) == 1
        delta = proposal.proposed_state_deltas[0]
        assert delta.entity_type == "attendee"
        assert delta.operation == "update"
        assert delta.entity_id == "att_002"
        assert delta.fields["responseStatus"] == "accepted"
        assert delta.previous_fields["responseStatus"] == "needsAction"

    async def test_decline_rsvp(self, calendar_pack, sample_state):
        """rsvp_calendar_event can decline an invitation."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.patch"),
            {
                "calendarId": "cal_primary",
                "eventId": "evt_001",
                "email": "bob@test.com",
                "responseStatus": "declined",
            },
            sample_state,
        )
        assert proposal.response_body["responseStatus"] == "declined"
        delta = proposal.proposed_state_deltas[0]
        assert delta.fields["responseStatus"] == "declined"
        assert delta.previous_fields["responseStatus"] == "accepted"

    async def test_tentative_rsvp(self, calendar_pack, sample_state):
        """rsvp_calendar_event can set tentative status."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.patch"),
            {
                "calendarId": "cal_primary",
                "eventId": "evt_001",
                "email": "bob@test.com",
                "responseStatus": "tentative",
            },
            sample_state,
        )
        assert proposal.response_body["responseStatus"] == "tentative"

    async def test_rsvp_event_not_found(self, calendar_pack, sample_state):
        """rsvp_calendar_event returns error for unknown event."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.patch"),
            {
                "calendarId": "cal_primary",
                "eventId": "evt_missing",
                "email": "bob@test.com",
                "responseStatus": "accepted",
            },
            sample_state,
        )
        assert "error" in proposal.response_body
        assert proposal.response_body["error"]["code"] == 404

    async def test_rsvp_attendee_not_found(self, calendar_pack, sample_state):
        """rsvp_calendar_event returns error for unknown attendee email."""
        proposal = await calendar_pack.handle_action(
            ToolName("events.patch"),
            {
                "calendarId": "cal_primary",
                "eventId": "evt_001",
                "email": "unknown@test.com",
                "responseStatus": "accepted",
            },
            sample_state,
        )
        assert "error" in proposal.response_body
        assert proposal.response_body["error"]["code"] == 404
