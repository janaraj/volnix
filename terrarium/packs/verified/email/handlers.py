"""Action handlers for the email service pack.

Each function handles one tool action, reading from and mutating the
world state as appropriate.
"""

from __future__ import annotations

from typing import Any


async def handle_email_send(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``email_send`` action."""
    ...


async def handle_email_list(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``email_list`` action."""
    ...


async def handle_email_read(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``email_read`` action."""
    ...


async def handle_email_search(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``email_search`` action."""
    ...


async def handle_email_reply(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``email_reply`` action."""
    ...


async def handle_email_mark_read(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``email_mark_read`` action."""
    ...
