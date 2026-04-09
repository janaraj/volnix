"""Tests for wired ValidationStep with ValidationPipeline integration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

from volnix.core.context import ActionContext, ResponseProposal
from volnix.core.types import ActorId, EntityId, ServiceId, StateDelta, StepVerdict
from volnix.validation.step import ValidationStep

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(**overrides: Any) -> ActionContext:
    now = datetime.now(UTC)
    defaults: dict[str, Any] = {
        "request_id": "req-vstep-001",
        "actor_id": ActorId("actor-test"),
        "service_id": ServiceId("svc"),
        "action": "do_thing",
        "world_time": now,
        "wall_time": now,
        "tick": 1,
    }
    defaults.update(overrides)
    return ActionContext(**defaults)


def _make_state_engine(entities: dict[str, dict[str, Any]] | None = None) -> AsyncMock:
    """Stub state engine for deep validation tests."""
    engine = AsyncMock()
    store = entities or {}

    async def _get_entity(entity_type: str, entity_id: EntityId) -> dict[str, Any]:
        if entity_id in store:
            return store[entity_id]
        from volnix.core.errors import EntityNotFoundError

        raise EntityNotFoundError(f"{entity_type}/{entity_id}")

    engine.get_entity = AsyncMock(side_effect=_get_entity)
    engine.query_entities = AsyncMock(return_value=[])
    return engine


# ---------------------------------------------------------------------------
# Tests: no proposal
# ---------------------------------------------------------------------------


async def test_no_proposal_returns_allow():
    """When response_proposal is None, step returns ALLOW."""
    step = ValidationStep()
    ctx = _make_ctx()
    result = await step.execute(ctx)
    assert result.verdict == StepVerdict.ALLOW
    assert "No proposal" in result.message


# ---------------------------------------------------------------------------
# Tests: structural errors
# ---------------------------------------------------------------------------


async def test_structural_error_missing_entity_type():
    """StateDelta with empty entity_type is caught by structural check."""
    step = ValidationStep()
    ctx = _make_ctx()
    ctx.response_proposal = ResponseProposal(
        proposed_state_deltas=[
            StateDelta(
                entity_type="",
                entity_id=EntityId("e1"),
                operation="create",
                fields={"name": "x"},
            ),
        ],
    )
    result = await step.execute(ctx)
    assert result.verdict == StepVerdict.ERROR
    assert "missing entity_type" in result.message


async def test_structural_error_invalid_operation():
    """StateDelta with unknown operation is caught by structural check."""
    step = ValidationStep()
    ctx = _make_ctx()
    ctx.response_proposal = ResponseProposal(
        proposed_state_deltas=[
            StateDelta(
                entity_type="widget",
                entity_id=EntityId("w1"),
                operation="upsert",
                fields={"name": "x"},
            ),
        ],
    )
    result = await step.execute(ctx)
    assert result.verdict == StepVerdict.ERROR
    assert "Unknown operation" in result.message


# ---------------------------------------------------------------------------
# Tests: no metadata falls back to structural only
# ---------------------------------------------------------------------------


async def test_no_metadata_structural_only_allow():
    """Valid deltas without validation_metadata pass (structural only)."""
    step = ValidationStep()
    ctx = _make_ctx()
    ctx.response_proposal = ResponseProposal(
        response_body={"id": "w1"},
        proposed_state_deltas=[
            StateDelta(
                entity_type="widget",
                entity_id=EntityId("w1"),
                operation="create",
                fields={"name": "x"},
            ),
        ],
    )
    result = await step.execute(ctx)
    assert result.verdict == StepVerdict.ALLOW


# ---------------------------------------------------------------------------
# Tests: deep validation via ValidationPipeline
# ---------------------------------------------------------------------------


async def test_deep_validation_schema_failure():
    """Schema mismatch in validation_metadata triggers ERROR."""
    step = ValidationStep(state_engine=_make_state_engine())
    ctx = _make_ctx()
    schema = {
        "required": ["id", "status"],
        "properties": {
            "id": {"type": "string"},
            "status": {"type": "string"},
        },
    }
    ctx.response_proposal = ResponseProposal(
        response_body={"status": "ok"},  # missing "id"
        validation_metadata={"response_schema": schema},
    )
    result = await step.execute(ctx)
    assert result.verdict == StepVerdict.ERROR
    assert "id" in result.message.lower()


async def test_deep_validation_all_pass():
    """Proposal that satisfies both structural and deep checks returns ALLOW."""
    step = ValidationStep(state_engine=_make_state_engine())
    ctx = _make_ctx()
    schema = {
        "required": ["id"],
        "properties": {
            "id": {"type": "string"},
        },
    }
    ctx.response_proposal = ResponseProposal(
        response_body={"id": "w1"},
        proposed_state_deltas=[
            StateDelta(
                entity_type="widget",
                entity_id=EntityId("w1"),
                operation="create",
                fields={"name": "x"},
            ),
        ],
        validation_metadata={"response_schema": schema},
    )
    result = await step.execute(ctx)
    assert result.verdict == StepVerdict.ALLOW


async def test_deep_validation_state_machine_failure():
    """Invalid state transition caught by deep validation."""
    step = ValidationStep(state_engine=_make_state_engine())
    ctx = _make_ctx()
    sm = {
        "order": {
            "transitions": {
                "pending": ["shipped"],
                "shipped": ["delivered"],
                "delivered": [],
            },
        },
    }
    ctx.response_proposal = ResponseProposal(
        response_body={"id": "o1"},
        proposed_state_deltas=[
            StateDelta(
                entity_type="order",
                entity_id=EntityId("o1"),
                operation="update",
                fields={"status": "pending"},
                previous_fields={"status": "delivered"},
            ),
        ],
        validation_metadata={"state_machines": sm},
    )
    result = await step.execute(ctx)
    assert result.verdict == StepVerdict.ERROR


# ---------------------------------------------------------------------------
# Tests: ledger recording
# ---------------------------------------------------------------------------


async def test_ledger_records_on_pass(mock_ledger):
    """Ledger entry is created when validation passes."""
    step = ValidationStep(ledger=mock_ledger)
    ctx = _make_ctx()
    ctx.response_proposal = ResponseProposal(
        response_body={"ok": True},
        proposed_state_deltas=[
            StateDelta(
                entity_type="thing",
                entity_id=EntityId("t1"),
                operation="create",
                fields={"a": 1},
            ),
        ],
    )
    await step.execute(ctx)
    assert mock_ledger.append.called
    entry = mock_ledger.entries[0]
    assert entry.passed is True


async def test_ledger_records_on_fail(mock_ledger):
    """Ledger entry is created when validation fails."""
    step = ValidationStep(ledger=mock_ledger)
    ctx = _make_ctx()
    ctx.response_proposal = ResponseProposal(
        proposed_state_deltas=[
            StateDelta(
                entity_type="",
                entity_id=EntityId("x"),
                operation="create",
                fields={},
            ),
        ],
    )
    await step.execute(ctx)
    assert mock_ledger.append.called
    entry = mock_ledger.entries[0]
    assert entry.passed is False
