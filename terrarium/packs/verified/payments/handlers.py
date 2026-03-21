"""Action handlers for the payments service pack."""

from __future__ import annotations

from typing import Any


async def handle_charges_list(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``charges_list`` action."""
    ...


async def handle_charges_get(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``charges_get`` action."""
    ...


async def handle_refund_create(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``refund_create`` action."""
    ...


async def handle_refund_list(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``refund_list`` action."""
    ...


async def handle_dispute_list(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``dispute_list`` action."""
    ...
