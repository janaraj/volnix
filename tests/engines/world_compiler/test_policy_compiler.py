"""Tests for NL policy trigger compilation during world compilation."""
import json

import pytest
from unittest.mock import AsyncMock

from volnix.engines.world_compiler.engine import WorldCompilerEngine
from volnix.engines.world_compiler.plan import ServiceResolution, WorldPlan
from volnix.kernel.surface import APIOperation, ServiceSurface
from volnix.llm.types import LLMResponse


def _make_surface(
    svc_name: str, *operations: tuple[str, str, str]
) -> ServiceSurface:
    """Build a ServiceSurface from service name and (name, service, desc) tuples."""
    ops = [
        APIOperation(name=name, service=svc, description=desc)
        for name, svc, desc in operations
    ]
    return ServiceSurface(
        service_name=svc_name,
        category="general",
        source="tier1_pack",
        fidelity_tier=1,
        operations=ops,
    )


def _make_plan(
    policies: list[dict],
    services: dict[str, ServiceResolution] | None = None,
) -> WorldPlan:
    """Build a minimal WorldPlan with policies and services."""
    if services is None:
        services = {
            "notion": ServiceResolution(
                service_name="notion",
                spec_reference="verified/notion",
                surface=_make_surface(
                    "notion",
                    ("pages.retrieve", "notion", "Retrieve a page"),
                    ("pages.update", "notion", "Update a page"),
                    ("pages.create", "notion", "Create a new page"),
                    ("databases.query", "notion", "Query a database"),
                    ("search", "notion", "Search across all pages"),
                ),
                resolution_source="tier1_pack",
            ),
            "slack": ServiceResolution(
                service_name="slack",
                spec_reference="verified/slack",
                surface=_make_surface(
                    "slack",
                    ("channels.list", "slack", "List channels"),
                    ("chat.postMessage", "slack", "Send a message"),
                ),
                resolution_source="tier1_pack",
            ),
        }
    return WorldPlan(
        name="Test World",
        description="Test",
        services=services,
        policies=policies,
    )


def _make_llm_response(compiled_policies: list[dict]) -> LLMResponse:
    """Build a mock LLM response with compiled policies."""
    return LLMResponse(
        content="",
        structured_output={"compiled_policies": compiled_policies},
        provider="mock",
        model="mock",
        latency_ms=0,
    )


async def _compile(plan: WorldPlan, llm_response: LLMResponse) -> WorldPlan:
    """Run _compile_policy_triggers on a plan with a mock router."""
    engine = WorldCompilerEngine()
    engine._llm_router = AsyncMock()
    engine._llm_router.route = AsyncMock(return_value=llm_response)
    return await engine._compile_policy_triggers(plan)


