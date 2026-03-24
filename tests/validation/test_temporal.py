"""Tests for terrarium.validation.temporal -- timestamp and ordering validation."""

from datetime import datetime

import pytest

from terrarium.core.types import ValidationType
from terrarium.validation.schema_contracts import TemporalOrderingRule
from terrarium.validation.temporal import TemporalValidator


@pytest.fixture
def validator():
    return TemporalValidator()


def test_valid_timestamp_past(validator):
    event = datetime(2024, 1, 1, 10, 0, 0)
    world = datetime(2024, 1, 1, 12, 0, 0)
    result = validator.validate_timestamp(event, world)
    assert result.valid is True
    assert result.validation_type == ValidationType.TEMPORAL


def test_valid_timestamp_equal(validator):
    t = datetime(2024, 6, 15, 8, 30, 0)
    result = validator.validate_timestamp(t, t)
    assert result.valid is True


def test_future_timestamp_rejected(validator):
    event = datetime(2024, 1, 2, 0, 0, 0)
    world = datetime(2024, 1, 1, 23, 59, 59)
    result = validator.validate_timestamp(event, world)
    assert result.valid is False
    assert len(result.errors) == 1


def test_ordering_correct(validator):
    before = datetime(2024, 1, 1, 10, 0, 0)
    after = datetime(2024, 1, 1, 11, 0, 0)
    result = validator.validate_ordering(before, after, "charge before refund")
    assert result.valid is True
    assert result.validation_type == ValidationType.TEMPORAL


def test_ordering_wrong(validator):
    before = datetime(2024, 1, 1, 12, 0, 0)
    after = datetime(2024, 1, 1, 11, 0, 0)
    result = validator.validate_ordering(before, after, "charge before refund")
    assert result.valid is False
    assert "charge before refund" in result.errors[0]


def test_ordering_equal(validator):
    t = datetime(2024, 3, 15, 9, 0, 0)
    result = validator.validate_ordering(t, t, "same-time events")
    assert result.valid is True


def test_validate_entity_orderings(validator):
    result = validator.validate_entity_orderings(
        "ticket",
        {
            "created_at": "2024-01-01T10:00:00",
            "updated_at": "2024-01-01T11:00:00",
        },
        [TemporalOrderingRule(before_field="created_at", after_field="updated_at")],
    )
    assert result.valid is True
