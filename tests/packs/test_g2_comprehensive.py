"""Comprehensive tests for the G2 Tier 2 profile system.

Covers:
- Full bootstrap pipeline (infer -> save -> load -> runtime)
- Empty profile rejection
- Missing identity field handling
- Validation failure blocking
- Infer save/reload roundtrip
- Duplicate action names across profiles
- Context Hub + OpenAPI wiring
- Profile YAML structure enforcement (auto-catch harness)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml

from volnix.core.context import ActionContext
from volnix.core.types import (
    ActorId,
    FidelityTier,
    ServiceId,
)
from volnix.engines.responder.tier2 import Tier2Generator
from volnix.llm.types import LLMResponse
from volnix.packs.profile_infer import ProfileInferrer
from volnix.packs.profile_loader import ProfileLoader
from volnix.packs.profile_registry import ProfileRegistry
from volnix.packs.profile_schema import (
    ProfileEntity,
    ProfileOperation,
    ServiceProfileData,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROFILES_DIR = Path(__file__).resolve().parents[2] / "volnix" / "packs" / "profiles"


def _make_yaml_response(data: dict) -> str:
    """Convert a dict to YAML string as LLM would return."""
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


def _make_llm_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        provider="mock",
        model="mock-model",
        latency_ms=50.0,
    )


def _make_mock_router_yaml(response_content: str) -> AsyncMock:
    """Create a mock LLM router that returns canned YAML content."""
    router = AsyncMock()
    router.route = AsyncMock(return_value=_make_llm_response(response_content))
    return router


def _make_mock_router_json(response_body: dict | None = None) -> AsyncMock:
    """Create a mock LLM router that returns canned JSON content."""
    if response_body is None:
        response_body = {"id": "item-42", "name": "Widget", "status": "new"}
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


def _minimal_profile_yaml(service_name: str = "acme") -> dict:
    """Return a minimal valid profile structure for LLM inference."""
    return {
        "profile_name": service_name,
        "service_name": service_name,
        "category": "testing",
        "operations": [
            {
                "name": f"{service_name}_create_widget",
                "service": service_name,
                "description": "Create a widget",
                "http_method": "POST",
                "http_path": "/api/widgets",
                "parameters": {"name": {"type": "string"}},
                "required_params": ["name"],
                "response_schema": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                    },
                },
                "creates_entity": "widget",
            },
        ],
        "entities": [
            {
                "name": "widget",
                "identity_field": "id",
                "fields": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                },
                "required": ["id"],
            },
        ],
        "state_machines": [
            {
                "entity_type": "widget",
                "field": "status",
                "transitions": {"new": ["active"], "active": ["archived"]},
            },
        ],
        "error_modes": [
            {"code": "NOT_FOUND", "when": "Widget not found", "http_status": 404},
        ],
        "behavioral_notes": ["Widgets are always round"],
        "responder_prompt": f"You are simulating the {service_name} API.",
    }


def _make_profile(
    service_name: str = "testpro",
    operations: list[ProfileOperation] | None = None,
    entities: list[ProfileEntity] | None = None,
) -> ServiceProfileData:
    """Create a test profile."""
    if operations is None:
        operations = [
            ProfileOperation(
                name=f"{service_name}_create_item",
                service=service_name,
                description="Create a new item",
                http_method="POST",
                http_path="/api/items",
                parameters={
                    "name": {"type": "string"},
                },
                required_params=["name"],
                response_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "status": {"type": "string"},
                    },
                    "required": ["id", "status"],
                },
                creates_entity="item",
            ),
        ]
    if entities is None:
        entities = [
            ProfileEntity(
                name="item",
                identity_field="uuid",
                fields={
                    "uuid": {"type": "string"},
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "status": {"type": "string"},
                },
                required=["uuid", "name"],
            ),
        ]
    return ServiceProfileData(
        profile_name=service_name,
        service_name=service_name,
        category="testing",
        fidelity_source="curated_profile",
        operations=operations,
        entities=entities,
        responder_prompt=f"You are simulating the {service_name} API.",
    )


def _make_ctx(action: str = "testpro_create_item", **kwargs) -> ActionContext:
    now = datetime.now(UTC)
    defaults = {
        "request_id": "req-test-001",
        "actor_id": ActorId("actor-test"),
        "service_id": ServiceId("testpro"),
        "action": action,
        "input_data": {"name": "Widget"},
        "world_time": now,
        "wall_time": now,
        "tick": 1,
    }
    defaults.update(kwargs)
    return ActionContext(**defaults)


# ---------------------------------------------------------------------------
# Test 13: Full bootstrap pipeline
# ---------------------------------------------------------------------------


async def test_full_bootstrap_infer_save_load_runtime(tmp_path: Path):
    """Unknown service -> infer -> save -> load -> Tier 2 runtime."""
    service_name = "test_bootstrap_svc"
    profile_data = _minimal_profile_yaml(service_name)
    yaml_content = _make_yaml_response(profile_data)

    # 1. Create ProfileInferrer with mock LLM
    infer_router = _make_mock_router_yaml(yaml_content)
    inferrer = ProfileInferrer(llm_router=infer_router)

    # 2. Infer the profile
    inferred = await inferrer.infer(service_name)
    assert isinstance(inferred, ServiceProfileData)
    assert inferred.service_name == service_name
    assert inferred.fidelity_source == "bootstrapped"
    assert len(inferred.operations) >= 1

    # 3. Save to tmp_path
    loader = ProfileLoader(tmp_path)
    saved_path = loader.save(inferred)
    assert saved_path.exists()

    # 4. Load back via ProfileLoader
    loaded = loader.load(service_name)
    assert loaded is not None
    assert loaded.service_name == service_name
    assert loaded.fidelity_source == "bootstrapped"

    # 5. Register in ProfileRegistry
    registry = ProfileRegistry()
    registry.register(loaded)
    assert registry.has_profile(service_name)

    op_name = loaded.operations[0].name
    found = registry.get_profile_for_action(op_name)
    assert found is not None
    assert found.service_name == service_name

    # 6. Create Tier2Generator with mock LLM
    response_body = {"id": "wgt-1", "name": "Widget"}
    runtime_router = _make_mock_router_json(response_body)
    gen = Tier2Generator(llm_router=runtime_router, seed=42)

    # 7. Generate response using loaded profile
    ctx = _make_ctx(
        action=op_name,
        service_id=ServiceId(service_name),
        input_data={"name": "Widget"},
    )
    proposal = await gen.generate(ctx, loaded)

    # 8. Verify response has correct structure
    assert proposal.response_body["id"] == "wgt-1"
    assert proposal.fidelity is not None
    assert proposal.fidelity.tier == FidelityTier.PROFILED


# ---------------------------------------------------------------------------
# Test 14: Empty profile rejection
# ---------------------------------------------------------------------------


async def test_infer_empty_operations_rejected():
    """Profile with 0 operations should be rejected."""
    # LLM returns profile with operations: []
    profile_data = {
        "profile_name": "empty_svc",
        "service_name": "empty_svc",
        "category": "testing",
        "operations": [],
        "entities": [],
        "responder_prompt": "You are simulating the empty_svc API.",
    }
    yaml_content = _make_yaml_response(profile_data)
    router = _make_mock_router_yaml(yaml_content)

    inferrer = ProfileInferrer(llm_router=router)

    with pytest.raises(ValueError, match="Could not generate valid profile"):
        await inferrer.infer("empty_svc")


# ---------------------------------------------------------------------------
# Test 15: Missing identity field in response
# ---------------------------------------------------------------------------


async def test_tier2_missing_identity_field_no_delta():
    """When response lacks identity field, StateDelta uses fallback 'id' field."""
    # Profile expects identity_field="uuid"
    profile = _make_profile(
        service_name="testpro",
        operations=[
            ProfileOperation(
                name="testpro_create_item",
                service="testpro",
                description="Create a new item",
                http_method="POST",
                http_path="/api/items",
                parameters={"name": {"type": "string"}},
                response_schema={
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                    },
                },
                creates_entity="item",
            ),
        ],
        entities=[
            ProfileEntity(
                name="item",
                identity_field="uuid",
                fields={
                    "uuid": {"type": "string"},
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                },
                required=["uuid"],
            ),
        ],
    )

    # LLM response has {"id": "123"} but no "uuid"
    response_body = {"id": "123", "name": "Thing"}
    router = _make_mock_router_json(response_body)
    gen = Tier2Generator(llm_router=router, seed=42)

    ctx = _make_ctx(action="testpro_create_item")
    proposal = await gen.generate(ctx, profile)

    # Identity field "uuid" is missing from response — no StateDelta created
    assert len(proposal.proposed_state_deltas) == 0


# ---------------------------------------------------------------------------
# Test 16: Validation failure blocks state commit
# ---------------------------------------------------------------------------


async def test_tier2_validation_failure_returns_error_proposal():
    """Schema validation failure on create/mutate op returns error after retry."""
    # Profile has response_schema requiring "id" and "status"
    profile = _make_profile()

    # LLM returns {"name": "Widget"} (missing both required fields)
    bad_response = {"name": "Widget"}
    router = _make_mock_router_json(bad_response)
    gen = Tier2Generator(llm_router=router, seed=42)

    ctx = _make_ctx(action="testpro_create_item")
    proposal = await gen.generate(ctx, profile)

    # Create operation with validation failure: retries then returns error
    assert "error" in proposal.response_body
    assert "Validation failed" in proposal.response_body["error"]
    # No state deltas should be proposed for invalid response
    assert not proposal.proposed_state_deltas


# ---------------------------------------------------------------------------
# Test 17: Infer save/reload roundtrip
# ---------------------------------------------------------------------------


async def test_infer_save_reload_roundtrip(tmp_path: Path):
    """Inferred profile saved to disk loads back identically."""
    service_name = "roundtrip_svc"
    profile_data = _minimal_profile_yaml(service_name)
    yaml_content = _make_yaml_response(profile_data)

    router = _make_mock_router_yaml(yaml_content)
    inferrer = ProfileInferrer(llm_router=router)

    # Infer a profile
    inferred = await inferrer.infer(service_name)

    # Save to tmp_path
    loader = ProfileLoader(tmp_path)
    loader.save(inferred)

    # Load from tmp_path
    loaded = loader.load(service_name)
    assert loaded is not None

    # Compare all fields
    assert loaded.profile_name == inferred.profile_name
    assert loaded.service_name == inferred.service_name
    assert loaded.category == inferred.category
    assert loaded.fidelity_source == inferred.fidelity_source
    assert loaded.version == inferred.version
    assert loaded.responder_prompt == inferred.responder_prompt
    assert loaded.confidence == inferred.confidence
    assert loaded.auth_pattern == inferred.auth_pattern
    assert loaded.base_url == inferred.base_url

    # Compare operations
    assert len(loaded.operations) == len(inferred.operations)
    for loaded_op, inferred_op in zip(loaded.operations, inferred.operations):
        assert loaded_op.name == inferred_op.name
        assert loaded_op.service == inferred_op.service
        assert loaded_op.http_method == inferred_op.http_method
        assert loaded_op.http_path == inferred_op.http_path
        assert loaded_op.is_read_only == inferred_op.is_read_only

    # Compare entities
    assert len(loaded.entities) == len(inferred.entities)
    for loaded_ent, inferred_ent in zip(loaded.entities, inferred.entities):
        assert loaded_ent.name == inferred_ent.name
        assert loaded_ent.identity_field == inferred_ent.identity_field

    # Compare state machines
    assert len(loaded.state_machines) == len(inferred.state_machines)

    # Compare source chain
    assert loaded.source_chain == inferred.source_chain


# ---------------------------------------------------------------------------
# Test 18: Duplicate action names across profiles
# ---------------------------------------------------------------------------


def test_profile_registry_first_registration_wins():
    """First profile to register an action name wins; second is skipped."""
    registry = ProfileRegistry()

    # Profile A with op "shared_op"
    profile_a = ServiceProfileData(
        profile_name="svc_a",
        service_name="svc_a",
        category="testing",
        operations=[
            ProfileOperation(
                name="shared_op",
                service="svc_a",
                description="Shared operation from A",
            ),
            ProfileOperation(
                name="unique_a",
                service="svc_a",
                description="Unique to A",
            ),
        ],
        responder_prompt="Service A.",
    )

    # Profile B with op "shared_op"
    profile_b = ServiceProfileData(
        profile_name="svc_b",
        service_name="svc_b",
        category="testing",
        operations=[
            ProfileOperation(
                name="shared_op",
                service="svc_b",
                description="Shared operation from B",
            ),
            ProfileOperation(
                name="unique_b",
                service="svc_b",
                description="Unique to B",
            ),
        ],
        responder_prompt="Service B.",
    )

    registry.register(profile_a)
    registry.register(profile_b)

    # get_profile_for_action("shared_op") returns profile_a (first registration wins)
    result = registry.get_profile_for_action("shared_op")
    assert result is not None
    assert result.service_name == "svc_a"

    # unique actions still resolve correctly
    result_a = registry.get_profile_for_action("unique_a")
    assert result_a is not None
    assert result_a.service_name == "svc_a"

    result_b = registry.get_profile_for_action("unique_b")
    assert result_b is not None
    assert result_b.service_name == "svc_b"


# ---------------------------------------------------------------------------
# Test 19: Context Hub + OpenAPI wiring
# ---------------------------------------------------------------------------


async def test_infer_with_context_hub_and_openapi():
    """Both Context Hub and OpenAPI sources are gathered and passed to LLM."""
    service_name = "multi_source_svc"
    profile_data = _minimal_profile_yaml(service_name)
    yaml_content = _make_yaml_response(profile_data)
    router = _make_mock_router_yaml(yaml_content)

    # Mock context_hub.fetch() returns docs
    context_hub = AsyncMock()
    context_hub.supports = AsyncMock(return_value=True)
    context_hub.fetch = AsyncMock(
        return_value={
            "source": "context_hub",
            "service": service_name,
            "raw_content": "Multi Source API documentation: widgets, gadgets...",
        }
    )

    # Mock openapi_provider.fetch() returns operations
    openapi_provider = AsyncMock()
    openapi_provider.supports = AsyncMock(return_value=True)
    openapi_provider.fetch = AsyncMock(
        return_value={
            "source": "openapi",
            "service": service_name,
            "operations": [
                {
                    "name": "createWidget",
                    "http_method": "POST",
                    "http_path": "/api/widgets",
                    "description": "Create a widget",
                },
                {
                    "name": "listWidgets",
                    "http_method": "GET",
                    "http_path": "/api/widgets",
                    "description": "List all widgets",
                },
            ],
        }
    )

    inferrer = ProfileInferrer(
        llm_router=router,
        context_hub=context_hub,
        openapi_provider=openapi_provider,
    )

    result = await inferrer.infer(service_name)

    # Verify both sources were queried
    context_hub.supports.assert_awaited_once_with(service_name)
    context_hub.fetch.assert_awaited_once_with(service_name)
    openapi_provider.supports.assert_awaited_once_with(service_name)
    openapi_provider.fetch.assert_awaited_once_with(service_name)

    # Verify LLM prompt includes both Context Hub docs and OpenAPI operations
    call_args = router.route.call_args
    request = call_args.args[0]
    assert "Multi Source API documentation" in request.user_content
    assert "createWidget" in request.user_content
    assert "listWidgets" in request.user_content

    # Verify confidence > 0.3 (not LLM-only) -- Context Hub gives 0.7
    assert result.confidence > 0.3

    # Source chain includes both
    assert "context_hub" in result.source_chain
    assert "openapi" in result.source_chain


# ---------------------------------------------------------------------------
# Test 20: Profile structure enforcement (auto-catch harness)
# ---------------------------------------------------------------------------


def test_new_profile_yaml_structure_validated():
    """Any new .profile.yaml MUST have required fields and valid structure.

    This test AUTOMATICALLY catches bad profiles added in future.
    It scans all .profile.yaml files in the profiles directory and
    validates their structure against the expected schema.
    """
    if not _PROFILES_DIR.is_dir():
        pytest.skip(f"Profiles directory not found: {_PROFILES_DIR}")

    profile_files: list[Path] = []

    # Flat files: profiles/*.profile.yaml
    profile_files.extend(sorted(_PROFILES_DIR.glob("*.profile.yaml")))

    # Subdirectory files: profiles/<service>/profile.yaml
    for subdir in sorted(_PROFILES_DIR.iterdir()):
        if subdir.is_dir() and not subdir.name.startswith("_"):
            candidate = subdir / "profile.yaml"
            if candidate.exists():
                profile_files.append(candidate)

    assert len(profile_files) > 0, (
        f"No .profile.yaml files found in {_PROFILES_DIR}. "
        "At least one curated profile should exist."
    )

    errors: list[str] = []

    for path in profile_files:
        rel = path.relative_to(_PROFILES_DIR)
        try:
            with path.open("r") as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            errors.append(f"{rel}: YAML parse error: {exc}")
            continue

        if not isinstance(raw, dict):
            errors.append(f"{rel}: root is not a dict")
            continue

        # --- Required top-level fields ---
        if not raw.get("profile_name"):
            errors.append(f"{rel}: missing or empty 'profile_name'")
        if not raw.get("service_name"):
            errors.append(f"{rel}: missing or empty 'service_name'")

        # --- Operations ---
        ops = raw.get("operations", [])
        if not isinstance(ops, list) or len(ops) == 0:
            errors.append(f"{rel}: 'operations' must be a non-empty list")
        else:
            for i, op in enumerate(ops):
                if not isinstance(op, dict):
                    errors.append(f"{rel}: operations[{i}] is not a dict")
                    continue
                if not op.get("name"):
                    errors.append(f"{rel}: operations[{i}] missing 'name'")
                if not op.get("http_method"):
                    op_name = op.get("name", "?")
                    errors.append(f"{rel}: operations[{i}] ({op_name}) missing 'http_method'")
                if not op.get("response_schema"):
                    errors.append(
                        f"{rel}: operations[{i}] ({op.get('name', '?')}) missing 'response_schema'"
                    )

        # --- Entities ---
        entities = raw.get("entities", [])
        if isinstance(entities, list):
            for i, ent in enumerate(entities):
                if not isinstance(ent, dict):
                    errors.append(f"{rel}: entities[{i}] is not a dict")
                    continue
                if not ent.get("identity_field"):
                    errors.append(
                        f"{rel}: entities[{i}] ({ent.get('name', '?')}) missing 'identity_field'"
                    )
                fields = ent.get("fields", {})
                if not isinstance(fields, dict) or len(fields) == 0:
                    errors.append(
                        f"{rel}: entities[{i}] ({ent.get('name', '?')}) must have at least 1 field"
                    )

        # --- State machines ---
        state_machines = raw.get("state_machines", [])
        if isinstance(state_machines, list):
            for i, sm in enumerate(state_machines):
                if not isinstance(sm, dict):
                    errors.append(f"{rel}: state_machines[{i}] is not a dict")
                    continue
                transitions = sm.get("transitions", {})
                if isinstance(transitions, dict):
                    # Verify all target states are reachable as source states
                    all_states = set(transitions.keys())
                    for source, targets in transitions.items():
                        if isinstance(targets, list):
                            for target in targets:
                                if target not in all_states:
                                    errors.append(
                                        f"{rel}: state_machines[{i}] "
                                        f"transition '{source}' -> '{target}' "
                                        f"references unknown state '{target}'"
                                    )

        # --- Responder prompt ---
        if not raw.get("responder_prompt"):
            errors.append(f"{rel}: missing or empty 'responder_prompt'")

        # --- Validate it loads as ServiceProfileData ---
        try:
            ServiceProfileData(**raw)
        except Exception as exc:
            errors.append(f"{rel}: failed to parse as ServiceProfileData: {exc}")

    if errors:
        error_report = "\n".join(f"  - {e}" for e in errors)
        pytest.fail(f"Profile structure validation found {len(errors)} issue(s):\n{error_report}")
