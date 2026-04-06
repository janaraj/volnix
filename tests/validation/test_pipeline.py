"""Tests for volnix.validation.pipeline -- composite validation pipeline."""

from __future__ import annotations

from typing import Any

import pytest

from volnix.core.context import ResponseProposal
from volnix.core.errors import EntityNotFoundError
from volnix.core.types import EntityId, StateDelta
from volnix.validation.pipeline import ValidationPipeline

# ---------------------------------------------------------------------------
# Mock state engine
# ---------------------------------------------------------------------------


class MockStateEngine:
    """Minimal mock implementing StateEngineProtocol for pipeline tests."""

    def __init__(self, entities: dict[str, dict[str, Any]] | None = None) -> None:
        self._entities = entities or {}

    async def get_entity(self, entity_type: str, entity_id: EntityId) -> dict[str, Any]:
        if entity_id in self._entities:
            return self._entities[entity_id]
        raise EntityNotFoundError(f"Entity {entity_id} not found")

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


RESPONSE_SCHEMA: dict = {
    "required": ["id", "status"],
    "properties": {
        "id": {"type": "string"},
        "status": {"type": "string", "enum": ["pending", "succeeded"]},
    },
}

STATE_MACHINES: dict = {
    "charge": {
        "transitions": {
            "pending": ["succeeded", "failed"],
            "succeeded": [],
            "failed": [],
        },
    },
}

ENTITY_SCHEMAS: dict = {
    "refund": {
        "fields": {
            "charge": "ref:charge",
            "amount": "integer",
        },
    },
}


def _valid_proposal() -> ResponseProposal:
    return ResponseProposal(
        response_body={"id": "ch_1", "status": "pending"},
    )


def _proposal_with_delta(
    fields: dict | None = None,
    previous_fields: dict | None = None,
    entity_type: str = "charge",
) -> ResponseProposal:
    return ResponseProposal(
        response_body={"id": "ch_1", "status": "pending"},
        proposed_state_deltas=[
            StateDelta(
                entity_type=entity_type,
                entity_id=EntityId("ch_1"),
                operation="update",
                fields=fields or {},
                previous_fields=previous_fields,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_all_valid():
    pipe = ValidationPipeline()
    state = MockStateEngine({"ch_1": {"id": "ch_1"}})
    proposal = _valid_proposal()
    result = await pipe.validate_response_proposal(proposal, state, response_schema=RESPONSE_SCHEMA)
    assert result.valid is True


@pytest.mark.asyncio
async def test_pipeline_schema_failure():
    pipe = ValidationPipeline()
    state = MockStateEngine()
    proposal = ResponseProposal(response_body={"status": "pending"})  # missing id
    result = await pipe.validate_response_proposal(proposal, state, response_schema=RESPONSE_SCHEMA)
    assert result.valid is False
    assert any("id" in e for e in result.errors)


@pytest.mark.asyncio
async def test_pipeline_state_machine_failure():
    pipe = ValidationPipeline()
    state = MockStateEngine()
    proposal = _proposal_with_delta(
        fields={"status": "pending"},
        previous_fields={"status": "succeeded"},
    )
    result = await pipe.validate_response_proposal(proposal, state, state_machines=STATE_MACHINES)
    assert result.valid is False


@pytest.mark.asyncio
async def test_pipeline_consistency_failure():
    pipe = ValidationPipeline()
    state = MockStateEngine({})  # no entities
    proposal = ResponseProposal(
        response_body={"id": "r_1", "status": "pending"},
        proposed_state_deltas=[
            StateDelta(
                entity_type="refund",
                entity_id=EntityId("r_1"),
                operation="create",
                fields={"charge": "ch_missing", "amount": 100},
            ),
        ],
    )
    result = await pipe.validate_response_proposal(proposal, state, entity_schemas=ENTITY_SCHEMAS)
    assert result.valid is False
    assert any("ch_missing" in e for e in result.errors)


@pytest.mark.asyncio
async def test_pipeline_amount_failure():
    pipe = ValidationPipeline()
    state = MockStateEngine()
    proposal = _proposal_with_delta(fields={"amount": -50})
    result = await pipe.validate_response_proposal(proposal, state)
    assert result.valid is False
    assert any("negative" in e.lower() for e in result.errors)


@pytest.mark.asyncio
async def test_pipeline_multiple_failures():
    pipe = ValidationPipeline()
    state = MockStateEngine({})
    proposal = ResponseProposal(
        response_body={"status": "invalid_val"},  # missing id, bad enum
        proposed_state_deltas=[
            StateDelta(
                entity_type="refund",
                entity_id=EntityId("r_1"),
                operation="create",
                fields={"charge": "ch_missing", "amount": -10},
            ),
        ],
    )
    result = await pipe.validate_response_proposal(
        proposal,
        state,
        response_schema=RESPONSE_SCHEMA,
        entity_schemas=ENTITY_SCHEMAS,
    )
    assert result.valid is False
    # At least: missing id, invalid enum, missing ref, negative amount
    assert len(result.errors) >= 3


@pytest.mark.asyncio
async def test_pipeline_retry_success():
    """LLM callback fixes the proposal on retry."""
    pipe = ValidationPipeline()
    state = MockStateEngine()

    bad_proposal = ResponseProposal(response_body={"status": "pending"})  # missing id
    good_proposal = ResponseProposal(response_body={"id": "ch_1", "status": "pending"})

    async def fix_callback(proposal, errors):
        return good_proposal

    final_proposal, result = await pipe.validate_with_retry(
        bad_proposal,
        state,
        fix_callback,
        max_retries=1,
        response_schema=RESPONSE_SCHEMA,
    )
    assert result.valid is True
    assert final_proposal is good_proposal


@pytest.mark.asyncio
async def test_pipeline_retry_exhausted():
    """LLM callback cannot fix the proposal; retries exhausted."""
    pipe = ValidationPipeline()
    state = MockStateEngine()

    bad_proposal = ResponseProposal(response_body={"status": "pending"})

    async def no_fix_callback(proposal, errors):
        return proposal  # still broken

    final_proposal, result = await pipe.validate_with_retry(
        bad_proposal,
        state,
        no_fix_callback,
        max_retries=2,
        response_schema=RESPONSE_SCHEMA,
    )
    assert result.valid is False


@pytest.mark.asyncio
async def test_pipeline_no_schema():
    """When no schema is provided, schema validation is skipped."""
    pipe = ValidationPipeline()
    state = MockStateEngine()
    proposal = ResponseProposal(response_body={"anything": "goes"})
    result = await pipe.validate_response_proposal(proposal, state)
    assert result.valid is True


@pytest.mark.asyncio
async def test_pipeline_no_state_machines():
    """When no state machines are provided, SM validation is skipped."""
    pipe = ValidationPipeline()
    state = MockStateEngine()
    proposal = _proposal_with_delta(
        fields={"status": "pending"},
        previous_fields={"status": "succeeded"},
    )
    # Without state_machines parameter, transition validation is skipped
    result = await pipe.validate_response_proposal(proposal, state)
    assert result.valid is True
