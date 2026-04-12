"""Dynamic negotiation tool schema builder (NF1).

Owns both :class:`NegotiationField` (the typed blueprint-declared
negotiation term model) and :func:`build_negotiation_tools` (the
builder that turns a list of fields into raw tool action dicts).

``NegotiationField`` lives in this pack-side module (not in
``volnix.engines.game.definition``) because of the architectural
layering: verified packs must not import from ``volnix.engines``
(enforced by ``tests/architecture/test_source_guards.py``). Having
the class here means engines import from packs, which is the allowed
direction.

When a blueprint declares ``game.negotiation_fields`` on the
:class:`volnix.engines.game.definition.GameDefinition`, the builder
produces JSON Schema-typed parameters for the four negotiation tools
(propose, counter, accept, reject). The raw action dicts are then
registered with the :class:`volnix.engines.agency.engine.AgencyEngine`
at game configure time via ``agency.register_game_tools(actions)``.

The builder returns RAW action dicts (the same shape
``available_actions`` uses in :meth:`AgencyEngine.configure`). The
agency's ``register_game_tools`` then layers meta_params
(``reasoning``, ``intended_for``, ``state_updates``) onto each action's
parameters — matching what ``_build_tool_definitions`` does for
regular pack-backed tools — and wraps them in ``ToolDefinition``.

When ``fields`` is empty, the builder returns the 4 static fallback
tool action dicts (``deal_id`` + optional ``message`` only), which is
the pre-NF1 behavior for minimal blueprints.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# ---------------------------------------------------------------------------
# NegotiationField — blueprint-declared negotiation term (typed)
# ---------------------------------------------------------------------------


NegotiationFieldType = Literal["number", "integer", "string", "boolean"]

# Valid JSON Schema property name (OpenAI function-calling requires
# parameter names to match ``^[A-Za-z_][A-Za-z0-9_]*$``).
_VALID_NEGOTIATION_FIELD_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class NegotiationField(BaseModel, frozen=True):
    """Blueprint-declared negotiation term.

    Each field becomes a typed, REQUIRED parameter on
    ``negotiate_propose`` and ``negotiate_counter``. Accept and reject
    never carry term fields.

    Type → JSON Schema primitive mapping:

    - ``number``  → ``{"type": "number"}``
    - ``integer`` → ``{"type": "integer"}``
    - ``string``  → ``{"type": "string"}``
    - ``boolean`` → ``{"type": "boolean"}``

    ``enum`` is only valid for string-typed fields (function-calling
    providers have inconsistent support for numeric enums).

    Field names must match ``^[A-Za-z_][A-Za-z0-9_]*$`` — dots, spaces,
    hyphens, and leading digits are rejected for OpenAI compatibility.

    Defined in this module (rather than engine-side) to respect the
    architectural layering: ``packs/verified`` cannot import from
    ``engines``. Engine code imports this class from the pack
    (``volnix.engines.game.definition`` re-exports it for convenience).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    type: NegotiationFieldType
    description: str = ""
    enum: list[str] | None = None

    @field_validator("name")
    @classmethod
    def _valid_identifier(cls, v: str) -> str:
        if not v:
            raise ValueError("NegotiationField.name must be non-empty")
        if not _VALID_NEGOTIATION_FIELD_NAME.match(v):
            raise ValueError(
                f"NegotiationField.name {v!r} is not a valid JSON Schema "
                f"property name (must match [A-Za-z_][A-Za-z0-9_]*). "
                f"Dots, spaces, hyphens, and leading digits are disallowed."
            )
        return v

    @model_validator(mode="after")
    def _enum_only_for_strings(self) -> NegotiationField:
        if self.enum is not None and self.type != "string":
            raise ValueError(
                f"NegotiationField {self.name!r}: enum is only valid for "
                f"string-typed fields (got type={self.type!r})."
            )
        return self


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

# Reserved parameter names — if a blueprint declared one of these as a
# negotiation field, the pack handler would silently strip it from the
# committed terms (see ``handlers._RESERVED_KEYS``). Reject loudly at
# build time instead of creating confusing runtime behavior.
_RESERVED_PARAM_NAMES: frozenset[str] = frozenset(
    {"deal_id", "message", "reasoning", "intended_for", "state_updates"}
)

# Static fallback parameter schema — matches the shape registered when
# the blueprint declares no negotiation fields (pre-NF1 behavior).
_STATIC_DEAL_ID_PARAMS: dict[str, Any] = {
    "type": "object",
    "required": ["deal_id"],
    "additionalProperties": True,
    "properties": {
        "deal_id": {
            "type": "string",
            "description": "ID of the deal you are negotiating (e.g. 'deal-001').",
        },
        "message": {
            "type": "string",
            "description": "Optional one-sentence in-character framing for this move.",
        },
    },
}


