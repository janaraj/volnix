"""Protocol and signature conformance guardrails."""

from __future__ import annotations

import pytest

from volnix.core.protocols import (
    AdapterProtocol,
    BudgetEngineProtocol,
    GatewayProtocol,
    PolicyEngineProtocol,
    StateEngineProtocol,
)
from volnix.core.types import EntityId, StateDelta, ValidationType
from volnix.engines.adapter.protocols.http_rest import HTTPRestAdapter
from volnix.engines.adapter.protocols.mcp_server import MCPServerAdapter
from volnix.engines.budget.engine import BudgetEngine
from volnix.engines.policy.engine import PolicyEngine
from volnix.engines.state.engine import StateEngine
from volnix.gateway.gateway import Gateway
from volnix.validation.consistency import ConsistencyValidator
from tests.architecture.helpers import assert_method_signature_matches_protocol
from tests.helpers.guardrails import staged_guardrail

pytestmark = [pytest.mark.architecture, pytest.mark.contract]


def test_state_engine_matches_state_protocol():
    assert_method_signature_matches_protocol(
        StateEngine,
        StateEngineProtocol,
        [
            "get_entity",
            "query_entities",
            "propose_mutation",
            "commit_event",
            "snapshot",
            "fork",
            "diff",
            "get_causal_chain",
            "get_timeline",
        ],
    )


def test_policy_engine_matches_policy_protocol():
    assert_method_signature_matches_protocol(
        PolicyEngine,
        PolicyEngineProtocol,
        ["evaluate", "get_active_policies", "resolve_hold"],
    )


def test_budget_engine_matches_budget_protocol():
    assert_method_signature_matches_protocol(
        BudgetEngine,
        BudgetEngineProtocol,
        ["check_budget", "deduct", "get_remaining", "get_spend_curve"],
    )


def test_gateway_matches_gateway_protocol():
    assert_method_signature_matches_protocol(
        Gateway,
        GatewayProtocol,
        ["handle_request", "deliver_observation"],
    )


def test_http_adapter_matches_adapter_protocol():
    assert_method_signature_matches_protocol(
        HTTPRestAdapter,
        AdapterProtocol,
        ["translate_inbound", "translate_outbound", "get_tool_manifest"],
    )


def test_mcp_adapter_matches_adapter_protocol():
    assert_method_signature_matches_protocol(
        MCPServerAdapter,
        AdapterProtocol,
        ["translate_inbound", "translate_outbound", "get_tool_manifest"],
    )


class StrictStateEngine:
    """Minimal state object matching the real StateEngineProtocol signature."""

    def __init__(self, existing: dict[tuple[str, str], dict]):
        self._existing = existing

    async def get_entity(self, entity_type: str, entity_id: EntityId) -> dict:
        key = (entity_type, str(entity_id))
        if key not in self._existing:
            from volnix.core.errors import EntityNotFoundError

            raise EntityNotFoundError(f"{entity_type}/{entity_id}")
        return self._existing[key]

    async def query_entities(self, entity_type: str, filters=None):
        return []

    async def propose_mutation(self, deltas):
        return deltas

    async def commit_event(self, event):
        return "evt-test"

    async def snapshot(self, label: str = "default"):
        return "snap-test"

    async def fork(self, snapshot_id):
        return "world-test"

    async def diff(self, snapshot_a, snapshot_b):
        return []

    async def get_causal_chain(self, event_id, direction: str = "backward"):
        return []

    async def get_timeline(self, start=None, end=None, entity_id=None):
        return []


@pytest.mark.asyncio
async def test_consistency_validator_works_with_real_state_protocol_shape():
    validator = ConsistencyValidator()
    state = StrictStateEngine({("charge", "ch_1"): {"id": "ch_1"}})
    delta = StateDelta(
        entity_type="refund",
        entity_id=EntityId("ref_1"),
        operation="create",
        fields={"charge": "ch_1"},
    )
    schema = {"fields": {"charge": "ref:charge"}}

    result = await validator.validate_references(delta, schema, state)

    assert result.valid is True
    assert result.validation_type == ValidationType.CONSISTENCY
