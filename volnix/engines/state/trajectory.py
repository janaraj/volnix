"""Trajectory primitives for state projection (PMF Plan Phase 4C
Step 9).

``TrajectoryPoint`` is the immutable, JSON-serialisable record of a
single change to an entity's field at a specific tick. A list of
``TrajectoryPoint`` values is the output of
``StateEngine.get_trajectory(entity_id, field_path, tick_range)``
— a historical-value projection reconstructed from committed
``WorldEvent.state_deltas``.

Lives under ``volnix/engines/state/`` (not ``volnix/observation/``)
because the concept of a trajectory is state-engine-native: the
timeline primitive in ``volnix/observation/`` (Step 10) consumes
this type but does not own it. Keeping ownership with the state
engine avoids a circular re-export when Step 10 lands.

The ``value`` field is typed as a JSON-native union (audit-fold
M2) and a field validator recursively rejects non-JSON-native
leaves (post-impl audit H3) so ``model_dump(mode="json")`` AND
``json.dumps(pt.value)`` are both safe for downstream product
wire-transport.

Also owns the private ``_MISSING`` sentinel + ``_extract_dotted``
helper that ``StateEngine.get_trajectory`` uses to walk nested
``fields`` dicts. Keeping them here (not in ``engine.py``) decouples
them from the engine's lifecycle so tests can reuse them without
importing the full engine (post-impl audit L4).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from volnix.core.types import EntityId, EventId

# Union of Python types that survive ``json.dumps`` round-trip
# losslessly. Restricting ``TrajectoryPoint.value`` to this union
# means no product using the trajectory API will hit a silent
# serialisation cliff on non-JSON values (pre-impl audit M2).
JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | dict[str, Any] | list[Any]


# Sentinel for "field not present" that survives ``None`` being a
# legitimate field value (a field set to ``null`` IS a trajectory
# point; a missing key is not). Module-private by convention but
# exported via the test-oriented ``__all__`` so test modules can
# assert the sentinel identity without reaching into ``engine.py``.
_MISSING: Any = object()


def _extract_dotted(obj: Any, segments: list[str]) -> Any:
    """Navigate ``segments`` through ``obj`` (nested dicts only).

    Returns ``_MISSING`` when any intermediate segment is missing
    or when ``obj`` stops being a dict before consuming the path.
    Numeric list indexing is NOT supported at Step 9 (pre-impl
    audit M1) — a path like ``"items.0"`` will return ``_MISSING``
    because lists don't have a ``"0"`` key.
    """
    cursor: Any = obj
    for seg in segments:
        if not isinstance(cursor, dict):
            return _MISSING
        if seg not in cursor:
            return _MISSING
        cursor = cursor[seg]
    return cursor


class TrajectoryPoint(BaseModel):
    """One historical value of a single entity field.

    Attributes:
        tick: Logical tick when the value was recorded.
        value: JSON-serialisable value extracted at the field_path.
            A field validator recursively rejects non-JSON-native
            leaves (datetime, custom objects, Pydantic models nested
            inside dict/list); the ``dict[str, Any]`` / ``list[Any]``
            unions widen the type annotation but the validator
            narrows it at runtime.
        event_id: The ``WorldEvent`` whose state_delta produced
            this value — enables the consumer to pull the full
            event (action, actor_id, etc.) for explanation.
        entity_id: The entity whose field this trajectory tracks.
            Redundant with the caller's query parameter but useful
            for deserialisation / logging.
        field_path: Dotted field path the caller queried for. Copy
            of the query parameter; simplifies round-trip through
            serialisation.
    """

    model_config = ConfigDict(frozen=True)

    tick: int
    value: JsonValue
    event_id: EventId
    entity_id: EntityId
    field_path: str

    @field_validator("value", mode="before")
    @classmethod
    def _reject_non_json_value(cls, v: Any) -> Any:
        """Post-impl audit H3: ``dict[str, Any]`` / ``list[Any]``
        type annotations widen to ``Any`` recursively, so Pydantic
        v2 happily accepts a ``datetime`` (or any custom object)
        nested inside. A downstream product calling
        ``json.dumps(pt.value)`` would then crash at runtime. We
        probe the JSON-safety promise at construction by feeding
        the value through ``json.dumps`` with the default encoder
        — any ``TypeError`` surfaces at the model boundary, not
        mid-serialisation.
        """
        try:
            json.dumps(v)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"TrajectoryPoint.value must be JSON-native; {type(v).__name__} rejected: {exc}"
            ) from exc
        return v


__all__ = [
    "TrajectoryPoint",
    "JsonValue",
    "JsonScalar",
    "_MISSING",
    "_extract_dotted",
]
