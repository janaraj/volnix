"""Tests for volnix.validation.state_machine -- state transition validation."""

import pytest

from volnix.core.types import ValidationType
from volnix.validation.state_machine import StateMachineValidator


SM: dict = {
    "transitions": {
        "open": ["in_progress", "closed"],
        "in_progress": ["closed"],
        "closed": ["open"],
    },
}


@pytest.fixture
def validator():
    return StateMachineValidator()


def test_valid_transition(validator):
    result = validator.validate_transition("open", "in_progress", SM)
    assert result.valid is True
    assert result.validation_type == ValidationType.STATE_MACHINE


def test_invalid_transition(validator):
    result = validator.validate_transition("open", "open", SM)
    assert result.valid is False
    assert len(result.errors) == 1
    assert "open" in result.errors[0]


def test_get_valid_transitions(validator):
    targets = validator.get_valid_transitions("open", SM)
    assert targets == ["in_progress", "closed"]


def test_get_valid_transitions_unknown_state(validator):
    targets = validator.get_valid_transitions("nonexistent", SM)
    assert targets == []


def test_transition_from_terminal(validator):
    """closed → open is defined, but closed → in_progress is not."""
    ok = validator.validate_transition("closed", "open", SM)
    assert ok.valid is True

    bad = validator.validate_transition("closed", "in_progress", SM)
    assert bad.valid is False


def test_empty_state_machine(validator):
    result = validator.validate_transition("open", "closed", {"transitions": {}})
    assert result.valid is False


def test_self_transition(validator):
    sm_with_self = {
        "transitions": {
            "active": ["active", "done"],
        },
    }
    result = validator.validate_transition("active", "active", sm_with_self)
    assert result.valid is True


def test_transition_error_message(validator):
    result = validator.validate_transition("in_progress", "open", SM)
    assert result.valid is False
    assert "in_progress" in result.errors[0]
    assert "open" in result.errors[0]
