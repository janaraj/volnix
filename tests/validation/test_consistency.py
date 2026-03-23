"""Tests for terrarium.validation.consistency -- referential integrity checks."""

from __future__ import annotations

from typing import Any

import pytest

from terrarium.core.errors import EntityNotFoundError
from terrarium.core.types import EntityId, StateDelta, ValidationType
from terrarium.validation.consistency import ConsistencyValidator


# ---------------------------------------------------------------------------
# Mock state engine
# ---------------------------------------------------------------------------


class MockStateEngine:
    """Minimal mock implementing get_entity for consistency tests."""

    def __init__(self, entities: dict[str, dict[str, Any]]) -> None:
        self._entities = entities

    async def get_entity(self, entity_type: str, entity_id: EntityId) -> dict[str, Any]:
        if entity_id in self._entities:
            return self._entities[entity_id]
        raise EntityNotFoundError(f"Entity {entity_id} not found")

    # The remaining protocol methods are unused in these tests.
    async def query_entities(self, entity_type, filters=None):
        return []

    async def propose_mutation(self, delta):
        return delta

    async def commit_event(self, event):
        pass

    async def snapshot(self):
        return "snap"

    async def fork(self, snapshot_id):
        return "world"

    async def diff(self, a, b):
        return []

    async def get_causal_chain(self, event_id):
        return []

    async def get_timeline(self, entity_id, start=None, end=None):
        return []


ENTITY_SCHEMA = {
    "fields": {
        "charge": "ref:charge",
        "customer": "ref:customer",
        "amount": "integer",
    },
}


@pytest.fixture
def validator():
    return ConsistencyValidator()


@pytest.mark.asyncio
async def test_validate_references_all_exist(validator):
    state = MockStateEngine({"ch_1": {"id": "ch_1"}, "cust_1": {"id": "cust_1"}})
    delta = StateDelta(
        entity_type="refund",
        entity_id=EntityId("ref_1"),
        operation="create",
        fields={"charge": "ch_1", "customer": "cust_1", "amount": 500},
    )
    result = await validator.validate_references(delta, ENTITY_SCHEMA, state)
    assert result.valid is True
    assert result.validation_type == ValidationType.CONSISTENCY


@pytest.mark.asyncio
async def test_validate_references_missing(validator):
    state = MockStateEngine({"ch_1": {"id": "ch_1"}})
    delta = StateDelta(
        entity_type="refund",
        entity_id=EntityId("ref_1"),
        operation="create",
        fields={"charge": "ch_1", "customer": "cust_999", "amount": 500},
    )
    result = await validator.validate_references(delta, ENTITY_SCHEMA, state)
    assert result.valid is False
    assert any("cust_999" in e for e in result.errors)


@pytest.mark.asyncio
async def test_validate_references_no_ref_fields(validator):
    schema = {"fields": {"amount": "integer", "note": "string"}}
    state = MockStateEngine({})
    delta = StateDelta(
        entity_type="payment",
        entity_id=EntityId("p_1"),
        operation="create",
        fields={"amount": 100, "note": "ok"},
    )
    result = await validator.validate_references(delta, schema, state)
    assert result.valid is True


@pytest.mark.asyncio
async def test_validate_references_field_not_in_delta(validator):
    """If a ref field is defined in schema but not present in delta, skip it."""
    state = MockStateEngine({})
    delta = StateDelta(
        entity_type="refund",
        entity_id=EntityId("ref_1"),
        operation="create",
        fields={"amount": 500},
    )
    result = await validator.validate_references(delta, ENTITY_SCHEMA, state)
    assert result.valid is True


@pytest.mark.asyncio
async def test_validate_entity_exists_found(validator):
    state = MockStateEngine({"ch_1": {"id": "ch_1", "type": "charge"}})
    result = await validator.validate_entity_exists("charge", EntityId("ch_1"), state)
    assert result.valid is True


@pytest.mark.asyncio
async def test_validate_entity_exists_missing(validator):
    state = MockStateEngine({})
    result = await validator.validate_entity_exists("charge", EntityId("ch_999"), state)
    assert result.valid is False
    assert any("ch_999" in e for e in result.errors)


@pytest.mark.asyncio
async def test_validate_references_multiple_refs(validator):
    """Both ref fields missing should produce two errors."""
    state = MockStateEngine({})
    delta = StateDelta(
        entity_type="refund",
        entity_id=EntityId("ref_1"),
        operation="create",
        fields={"charge": "ch_missing", "customer": "cust_missing", "amount": 10},
    )
    result = await validator.validate_references(delta, ENTITY_SCHEMA, state)
    assert result.valid is False
    assert len(result.errors) == 2


@pytest.mark.asyncio
async def test_consistency_returns_validation_type(validator):
    state = MockStateEngine({"x": {"id": "x"}})
    result = await validator.validate_entity_exists("thing", EntityId("x"), state)
    assert result.validation_type == ValidationType.CONSISTENCY