class TestCompilePolicyTriggers:
    """Test _compile_policy_triggers method."""

    async def test_compile_nl_trigger_basic(self):
        """Single NL trigger compiled to one dict trigger."""
        plan = _make_plan([
            {
                "name": "Archive approval",
                "trigger": "archiving a database or more than 5 pages",
                "enforcement": "hold",
                "hold_config": {"approver_role": "admin"},
            }
        ])
        llm_resp = _make_llm_response([
            {
                "policy_name": "Archive approval",
                "triggers": [
                    {"action": "pages.update", "condition": "input.archived == true"},
                ],
            }
        ])

        result = await _compile(plan, llm_resp)

        assert len(result.policies) == 1
        policy = result.policies[0]
        assert isinstance(policy["trigger"], dict)
        assert policy["trigger"]["action"] == "pages.update"
        assert policy["trigger"]["condition"] == "input.archived == true"
        assert policy["enforcement"] == "hold"
        assert policy["_compiled_from_nl"] == "archiving a database or more than 5 pages"

    async def test_compile_nl_trigger_multi_action(self):
        """NL trigger that maps to multiple actions creates cloned policies."""
        plan = _make_plan([
            {
                "name": "Block list operations",
                "trigger": "block all list operations on sensitive data",
                "enforcement": "block",
            }
        ])
        llm_resp = _make_llm_response([
            {
                "policy_name": "Block list operations",
                "triggers": [
                    {"action": "channels.list"},
                    {"action": "databases.query"},
                ],
            }
        ])

        result = await _compile(plan, llm_resp)

        assert len(result.policies) == 2
        # First replaces in-place
        assert result.policies[0]["trigger"]["action"] == "channels.list"
        assert result.policies[0]["enforcement"] == "block"
        # Second is appended clone
        assert result.policies[1]["trigger"]["action"] == "databases.query"
        assert result.policies[1]["enforcement"] == "block"
        assert "Block list operations" in result.policies[1]["name"]

    async def test_compile_preserves_dict_triggers(self):
        """Dict triggers pass through — no LLM call made."""
        plan = _make_plan([
            {
                "name": "Archive approval",
                "trigger": {"action": "pages.update", "condition": "input.archived == true"},
                "enforcement": "hold",
            }
        ])

        engine = WorldCompilerEngine()
        engine._llm_router = AsyncMock()

        result = await engine._compile_policy_triggers(plan)

        # No LLM call
        engine._llm_router.route.assert_not_called()
        # Policy unchanged
        assert result.policies == plan.policies

    async def test_compile_mixed_triggers(self):
        """Only NL triggers compiled; dict triggers untouched."""
        plan = _make_plan([
            {
                "name": "Dict policy",
                "trigger": {"action": "pages.update"},
                "enforcement": "hold",
            },
            {
                "name": "NL policy",
                "trigger": "refund amount exceeds limit",
                "enforcement": "block",
            },
        ])
        llm_resp = _make_llm_response([
            {
                "policy_name": "NL policy",
                "triggers": [{"action": "pages.create"}],
            }
        ])

        result = await _compile(plan, llm_resp)

        # Dict trigger unchanged
        assert isinstance(result.policies[0]["trigger"], dict)
        assert result.policies[0]["trigger"]["action"] == "pages.update"
        # NL trigger compiled
        assert isinstance(result.policies[1]["trigger"], dict)
        assert result.policies[1]["trigger"]["action"] == "pages.create"
        assert result.policies[1]["_compiled_from_nl"] == "refund amount exceeds limit"

    async def test_compile_unresolvable_trigger(self):
        """Unresolvable trigger adds warning and preserves original."""
        plan = _make_plan([
            {
                "name": "Conceptual policy",
                "trigger": "conclusion stated without supporting data",
                "enforcement": "escalate",
            }
        ])
        llm_resp = _make_llm_response([
            {
                "policy_name": "Conceptual policy",
                "triggers": [],
                "unresolvable": True,
                "reason": "describes a semantic situation, not an API operation",
            }
        ])

        result = await _compile(plan, llm_resp)

        # Original preserved (still a string trigger)
        assert isinstance(result.policies[0]["trigger"], str)
        # Warning added
        assert any("unresolvable" in w for w in result.warnings)

    async def test_compile_no_services(self):
        """No resolved services → early return with original plan."""
        plan = _make_plan(
            policies=[
                {
                    "name": "NL policy",
                    "trigger": "some natural language trigger",
                    "enforcement": "block",
                }
            ],
            services={},
        )

        engine = WorldCompilerEngine()
        engine._llm_router = AsyncMock()

        result = await engine._compile_policy_triggers(plan)

        # No LLM call — no operations to compile against
        engine._llm_router.route.assert_not_called()
        # Plan returned unchanged
        assert result.policies == plan.policies

    async def test_compile_preserves_metadata(self):
        """Enforcement, hold_config, and other metadata preserved after compilation."""
        plan = _make_plan([
            {
                "name": "Refund approval",
                "trigger": "refund amount exceeds agent authority",
                "enforcement": "hold",
                "hold_config": {"approver_role": "supervisor", "timeout": "30m"},
            }
        ])
        llm_resp = _make_llm_response([
            {
                "policy_name": "Refund approval",
                "triggers": [{"action": "pages.update", "condition": "input.amount > 5000"}],
            }
        ])

        result = await _compile(plan, llm_resp)

        policy = result.policies[0]
        assert policy["enforcement"] == "hold"
        assert policy["hold_config"]["approver_role"] == "supervisor"
        assert policy["hold_config"]["timeout"] == "30m"
        assert policy["_compiled_from_nl"] == "refund amount exceeds agent authority"

    async def test_compile_seed_passed(self):
        """Seed is forwarded to LLM router for reproducibility."""
        plan = _make_plan([
            {
                "name": "NL policy",
                "trigger": "some trigger",
                "enforcement": "log",
            }
        ])
        plan = plan.model_copy(update={"seed": 12345})

        llm_resp = _make_llm_response([
            {
                "policy_name": "NL policy",
                "triggers": [{"action": "pages.update"}],
            }
        ])

        engine = WorldCompilerEngine()
        engine._llm_router = AsyncMock()
        engine._llm_router.route = AsyncMock(return_value=llm_resp)

        await engine._compile_policy_triggers(plan)

        # Verify the LLM request included the seed
        call_args = engine._llm_router.route.call_args
        request = call_args[0][0]
        assert request.seed == 12345
