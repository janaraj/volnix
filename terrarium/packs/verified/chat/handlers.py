"""Action handlers for the chat service pack."""

from __future__ import annotations

from typing import Any


async def handle_chat_send_message(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``chat_send_message`` action."""
    ...


async def handle_chat_list_channels(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``chat_list_channels`` action."""
    ...


async def handle_chat_list_messages(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``chat_list_messages`` action."""
    ...


async def handle_chat_create_channel(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``chat_create_channel`` action."""
    ...
