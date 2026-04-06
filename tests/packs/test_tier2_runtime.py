"""Tests for Tier 2 runtime -- profiled LLM responses.

Covers:
- Tier2Generator with mock LLM router
- Operation lookup from profile
- Response validation against schema
- Proposal construction with FidelityMetadata tier=2
- Responder engine Tier 2 fallback (Tier 1 -> Tier 2 -> error)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from volnix.core.context import ActionContext
from volnix.core.types import (
    ActorId,
    EntityId,
    FidelitySource,
    FidelityTier,
    ServiceId,
    StepVerdict,
)
from volnix.engines.responder.tier2 import Tier2Generator
from volnix.llm.types import LLMResponse
from volnix.packs.profile_schema import (
    ProfileEntity,
    ProfileErrorMode,
    ProfileExample,
    ProfileOperation,
    ProfileStateMachine,
    ServiceProfileData,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_profile() -> ServiceProfileData:
    """Create a test profile with operations, entities, state machines, etc."""
    return ServiceProfileData(
        profile_name="testpro",
        service_name="testpro",
        category="testing",
        version="1.0.0",
        fidelity_source="curated_profile",
        operations=[
            ProfileOperation(
                name="testpro_create_item",
                service="testpro",
                description="Create a new item",
                http_method="POST",
                http_path="/api/items",
                parameters={
                    "name": {"type": "string"},
                    "color": {"type": "string"},
                },
                required_params=["name"],
                response_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "color": {"type": "string"},
                        "status": {"type": "string"},
                    },
                    "required": ["id", "name"],
                },
                creates_entity="item",
            ),
            ProfileOperation(
                name="testpro_get_item",
                service="testpro",
                description="Get an item by ID",
                http_method="GET",
                http_path="/api/items/{id}",
                parameters={"id": {"type": "string"}},
                required_params=["id"],
                response_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                    },
                },
                is_read_only=True,
            ),
            ProfileOperation(
                name="testpro_update_item",
                service="testpro",
                description="Update an existing item",
                http_method="PUT",
                http_path="/api/items/{id}",
                parameters={
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                },
                required_params=["id"],
                response_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                    },
                },
                mutates_entity="item",
            ),
        ],
        entities=[
            ProfileEntity(
                name="item",
                identity_field="id",
                fields={
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "color": {"type": "string"},
                    "status": {"type": "string"},
                },
                required=["id", "name"],
            ),
        ],
        state_machines=[
            ProfileStateMachine(
                entity_type="item",
                field="status",
                transitions={"new": ["active"], "active": ["archived"]},
            ),
        ],
        error_modes=[
            ProfileErrorMode(
                code="NOT_FOUND",
                when="Item does not exist",
                http_status=404,
            ),
        ],
        behavioral_notes=["Items always have a color", "IDs are UUIDs"],
        examples=[
            ProfileExample(
                operation="testpro_create_item",
                request={"name": "Widget", "color": "blue"},
                response={"id": "item-1", "name": "Widget", "color": "blue", "status": "new"},
            ),
        ],
        responder_prompt="You are simulating the TestPro API. Always return valid JSON.",
    )


def _make_ctx(action: str = "testpro_create_item", **kwargs) -> ActionContext:
    """Create an ActionContext for testing."""
    now = datetime.now(UTC)
    defaults = {
        "request_id": "req-test-001",
        "actor_id": ActorId("actor-test"),
        "service_id": ServiceId("testpro"),
        "action": action,
        "input_data": {"name": "Widget", "color": "blue"},
        "world_time": now,
        "wall_time": now,
        "tick": 1,
    }
    defaults.update(kwargs)
    return ActionContext(**defaults)


def _make_mock_router(response_body: dict | None = None) -> AsyncMock:
    """Create a mock LLM router that returns a canned response."""
    if response_body is None:
        response_body = {
            "id": "item-42",
            "name": "Widget",
            "color": "blue",
            "status": "new",
        }
    mock_router = AsyncMock()
    mock_router.route = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(response_body),
            provider="mock",
            model="mock-model",
            latency_ms=10.0,
        )
    )
    return mock_router


# ---------------------------------------------------------------------------
# Tier2Generator tests
# ---------------------------------------------------------------------------


async def test_tier2_generator_with_mock_llm():
    """Generate a response from a profile using mock LLM."""
    router = _make_mock_router()
    gen = Tier2Generator(llm_router=router, seed=42)
    profile = _make_profile()
    ctx = _make_ctx()

    proposal = await gen.generate(ctx, profile)

    # Verify response body
    assert proposal.response_body["id"] == "item-42"
    assert proposal.response_body["name"] == "Widget"
    assert proposal.response_body["color"] == "blue"

    # Verify fidelity metadata
    assert proposal.fidelity is not None
    assert proposal.fidelity.tier == FidelityTier.PROFILED
    assert proposal.fidelity.tier == 2
    assert proposal.fidelity.source == "testpro"
    assert proposal.fidelity.fidelity_source == FidelitySource.CURATED_PROFILE
    assert proposal.fidelity.deterministic is False
    assert proposal.fidelity.replay_stable is False
    assert proposal.fidelity.benchmark_grade is False

    # Verify LLM was called via router
    router.route.assert_awaited_once()
    call_args = router.route.call_args
    assert call_args.kwargs["engine_name"] == "responder"
    assert call_args.kwargs["use_case"] == "tier2"

    # Verify fidelity warning
    assert proposal.fidelity_warning is not None
    assert "Tier 2 profile: testpro" in proposal.fidelity_warning


async def test_tier2_find_operation():
    """Correct operation lookup by action name."""
    gen = Tier2Generator(llm_router=AsyncMock(), seed=42)
    profile = _make_profile()

    # Found
    op = gen._find_operation(profile, "testpro_create_item")
    assert op is not None
    assert op.name == "testpro_create_item"
    assert op.creates_entity == "item"

    # Found (different operation)
    op2 = gen._find_operation(profile, "testpro_get_item")
    assert op2 is not None
    assert op2.is_read_only is True

    # Not found
    op3 = gen._find_operation(profile, "nonexistent_operation")
    assert op3 is None


async def test_tier2_operation_not_found_returns_error_proposal():
    """When action does not match any profile operation, return error proposal."""
    router = _make_mock_router()
    gen = Tier2Generator(llm_router=router, seed=42)
    profile = _make_profile()
    ctx = _make_ctx(action="nonexistent_action")

    proposal = await gen.generate(ctx, profile)

    assert "error" in proposal.response_body
    assert "nonexistent_action" in proposal.response_body["error"]
    assert proposal.fidelity is not None
    assert proposal.fidelity.tier == FidelityTier.PROFILED
    assert proposal.fidelity.source == "tier2_error"

    # LLM should NOT have been called
    router.route.assert_not_awaited()


async def test_tier2_validation_catches_bad_response_create():
    """Schema validation on create operations retries, then returns error if still invalid."""
    # Return a response missing required "id" field
    bad_response = {"name": "Widget", "color": "blue"}
    router = _make_mock_router(response_body=bad_response)
    gen = Tier2Generator(llm_router=router, seed=42)
    profile = _make_profile()
    ctx = _make_ctx()  # testpro_create_item — creates entity

    proposal = await gen.generate(ctx, profile)

    # Create operation with validation failure should return error after retry
    assert "error" in proposal.response_body
    assert "Validation failed" in proposal.response_body["error"]
    # No state deltas should be proposed for invalid response
    assert not proposal.proposed_state_deltas
    # LLM was called twice (initial + retry)
    assert router.route.await_count == 2


async def test_tier2_validation_warnings_read_only():
    """Schema validation on read-only operations logs warnings but returns data."""
    # Return a response that fails to parse as JSON (triggers _parse_error)
    gen = Tier2Generator(llm_router=AsyncMock(), seed=42)
    profile = _make_profile()

    # Manually build profile with a read-only op that has required fields
    read_op = ProfileOperation(
        name="testpro_get_strict",
        service="testpro",
        description="Get an item (strict schema)",
        http_method="GET",
        http_path="/api/items/{id}",
        parameters={"id": {"type": "string"}},
        required_params=["id"],
        response_schema={
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["id", "name"],
        },
        is_read_only=True,
    )
    profile_with_strict = ServiceProfileData(
        profile_name=profile.profile_name,
        service_name=profile.service_name,
        category=profile.category,
        version=profile.version,
        fidelity_source=profile.fidelity_source,
        operations=[*profile.operations, read_op],
        entities=profile.entities,
        state_machines=profile.state_machines,
        error_modes=profile.error_modes,
        behavioral_notes=profile.behavioral_notes,
        examples=profile.examples,
        responder_prompt=profile.responder_prompt,
    )

    # Response missing required "id" field
    partial_response = {"name": "Widget"}
    router = _make_mock_router(response_body=partial_response)
    gen = Tier2Generator(llm_router=router, seed=42)
    ctx = _make_ctx(action="testpro_get_strict", input_data={"id": "item-1"})

    proposal = await gen.generate(ctx, profile_with_strict)

    # Read-only: response returned despite validation warnings
    assert proposal.response_body["name"] == "Widget"
    # Fidelity warning should mention validation
    assert proposal.fidelity_warning is not None
    assert "Validation warnings" in proposal.fidelity_warning


async def test_tier2_validation_passes_good_response():
    """Schema validation passes for a well-formed response."""
    good_response = {"id": "item-1", "name": "Widget", "color": "blue", "status": "new"}
    router = _make_mock_router(response_body=good_response)
    gen = Tier2Generator(llm_router=router, seed=42)
    profile = _make_profile()
    ctx = _make_ctx()

    proposal = await gen.generate(ctx, profile)

    # No validation warnings
    assert proposal.fidelity_warning is not None
    assert "Validation warnings" not in proposal.fidelity_warning


async def test_tier2_builds_proposal_with_fidelity():
    """ResponseProposal includes correct FidelityMetadata for tier 2."""
    router = _make_mock_router()
    gen = Tier2Generator(llm_router=router, seed=42)
    profile = _make_profile()
    ctx = _make_ctx()

    proposal = await gen.generate(ctx, profile)

    assert proposal.fidelity is not None
    assert proposal.fidelity.tier == FidelityTier.PROFILED
    assert proposal.fidelity.tier == 2
    assert proposal.fidelity.source == "testpro"
    assert proposal.fidelity.fidelity_source == FidelitySource.CURATED_PROFILE


async def test_tier2_creates_entity_state_delta():
    """Creates a StateDelta when operation creates an entity."""
    response_body = {"id": "item-99", "name": "Gadget", "color": "red", "status": "new"}
    router = _make_mock_router(response_body=response_body)
    gen = Tier2Generator(llm_router=router, seed=42)
    profile = _make_profile()
    ctx = _make_ctx(action="testpro_create_item")

    proposal = await gen.generate(ctx, profile)

    assert len(proposal.proposed_state_deltas) == 1
    delta = proposal.proposed_state_deltas[0]
    assert delta.entity_type == "item"
    assert delta.entity_id == EntityId("item-99")
    assert delta.operation == "create"
    assert delta.fields["name"] == "Gadget"


async def test_tier2_mutates_entity_state_delta():
    """Creates a StateDelta when operation mutates an entity."""
    response_body = {"id": "item-1", "name": "Updated Widget"}
    router = _make_mock_router(response_body=response_body)
    gen = Tier2Generator(llm_router=router, seed=42)
    profile = _make_profile()
    ctx = _make_ctx(
        action="testpro_update_item",
        input_data={"id": "item-1", "name": "Updated Widget"},
    )

    proposal = await gen.generate(ctx, profile)

    assert len(proposal.proposed_state_deltas) == 1
    delta = proposal.proposed_state_deltas[0]
    assert delta.entity_type == "item"
    assert delta.entity_id == EntityId("item-1")
    assert delta.operation == "update"


async def test_tier2_read_only_no_state_delta():
    """Read-only operations produce no state deltas."""
    response_body = {"id": "item-1", "name": "Widget"}
    router = _make_mock_router(response_body=response_body)
    gen = Tier2Generator(llm_router=router, seed=42)
    profile = _make_profile()
    ctx = _make_ctx(action="testpro_get_item", input_data={"id": "item-1"})

    proposal = await gen.generate(ctx, profile)

    assert len(proposal.proposed_state_deltas) == 0


async def test_tier2_system_prompt_includes_behavioral_notes():
    """System prompt includes behavioral notes from profile."""
    gen = Tier2Generator(llm_router=AsyncMock(), seed=42)
    profile = _make_profile()
    op = profile.operations[0]

    prompt = gen._build_system_prompt(profile, op)

    assert "Items always have a color" in prompt
    assert "IDs are UUIDs" in prompt
    assert "Behavioral Rules" in prompt


async def test_tier2_system_prompt_includes_error_modes():
    """System prompt includes error modes from profile."""
    gen = Tier2Generator(llm_router=AsyncMock(), seed=42)
    profile = _make_profile()
    op = profile.operations[0]

    prompt = gen._build_system_prompt(profile, op)

    assert "NOT_FOUND" in prompt
    assert "Item does not exist" in prompt
    assert "Error Modes" in prompt


async def test_tier2_user_prompt_includes_examples():
    """User prompt includes matching few-shot examples."""
    gen = Tier2Generator(llm_router=AsyncMock(), seed=42)
    profile = _make_profile()
    op = profile.operations[0]  # testpro_create_item
    ctx = _make_ctx()

    prompt = gen._build_user_prompt(ctx, profile, op, {})

    assert "Examples" in prompt
    assert "Widget" in prompt
    assert "blue" in prompt


async def test_tier2_user_prompt_includes_state():
    """User prompt includes current world state when provided."""
    gen = Tier2Generator(llm_router=AsyncMock(), seed=42)
    profile = _make_profile()
    op = profile.operations[0]
    ctx = _make_ctx()

    current_state = {
        "items": [
            {"id": "item-1", "name": "Existing Widget", "color": "green"},
        ],
    }

    prompt = gen._build_user_prompt(ctx, profile, op, current_state)

    assert "Current World State" in prompt
    assert "Existing Widget" in prompt


async def test_tier2_parse_response_structured_output():
    """Parse response uses structured_output when available."""
    gen = Tier2Generator(llm_router=AsyncMock(), seed=42)

    response = LLMResponse(
        content="ignored",
        structured_output={"id": "from-structured"},
        provider="mock",
        model="mock-model",
    )

    result = gen._parse_response(response)
    assert result["id"] == "from-structured"


async def test_tier2_parse_response_json_content():
    """Parse response parses JSON from content string."""
    gen = Tier2Generator(llm_router=AsyncMock(), seed=42)

    response = LLMResponse(
        content='{"id": "from-content"}',
        provider="mock",
        model="mock-model",
    )

    result = gen._parse_response(response)
    assert result["id"] == "from-content"


async def test_tier2_parse_response_strips_markdown():
    """Parse response strips markdown code block wrappers."""
    gen = Tier2Generator(llm_router=AsyncMock(), seed=42)

    response = LLMResponse(
        content='```json\n{"id": "from-markdown"}\n```',
        provider="mock",
        model="mock-model",
    )

    result = gen._parse_response(response)
    assert result["id"] == "from-markdown"


async def test_tier2_parse_response_fallback():
    """Parse response returns error marker for unparseable content."""
    gen = Tier2Generator(llm_router=AsyncMock(), seed=42)

    response = LLMResponse(
        content="This is not JSON at all",
        provider="mock",
        model="mock-model",
    )

    result = gen._parse_response(response)
    assert result.get("_parse_error") is True


async def test_tier2_bootstrapped_fidelity_source():
    """Bootstrapped profiles set correct FidelitySource."""
    response_body = {"id": "item-1", "name": "Test"}
    router = _make_mock_router(response_body=response_body)
    gen = Tier2Generator(llm_router=router, seed=42)
    profile = ServiceProfileData(
        profile_name="bootstrapped_svc",
        service_name="bootstrapped_svc",
        category="testing",
        fidelity_source="bootstrapped",
        operations=[
            ProfileOperation(
                name="bootstrapped_svc_get",
                service="bootstrapped_svc",
                description="Get",
                response_schema={"type": "object", "properties": {"id": {"type": "string"}}},
                is_read_only=True,
            ),
        ],
    )
    ctx = _make_ctx(action="bootstrapped_svc_get", service_id=ServiceId("bootstrapped_svc"))

    proposal = await gen.generate(ctx, profile)

    assert proposal.fidelity is not None
    assert proposal.fidelity.fidelity_source == FidelitySource.BOOTSTRAPPED


async def test_tier2_with_current_state():
    """Generate passes current state to the LLM prompt."""
    response_body = {"id": "item-1", "name": "Widget"}
    router = _make_mock_router(response_body=response_body)
    gen = Tier2Generator(llm_router=router, seed=42)
    profile = _make_profile()
    ctx = _make_ctx(action="testpro_get_item", input_data={"id": "item-1"})

    current_state = {
        "items": [{"id": "item-1", "name": "Widget", "color": "blue"}],
    }

    await gen.generate(ctx, profile, current_state)

    # Verify the LLM was called with state in the prompt
    call_args = router.route.call_args
    request = call_args.args[0]
    assert "Widget" in request.user_content
    assert "Current World State" in request.user_content


# ---------------------------------------------------------------------------
# Responder engine Tier 2 fallback
# ---------------------------------------------------------------------------


async def test_responder_falls_back_to_tier2():
    """When Tier 1 has no pack, responder falls back to Tier 2 profile."""
    from volnix.engines.responder.engine import WorldResponderEngine

    engine = WorldResponderEngine()
    await engine.initialize(
        config={
            "verified_packs_dir": "/tmp/nonexistent_packs_dir",
            "_llm_router": _make_mock_router(),
        },
        bus=AsyncMock(),
    )

    # Register a profile
    profile = _make_profile()
    engine._profile_registry.register(profile)

    # Create context for a Tier 2 action (no Tier 1 pack)
    ctx = _make_ctx(action="testpro_create_item")

    result = await engine.execute(ctx)

    assert result.verdict == StepVerdict.ALLOW
    assert result.metadata.get("fidelity_tier") == 2
    assert result.metadata.get("profile") == "testpro"
    assert ctx.response_proposal is not None
    assert ctx.response_proposal.fidelity is not None
    assert ctx.response_proposal.fidelity.tier == FidelityTier.PROFILED


async def test_responder_returns_error_when_no_handler():
    """When neither Tier 1 nor Tier 2 handles the action, return error."""
    from volnix.engines.responder.engine import WorldResponderEngine

    engine = WorldResponderEngine()
    await engine.initialize(
        config={
            "verified_packs_dir": "/tmp/nonexistent_packs_dir",
            "_llm_router": _make_mock_router(),
        },
        bus=AsyncMock(),
    )

    ctx = _make_ctx(action="completely_unknown_action")

    result = await engine.execute(ctx)

    assert result.verdict == StepVerdict.ERROR
    assert "No pack or profile found" in result.message


async def test_responder_profile_registry_accessible():
    """Profile registry is accessible via engine property."""
    from volnix.engines.responder.engine import WorldResponderEngine

    engine = WorldResponderEngine()
    await engine.initialize(
        config={
            "verified_packs_dir": "/tmp/nonexistent_packs_dir",
        },
        bus=AsyncMock(),
    )

    assert engine.profile_registry is not None
    assert engine.profile_loader is not None
