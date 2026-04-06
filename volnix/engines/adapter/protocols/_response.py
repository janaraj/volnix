"""Shared response helpers for protocol adapters.

Used by HTTP REST and MCP adapters to normalize pack responses
for external tool transports.
"""

from __future__ import annotations

from typing import Any


def unwrap_single_entity(body: dict[str, Any]) -> dict[str, Any]:
    """Unwrap single-entity wrapper: {"ticket": {...}} -> inner dict.

    Pack handlers return Zendesk/Gmail/Stripe-style wrappers like
    ``{"ticket": {"id": "t-1", ...}}``.  External agents (and LLMs)
    work better with the inner object directly.

    Multi-key responses (lists, errors) pass through unchanged:
      {"tickets": [...], "count": 5}  -> unchanged
      {"error": "NotFound", ...}      -> unchanged
    """
    if not isinstance(body, dict):
        return body
    keys = list(body.keys())
    if len(keys) == 1 and isinstance(body[keys[0]], dict) and "error" not in body:
        return body[keys[0]]
    return body
