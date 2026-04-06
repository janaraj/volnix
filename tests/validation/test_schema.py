"""Tests for volnix.validation.schema -- response schema validation."""

from volnix.core.types import ValidationType
from volnix.validation.schema import SchemaValidator, ValidationResult

# ---------------------------------------------------------------------------
# ValidationResult tests
# ---------------------------------------------------------------------------


def test_validation_result_defaults():
    r = ValidationResult()
    assert r.valid is True
    assert r.errors == []
    assert r.warnings == []
    assert r.validation_type is None


def test_validation_result_merge_both_valid():
    r1 = ValidationResult(valid=True, warnings=["w1"])
    r2 = ValidationResult(valid=True, warnings=["w2"])
    merged = r1.merge(r2)
    assert merged is not r1
    assert merged is not r2
    assert merged.valid is True
    assert merged.warnings == ["w1", "w2"]
    assert merged.errors == []


def test_validation_result_merge_one_invalid():
    r1 = ValidationResult(
        valid=False,
        errors=["e1"],
        validation_type=ValidationType.SCHEMA,
    )
    r2 = ValidationResult(
        valid=True,
        warnings=["w1"],
        validation_type=ValidationType.AMOUNT,
    )
    merged = r1.merge(r2)
    assert merged.valid is False
    assert merged.errors == ["e1"]
    assert merged.warnings == ["w1"]
    # Different types → None
    assert merged.validation_type is None


# ---------------------------------------------------------------------------
# SchemaValidator tests
# ---------------------------------------------------------------------------


SAMPLE_SCHEMA: dict = {
    "required": ["id", "status"],
    "properties": {
        "id": {"type": "string"},
        "status": {"type": "string", "enum": ["pending", "succeeded"]},
        "amount": {"type": "integer", "minimum": 0, "maximum": 1000},
    },
}


def test_validate_response_valid():
    v = SchemaValidator()
    result = v.validate_response({"id": "abc", "status": "pending", "amount": 100}, SAMPLE_SCHEMA)
    assert result.valid is True
    assert result.errors == []
    assert result.validation_type == ValidationType.SCHEMA


def test_validate_response_missing_required():
    v = SchemaValidator()
    result = v.validate_response({"status": "pending"}, SAMPLE_SCHEMA)
    assert result.valid is False
    assert any("id" in e for e in result.errors)


def test_validate_response_wrong_type():
    v = SchemaValidator()
    result = v.validate_response({"id": 123, "status": "pending"}, SAMPLE_SCHEMA)
    assert result.valid is False
    assert any("type" in e.lower() for e in result.errors)


def test_validate_response_invalid_enum():
    v = SchemaValidator()
    result = v.validate_response({"id": "abc", "status": "cancelled"}, SAMPLE_SCHEMA)
    assert result.valid is False
    assert any("cancelled" in e for e in result.errors)


def test_validate_response_below_minimum():
    v = SchemaValidator()
    result = v.validate_response({"id": "abc", "status": "pending", "amount": -5}, SAMPLE_SCHEMA)
    assert result.valid is False
    assert any("minimum" in e.lower() for e in result.errors)


def test_validate_response_above_maximum():
    v = SchemaValidator()
    result = v.validate_response({"id": "abc", "status": "pending", "amount": 2000}, SAMPLE_SCHEMA)
    assert result.valid is False
    assert any("maximum" in e.lower() for e in result.errors)


def test_validate_entity_same_logic():
    """validate_entity uses the same logic as validate_response."""
    v = SchemaValidator()
    result = v.validate_entity({"id": "e1", "status": "succeeded"}, SAMPLE_SCHEMA)
    assert result.valid is True
    assert result.validation_type == ValidationType.SCHEMA

    bad = v.validate_entity({"status": "succeeded"}, SAMPLE_SCHEMA)
    assert bad.valid is False
