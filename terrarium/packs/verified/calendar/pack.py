"""Calendar service pack (Tier 1 -- verified).

Provides the canonical tool surface for scheduling services:
list events, create event, and check availability.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.base import ServicePack


class CalendarPack(ServicePack):
    """Verified pack for calendar / scheduling services.

    Tools: calendar_list_events, calendar_create_event,
    calendar_check_availability.
    """

    pack_name: ClassVar[str] = "calendar"
    category: ClassVar[str] = "scheduling"
    fidelity_tier: ClassVar[int] = 1

    def get_tools(self) -> list[dict]:
        """Return the calendar tool manifest."""
        ...

    def get_entity_schemas(self) -> dict:
        """Return entity schemas (event, calendar, attendee)."""
        ...

    def get_state_machines(self) -> dict:
        """Return state machines for calendar entities."""
        ...

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate calendar action handler."""
        ...
