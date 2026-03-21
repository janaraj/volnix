"""Tests for terrarium.core.events — event dataclasses and serialization."""
import pytest
from terrarium.core.events import (
    Event, WorldEvent,
    PermissionDeniedEvent, PolicyBlockEvent, PolicyHoldEvent,
    BudgetExhaustedEvent, CapabilityGapEvent,
)


def test_event_id_generation():
    ...


def test_event_base_fields():
    ...


def test_world_event_fields():
    ...


def test_permission_denied_event():
    ...


def test_policy_block_event():
    ...


def test_policy_hold_event():
    ...


def test_budget_exhausted_event():
    ...


def test_capability_gap_event():
    ...


def test_event_serialization_roundtrip():
    ...


def test_event_type_discriminator():
    ...
