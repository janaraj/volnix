"""Action handlers for the repos service pack."""

from __future__ import annotations

from typing import Any


async def handle_repo_list_branches(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``repo_list_branches`` action."""
    ...


async def handle_repo_create_pr(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``repo_create_pr`` action."""
    ...


async def handle_repo_list_prs(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``repo_list_prs`` action."""
    ...


async def handle_repo_merge_pr(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``repo_merge_pr`` action."""
    ...


async def handle_repo_add_review(input_data: dict, state: dict) -> dict[str, Any]:
    """Handle the ``repo_add_review`` action."""
    ...