def _static_action(name: str, description: str) -> dict[str, Any]:
    """Build a single static fallback action dict."""
    return {
        "name": name,
        "service": "game",
        "description": description,
        "parameters": _STATIC_DEAL_ID_PARAMS,
        "http_method": "POST",
    }


_STATIC_FALLBACK_ACTIONS: list[dict[str, Any]] = [
    _static_action(
        "negotiate_propose",
        "Put an opening proposal on the table. Specify terms in the message.",
    ),
    _static_action(
        "negotiate_counter",
        "Counter-offer on an open deal. Specify terms in the message.",
    ),
    _static_action(
        "negotiate_accept",
        "Close the deal. Accept the other party's current terms.",
    ),
    _static_action(
        "negotiate_reject",
        "Walk away from the negotiation.",
    ),
]


def _field_schema(field: NegotiationField) -> dict[str, Any]:
    """Map a :class:`NegotiationField` to a JSON Schema fragment."""
    schema: dict[str, Any] = {"type": field.type}
    if field.description:
        schema["description"] = field.description
    if field.enum is not None:
        schema["enum"] = list(field.enum)
    return schema


def _typed_propose_counter_params(fields: list[NegotiationField]) -> dict[str, Any]:
    """Build propose/counter parameter schema. All declared fields REQUIRED."""
    properties: dict[str, Any] = {
        "deal_id": {
            "type": "string",
            "description": "ID of the deal you are negotiating.",
        },
        "message": {
            "type": "string",
            "description": "Optional one-sentence in-character framing.",
        },
    }
    required: list[str] = ["deal_id"]
    for field in fields:
        properties[field.name] = _field_schema(field)
        required.append(field.name)
    return {
        "type": "object",
        "required": required,
        "additionalProperties": False,
        "properties": properties,
    }


def _terminal_params() -> dict[str, Any]:
    """Build accept/reject parameter schema — deal_id + optional message only."""
    return {
        "type": "object",
        "required": ["deal_id"],
        "additionalProperties": False,
        "properties": {
            "deal_id": {
                "type": "string",
                "description": "ID of the deal you are closing.",
            },
            "message": {
                "type": "string",
                "description": "Optional one-sentence in-character framing.",
            },
        },
    }


def build_negotiation_tools(fields: list[NegotiationField]) -> list[dict[str, Any]]:
    """Build the 4 negotiation tool action dicts.

    Args:
        fields: Blueprint-declared negotiation terms. When empty, returns
            the static fallback (``deal_id`` + ``message``) — backward
            compatible with blueprints that declare no negotiation_fields.

    Returns:
        A list of 4 raw action dicts (propose, counter, accept, reject).
        These are passed to :meth:`AgencyEngine.register_game_tools`,
        which layers meta_params on top and wraps each in a
        ``ToolDefinition``.

    Raises:
        ValueError: Duplicate field names or reserved name collision.
            Individual field validation (identifier syntax, valid type,
            enum-only-for-strings) is enforced by the
            :class:`NegotiationField` Pydantic model.
    """
    if not fields:
        # Return shallow copies so caller mutation can't leak into the
        # module-level fallback list.
        return [dict(action) for action in _STATIC_FALLBACK_ACTIONS]

    seen: set[str] = set()
    for field in fields:
        if field.name in _RESERVED_PARAM_NAMES:
            raise ValueError(
                f"Negotiation field name {field.name!r} collides with a "
                f"reserved parameter name "
                f"({sorted(_RESERVED_PARAM_NAMES)}). Choose a different name."
            )
        if field.name in seen:
            raise ValueError(
                f"Duplicate negotiation field name: {field.name!r}. "
                f"Each blueprint-declared field must have a unique name."
            )
        seen.add(field.name)

    field_list_str = ", ".join(f.name for f in fields)
    propose_counter = _typed_propose_counter_params(fields)
    terminal = _terminal_params()

    return [
        {
            "name": "negotiate_propose",
            "service": "game",
            "description": (
                f"Put an opening proposal on the table. You MUST specify "
                f"all declared negotiation fields: {field_list_str}."
            ),
            "parameters": propose_counter,
            "http_method": "POST",
        },
        {
            "name": "negotiate_counter",
            "service": "game",
            "description": (
                f"Counter-offer on an open deal. You MUST specify all "
                f"declared negotiation fields: {field_list_str}. Any term "
                f"you don't repeat will be reset."
            ),
            "parameters": propose_counter,
            "http_method": "POST",
        },
        {
            "name": "negotiate_accept",
            "service": "game",
            "description": (
                "Close the deal. Accept the other party's current terms. "
                "Locks in the deal and earns an efficiency bonus for "
                "closing early."
            ),
            "parameters": terminal,
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
            "parameters": terminal,
            "http_method": "POST",
        },
    ]


__all__ = ["build_negotiation_tools"]
