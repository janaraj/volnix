"""Normalization helpers for compiler-time schema contracts.

Compiler validation reads the same service-pack schemas used elsewhere and
extracts explicit metadata contracts from them. This module does not infer
references or temporal rules from field names.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

_LEGACY_TYPE_MAP = {
    "string": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
}


class ReferenceRule(BaseModel, frozen=True):
    """Explicit reference contract for one field."""

    field: str
    target_entity_type: str


class TemporalOrderingRule(BaseModel, frozen=True):
    """Explicit temporal ordering contract for one entity schema."""

    before_field: str
    after_field: str
    context: str = ""


class NormalizedEntitySchema(BaseModel, frozen=True):
    """Canonical schema contract used by compiler validators."""

    json_schema: dict[str, Any] = Field(default_factory=dict)
    identity_field: str | None = None
    references: list[ReferenceRule] = Field(default_factory=list)
    temporal_orderings: list[TemporalOrderingRule] = Field(default_factory=list)


def normalize_entity_schema(schema: dict[str, Any]) -> NormalizedEntitySchema:
    """Normalize pack or legacy validation schema into compiler contracts."""
    json_schema = _normalize_json_schema(schema)
    properties = json_schema.get("properties", {})
    references: list[ReferenceRule] = []

    for field_name, field_schema in properties.items():
        ref_meta = field_schema.get("x-volnix-ref")
        if isinstance(ref_meta, str) and ref_meta:
            references.append(
                ReferenceRule(field=field_name, target_entity_type=ref_meta)
            )
        elif isinstance(ref_meta, dict):
            target_entity_type = ref_meta.get("entity_type")
            if target_entity_type:
                references.append(
                    ReferenceRule(
                        field=field_name,
                        target_entity_type=str(target_entity_type),
                    )
                )

    orderings = _extract_temporal_orderings(schema, json_schema)
    identity_field = _extract_identity_field(schema, json_schema)

    return NormalizedEntitySchema(
        json_schema=json_schema,
        identity_field=identity_field,
        references=references,
        temporal_orderings=orderings,
    )


def normalize_entity_schemas(
    schemas: dict[str, dict[str, Any]],
) -> dict[str, NormalizedEntitySchema]:
    """Normalize every entity schema in a service surface."""
    return {
        entity_type: normalize_entity_schema(schema)
        for entity_type, schema in schemas.items()
    }


def _normalize_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-Schema-like representation for validation primitives."""
    if "properties" in schema or schema.get("type") == "object":
        normalized = dict(schema)
        normalized.setdefault("type", "object")
        normalized.setdefault("properties", {})
        return normalized

    if "fields" not in schema:
        return {"type": "object", "properties": {}}

    properties: dict[str, Any] = {}
    for field_name, field_type in schema.get("fields", {}).items():
        if isinstance(field_type, str) and field_type.startswith("ref:"):
            properties[field_name] = {
                "type": "string",
                "x-volnix-ref": field_type.split(":", 1)[1],
            }
            continue

        field_schema: dict[str, Any] = {}
        if isinstance(field_type, str):
            json_type = _LEGACY_TYPE_MAP.get(field_type)
            if json_type is not None:
                field_schema["type"] = json_type
        properties[field_name] = field_schema

    return {
        "type": "object",
        "properties": properties,
    }


def _extract_identity_field(
    raw_schema: dict[str, Any],
    json_schema: dict[str, Any],
) -> str | None:
    """Read the identity field contract for an entity schema."""
    for schema in (raw_schema, json_schema):
        identity_field = schema.get("x-volnix-identity")
        if isinstance(identity_field, str) and identity_field:
            return identity_field

    if "id" in json_schema.get("properties", {}):
        return "id"
    return None


def _extract_temporal_orderings(
    raw_schema: dict[str, Any],
    json_schema: dict[str, Any],
) -> list[TemporalOrderingRule]:
    """Read explicit temporal ordering rules from schema metadata."""
    candidates = raw_schema.get("x-volnix-ordering")
    if candidates is None:
        candidates = json_schema.get("x-volnix-ordering", [])

    rules: list[TemporalOrderingRule] = []
    if not isinstance(candidates, list):
        return rules

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        before_field = candidate.get("before_field") or candidate.get("before")
        after_field = candidate.get("after_field") or candidate.get("after")
        if not before_field or not after_field:
            continue
        rules.append(
            TemporalOrderingRule(
                before_field=str(before_field),
                after_field=str(after_field),
                context=str(candidate.get("context", "")),
            )
        )
    return rules
