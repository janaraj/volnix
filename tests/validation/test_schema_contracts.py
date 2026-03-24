"""Tests for compiler schema-contract normalization."""

from terrarium.validation.schema_contracts import normalize_entity_schema


def test_normalize_json_schema_with_reference_and_identity():
    schema = {
        "type": "object",
        "x-terrarium-identity": "ticket_id",
        "properties": {
            "ticket_id": {"type": "string"},
            "customer_id": {"type": "string", "x-terrarium-ref": "customer"},
        },
    }

    normalized = normalize_entity_schema(schema)

    assert normalized.identity_field == "ticket_id"
    assert normalized.references[0].field == "customer_id"
    assert normalized.references[0].target_entity_type == "customer"


def test_normalize_json_schema_with_temporal_ordering():
    schema = {
        "type": "object",
        "properties": {
            "created_at": {"type": "string"},
            "updated_at": {"type": "string"},
        },
        "x-terrarium-ordering": [
            {"before": "created_at", "after": "updated_at", "context": "entity lifecycle"},
        ],
    }

    normalized = normalize_entity_schema(schema)

    assert len(normalized.temporal_orderings) == 1
    assert normalized.temporal_orderings[0].before_field == "created_at"
    assert normalized.temporal_orderings[0].after_field == "updated_at"


def test_normalize_legacy_ref_schema():
    schema = {
        "fields": {
            "id": "string",
            "charge": "ref:charge",
        },
    }

    normalized = normalize_entity_schema(schema)

    assert normalized.identity_field == "id"
    assert normalized.json_schema["properties"]["charge"]["x-terrarium-ref"] == "charge"
    assert normalized.references[0].target_entity_type == "charge"
