"""Shared actor identity resolution for protocol adapters.

All protocol adapters resolve actor identity using the same priority:
  1. Bearer token (``terr_*``) → SlotManager lookup
  2. Body field (``actor_id``)
  3. Header (``x-actor-id``)
  4. Default (protocol-specific)

This module extracts the common logic so HTTP REST, OpenAI compat,
and Anthropic compat all behave identically.
"""

from __future__ import annotations

from typing import Any


def resolve_actor_id(
    request: Any,
    body: dict[str, Any],
    default: str,
    gateway: Any = None,
) -> str | None:
    """Resolve actor identity from request context.

    Args:
        request: The Starlette/FastAPI request object.
        body: Parsed request body dict.
        default: Fallback actor_id if no other source found.
        gateway: Gateway instance for token resolution via SlotManager.

    Returns:
        Resolved actor_id string, or ``None`` if a Bearer token was
        provided but is invalid (caller should return 401).
    """
    auth = request.headers.get("authorization", "")

    # Priority 1: Bearer token
    if auth.startswith("Bearer terr_"):
        token = auth.removeprefix("Bearer ").strip()
        slot_mgr = getattr(gateway, "_slot_manager", None) if gateway else None
        if slot_mgr:
            resolved = slot_mgr.resolve_token(token)
            if resolved:
                return str(resolved)
            return None  # Invalid token — caller should 401

    # Priority 2: Body field
    body_id = body.get("actor_id", "")
    if body_id:
        return str(body_id)

    # Priority 3: Header
    header_id = request.headers.get("x-actor-id", "").strip()
    if header_id:
        return header_id

    # Priority 4: Default
    return default
