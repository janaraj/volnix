"""Entity schemas + tool definitions for the game service pack.

Tool definitions are the *legacy fallback* schemas — they are the
"pure closing" shape (``deal_id`` + optional ``message``). When a
blueprint declares ``game.type_config.negotiation_fields``, the
orchestrator registers *dynamic* tool definitions built from those
declared fields via the P1 ``_build_negotiation_tools`` helper
(relocated to ``tool_schema.py`` in this pack). The legacy static
definitions here are used only when no ``negotiation_fields`` are
declared (e.g. Q3 Steel's original minimal negotiation).
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------

NEGOTIATION_DEAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "parties", "status"],
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "parties": {"type": "array", "items": {"type": "string"}},
        "status": {
            "type": "string",
            "enum": ["open", "proposed", "countered", "accepted", "rejected"],
        },
        "terms": {"type": "object"},
        "terms_template": {"type": "object"},
        "last_proposed_by": {"type": "string"},
        "last_updated_at": {"type": "string"},
        # P7-ready consent ledger
        "consent_by": {"type": "array", "items": {"type": "string"}},
        "consent_rule": {
            "type": "string",
            "enum": ["unanimous", "majority"],
        },
        # Terminal-state tracking
        "accepted_by": {"type": "string"},
        "accepted_at": {"type": "string"},
        "rejected_by": {"type": "string"},
        "rejected_at": {"type": "string"},
    },
}

NEGOTIATION_PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "deal_id", "proposed_by", "msg_type", "created_at"],
    "properties": {
        "id": {"type": "string"},
        "deal_id": {"type": "string"},
        "proposed_by": {"type": "string"},
        "msg_type": {"type": "string", "enum": ["propose", "counter"]},
        "terms": {"type": "object"},
        "created_at": {"type": "string"},
    },
}

GAME_PLAYER_BRIEF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "actor_role", "deal_id"],
    "properties": {
        "id": {"type": "string"},
        "actor_role": {"type": "string"},
        "deal_id": {"type": "string"},
        "owner_role": {"type": "string"},  # visibility rule target
        "brief_content": {"type": "string"},
        "mission": {"type": "string"},
        "prohibited_actions": {"type": "array", "items": {"type": "string"}},
        "notion_page_id": {"type": "string"},
    },
}

NEGOTIATION_TARGET_TERMS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "actor_role", "deal_id"],
    "properties": {
        "id": {"type": "string"},
        "actor_role": {"type": "string"},
        "deal_id": {"type": "string"},
        "ideal_terms": {"type": "object"},
        "term_weights": {"type": "object"},
        "term_ranges": {"type": "object"},
        "batna_score": {"type": "number"},
    },
}

# ---------------------------------------------------------------------------
# Legacy / fallback tool definitions (pure-closing schema)
# ---------------------------------------------------------------------------

_DEAL_ID_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["deal_id"],
    "additionalProperties": True,
    "properties": {
        "deal_id": {
            "type": "string",
            "description": "ID of the deal you are negotiating (e.g., 'deal-001').",
        },
        "message": {
            "type": "string",
            "description": "Optional one-sentence in-character framing for this move.",
        },
    },
}

GAME_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "negotiate_propose",
        "service": "game",
        "description": (
            "Put an opening proposal on the table. Specify all declared "
            "negotiation fields — they come from the blueprint's "
            "game.type_config.negotiation_fields."
        ),
        "parameters": _DEAL_ID_SCHEMA,
        "http_method": "POST",
    },
    {
        "name": "negotiate_counter",
        "service": "game",
        "description": (
            "Counter-offer on an open deal. Specify all declared "
            "negotiation fields — any term you don't repeat will be "
            "reset to your counter values."
        ),
        "parameters": _DEAL_ID_SCHEMA,
        "http_method": "POST",
    },
    {
        "name": "negotiate_accept",
        "service": "game",
        "description": (
            "Close the deal. Accept the other party's current terms. "
            "This locks in the deal and earns an efficiency bonus for "
            "closing early."
        ),
        "parameters": _DEAL_ID_SCHEMA,
        "http_method": "POST",
    },
    {
        "name": "negotiate_reject",
        "service": "game",
        "description": (
            "Walk away from the negotiation. Use only when the other "
            "party's terms are worse than your BATNA and they refuse "
            "to move."
        ),
        "parameters": _DEAL_ID_SCHEMA,
        "http_method": "POST",
    },
]
