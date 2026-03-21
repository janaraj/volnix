"""Action handlers for the calendar service pack."""

from __future__ import annotations

from typing import Any


async def handle_calendar_list_events(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``calendar_list_events`` action."""
    ...


async def handle_calendar_create_event(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``calendar_create_event`` action."""
    ...


async def handle_calendar_check_availability(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``calendar_check_availability`` action."""
    ...
