"""Tests for volnix.validation.amounts -- monetary amount and refund validation."""

import pytest

from volnix.core.types import ValidationType
from volnix.validation.amounts import AmountValidator


@pytest.fixture
def validator():
    return AmountValidator()


def test_refund_within_charge(validator):
    result = validator.validate_refund_amount(500, 1000)
    assert result.valid is True
    assert result.validation_type == ValidationType.AMOUNT


def test_refund_equal_charge(validator):
    result = validator.validate_refund_amount(1000, 1000)
    assert result.valid is True


def test_refund_exceeds_charge(validator):
    result = validator.validate_refund_amount(1500, 1000)
    assert result.valid is False
    assert any("1500" in e and "1000" in e for e in result.errors)


def test_budget_deduction_within(validator):
    result = validator.validate_budget_deduction(50.0, 100.0)
    assert result.valid is True


def test_budget_deduction_exceeds(validator):
    result = validator.validate_budget_deduction(150.0, 100.0)
    assert result.valid is False
    assert any("150" in e for e in result.errors)


def test_non_negative_positive(validator):
    result = validator.validate_non_negative(42.0, "balance")
    assert result.valid is True


def test_non_negative_zero(validator):
    result = validator.validate_non_negative(0.0, "balance")
    assert result.valid is True


def test_non_negative_negative(validator):
    result = validator.validate_non_negative(-1.0, "balance")
    assert result.valid is False
    assert any("balance" in e for e in result.errors)
