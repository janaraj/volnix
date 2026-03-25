"""Tests for Tier 2 YAML profile infrastructure.

Covers:
- Pydantic model creation (ProfileOperation, ProfileEntity, ServiceProfileData)
- YAML loading of built-in jira and shopify profiles
- ProfileLoader discover/load/save/roundtrip
- ProfileRegistry register and lookup
- profile_to_surface conversion
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from terrarium.kernel.surface import APIOperation, ServiceSurface
from terrarium.packs.profile_loader import ProfileLoader
from terrarium.packs.profile_registry import ProfileRegistry
from terrarium.packs.profile_schema import (
    ProfileEntity,
    ProfileErrorMode,
    ProfileExample,
    ProfileOperation,
    ProfileStateMachine,
    ServiceProfileData,
)
from terrarium.packs.profile_surface import profile_to_surface

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROFILES_DIR = Path(__file__).resolve().parents[2] / "terrarium" / "packs" / "profiles"


# ---------------------------------------------------------------------------
# ProfileOperation creation
# ---------------------------------------------------------------------------


def test_profile_operation_creation():
    op = ProfileOperation(
        name="test_create_item",
        service="test_service",
        description="Create an item",
        http_method="POST",
        http_path="/api/items",
        parameters={"name": {"type": "string"}},
        required_params=["name"],
        response_schema={"type": "object", "properties": {"id": {"type": "string"}}},
        creates_entity="item",
    )
    assert op.name == "test_create_item"
    assert op.service == "test_service"
    assert op.http_method == "POST"
    assert op.http_path == "/api/items"
    assert op.required_params == ["name"]
    assert op.creates_entity == "item"
    assert op.mutates_entity is None
    assert op.is_read_only is False


def test_profile_operation_defaults():
    op = ProfileOperation(name="op", service="svc")
    assert op.http_method == "POST"
    assert op.http_path == ""
    assert op.parameters == {}
    assert op.required_params == []
    assert op.response_schema == {}
    assert op.is_read_only is False
    assert op.creates_entity is None
    assert op.mutates_entity is None


def test_profile_operation_frozen():
    op = ProfileOperation(name="op", service="svc")
    with pytest.raises(Exception):  # ValidationError for frozen model
        op.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ProfileEntity creation
# ---------------------------------------------------------------------------


def test_profile_entity_creation():
    entity = ProfileEntity(
        name="ticket",
        identity_field="key",
        fields={"key": {"type": "string"}, "title": {"type": "string"}},
        required=["key", "title"],
    )
    assert entity.name == "ticket"
    assert entity.identity_field == "key"
    assert "key" in entity.fields
    assert "title" in entity.fields
    assert entity.required == ["key", "title"]


def test_profile_entity_defaults():
    entity = ProfileEntity(name="thing")
    assert entity.identity_field == "id"
    assert entity.fields == {}
    assert entity.required == []


# ---------------------------------------------------------------------------
# ServiceProfileData creation
# ---------------------------------------------------------------------------


def test_service_profile_data_creation():
    profile = ServiceProfileData(
        profile_name="test_service",
        service_name="test_service",
        category="testing",
        version="2.0.0",
        fidelity_source="bootstrapped",
        operations=[
            ProfileOperation(
                name="test_op",
                service="test_service",
                description="A test operation",
                parameters={"x": {"type": "integer"}},
                required_params=["x"],
                response_schema={"type": "object"},
            ),
        ],
        entities=[
            ProfileEntity(name="widget", identity_field="id", fields={"id": {"type": "string"}}),
        ],
        state_machines=[
            ProfileStateMachine(
                entity_type="widget",
                field="state",
                transitions={"new": ["active"], "active": ["archived"]},
            ),
        ],
        error_modes=[
            ProfileErrorMode(code="NOT_FOUND", when="Widget not found", http_status=404),
        ],
        behavioral_notes=["Widgets are always blue"],
        examples=[
            ProfileExample(
                operation="test_op",
                request={"x": 42},
                response={"result": "ok"},
            ),
        ],
        responder_prompt="You are a test service.",
    )
    assert profile.profile_name == "test_service"
    assert profile.service_name == "test_service"
    assert profile.category == "testing"
    assert profile.version == "2.0.0"
    assert profile.fidelity_source == "bootstrapped"
    assert len(profile.operations) == 1
    assert len(profile.entities) == 1
    assert len(profile.state_machines) == 1
    assert len(profile.error_modes) == 1
    assert len(profile.behavioral_notes) == 1
    assert len(profile.examples) == 1
    assert profile.responder_prompt == "You are a test service."
    assert profile.confidence == 0.9  # default


def test_service_profile_data_frozen():
    profile = ServiceProfileData(profile_name="p", service_name="s", category="c")
    with pytest.raises(Exception):
        profile.service_name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Load Jira profile from YAML
# ---------------------------------------------------------------------------


def test_load_jira_profile_from_yaml():
    jira_path = PROFILES_DIR / "jira.profile.yaml"
    assert jira_path.exists(), f"Jira profile not found at {jira_path}"

    with jira_path.open() as f:
        raw = yaml.safe_load(f)

    profile = ServiceProfileData(**raw)

    assert profile.profile_name == "jira"
    assert profile.service_name == "jira"
    assert profile.category == "work_management"
    assert profile.fidelity_source == "curated_profile"

    # Operations
    op_names = [op.name for op in profile.operations]
    assert "jira_create_issue" in op_names
    assert "jira_get_issue" in op_names
    assert "jira_update_issue" in op_names
    assert "jira_list_issues" in op_names
    assert "jira_add_comment" in op_names
    assert "jira_transition_issue" in op_names
    assert "jira_search" in op_names
    assert len(profile.operations) == 7

    # Entities
    entity_names = [e.name for e in profile.entities]
    assert "issue" in entity_names
    assert "comment" in entity_names
    assert "project" in entity_names

    # State machines
    assert len(profile.state_machines) >= 1
    issue_sm = next(sm for sm in profile.state_machines if sm.entity_type == "issue")
    assert "To Do" in issue_sm.transitions
    assert "In Progress" in issue_sm.transitions["To Do"]

    # Error modes
    error_codes = [em.code for em in profile.error_modes]
    assert "ISSUE_NOT_FOUND" in error_codes
    assert "PERMISSION_DENIED" in error_codes
    assert "INVALID_TRANSITION" in error_codes

    # Behavioral notes
    assert len(profile.behavioral_notes) > 0

    # Responder prompt
    assert "Jira Cloud REST API" in profile.responder_prompt

    # Auth
    assert profile.auth_pattern == "bearer"


# ---------------------------------------------------------------------------
# Load Shopify profile from YAML
# ---------------------------------------------------------------------------


def test_load_shopify_profile_from_yaml():
    shopify_path = PROFILES_DIR / "shopify.profile.yaml"
    assert shopify_path.exists(), f"Shopify profile not found at {shopify_path}"

    with shopify_path.open() as f:
        raw = yaml.safe_load(f)

    profile = ServiceProfileData(**raw)

    assert profile.profile_name == "shopify"
    assert profile.service_name == "shopify"
    assert profile.category == "commerce"
    assert profile.fidelity_source == "curated_profile"

    # Operations
    op_names = [op.name for op in profile.operations]
    assert "shopify_create_product" in op_names
    assert "shopify_get_product" in op_names
    assert "shopify_list_products" in op_names
    assert "shopify_create_order" in op_names
    assert "shopify_get_order" in op_names
    assert "shopify_list_orders" in op_names
    assert "shopify_create_customer" in op_names
    assert "shopify_get_customer" in op_names
    assert len(profile.operations) == 8

    # Entities
    entity_names = [e.name for e in profile.entities]
    assert "product" in entity_names
    assert "order" in entity_names
    assert "customer" in entity_names

    # State machines
    assert len(profile.state_machines) >= 1
    order_sm = next(sm for sm in profile.state_machines if sm.entity_type == "order")
    assert "pending" in order_sm.transitions
    assert "paid" in order_sm.transitions["pending"]

    # Error modes
    error_codes = [em.code for em in profile.error_modes]
    assert "NOT_FOUND" in error_codes
    assert "INVALID_PRODUCT" in error_codes
    assert "INSUFFICIENT_INVENTORY" in error_codes

    # Responder prompt
    assert "Shopify Admin REST API" in profile.responder_prompt

    # Auth
    assert profile.auth_pattern == "api_key"


# ---------------------------------------------------------------------------
# profile_to_surface conversion
# ---------------------------------------------------------------------------


def test_profile_to_surface_conversion():
    """Convert a ServiceProfileData to ServiceSurface and verify structure."""
    profile = ServiceProfileData(
        profile_name="acme",
        service_name="acme",
        category="testing",
        fidelity_source="curated_profile",
        operations=[
            ProfileOperation(
                name="acme_create_widget",
                service="acme",
                description="Create a widget",
                http_method="POST",
                http_path="/api/widgets",
                parameters={"name": {"type": "string"}, "color": {"type": "string"}},
                required_params=["name"],
                response_schema={"type": "object", "properties": {"id": {"type": "string"}}},
                creates_entity="widget",
            ),
            ProfileOperation(
                name="acme_get_widget",
                service="acme",
                description="Get a widget",
                http_method="GET",
                http_path="/api/widgets/{id}",
                parameters={"id": {"type": "string"}},
                required_params=["id"],
                response_schema={"type": "object"},
                is_read_only=True,
            ),
        ],
        entities=[
            ProfileEntity(
                name="widget",
                identity_field="id",
                fields={
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "color": {"type": "string"},
                },
                required=["id", "name"],
            ),
        ],
        state_machines=[
            ProfileStateMachine(
                entity_type="widget",
                field="state",
                transitions={"new": ["active"], "active": ["archived"]},
            ),
        ],
        confidence=0.85,
        auth_pattern="bearer",
        base_url="https://api.acme.com",
    )

    surface = profile_to_surface(profile)

    # Basic surface properties
    assert isinstance(surface, ServiceSurface)
    assert surface.service_name == "acme"
    assert surface.category == "testing"
    assert surface.fidelity_tier == 2
    assert surface.source == "curated_profile"
    assert surface.confidence == 0.85
    assert surface.auth_pattern == "bearer"
    assert surface.base_url == "https://api.acme.com"

    # Operations
    assert len(surface.operations) == 2
    create_op = surface.get_operation("acme_create_widget")
    assert create_op is not None
    assert isinstance(create_op, APIOperation)
    assert create_op.service == "acme"
    assert create_op.http_method == "POST"
    assert create_op.http_path == "/api/widgets"
    assert create_op.required_params == ["name"]
    assert create_op.creates_entity == "widget"
    assert create_op.is_read_only is False

    get_op = surface.get_operation("acme_get_widget")
    assert get_op is not None
    assert get_op.is_read_only is True

    # Entity schemas
    assert "widget" in surface.entity_schemas
    widget_schema = surface.entity_schemas["widget"]
    assert widget_schema["type"] == "object"
    assert widget_schema["x-terrarium-identity"] == "id"
    assert widget_schema["required"] == ["id", "name"]
    assert "id" in widget_schema["properties"]

    # State machines
    assert "widget" in surface.state_machines
    assert surface.state_machines["widget"]["field"] == "state"
    assert surface.state_machines["widget"]["transitions"]["new"] == ["active"]

    # MCP tools should be generatable
    mcp_tools = surface.get_mcp_tools()
    assert len(mcp_tools) == 2
    tool_names = [t["name"] for t in mcp_tools]
    assert "acme_create_widget" in tool_names
    assert "acme_get_widget" in tool_names

    # HTTP routes
    routes = surface.get_http_routes()
    assert len(routes) == 2


def test_profile_to_surface_jira():
    """Load real Jira profile and convert to surface."""
    jira_path = PROFILES_DIR / "jira.profile.yaml"
    with jira_path.open() as f:
        raw = yaml.safe_load(f)
    profile = ServiceProfileData(**raw)
    surface = profile_to_surface(profile)

    assert surface.service_name == "jira"
    assert surface.fidelity_tier == 2
    assert len(surface.operations) == 7
    assert surface.get_operation("jira_create_issue") is not None
    assert "issue" in surface.entity_schemas
    assert "issue" in surface.state_machines


# ---------------------------------------------------------------------------
# ProfileRegistry register and lookup
# ---------------------------------------------------------------------------


def test_profile_registry_register_and_lookup():
    registry = ProfileRegistry()

    profile = ServiceProfileData(
        profile_name="testpro",
        service_name="testpro",
        category="testing",
        operations=[
            ProfileOperation(name="testpro_action_a", service="testpro"),
            ProfileOperation(name="testpro_action_b", service="testpro"),
        ],
    )

    assert not registry.has_profile("testpro")
    registry.register(profile)
    assert registry.has_profile("testpro")

    # Lookup by service name
    found = registry.get_profile("testpro")
    assert found is not None
    assert found.service_name == "testpro"

    # Lookup by action name
    found_by_action = registry.get_profile_for_action("testpro_action_a")
    assert found_by_action is not None
    assert found_by_action.service_name == "testpro"

    found_by_action_b = registry.get_profile_for_action("testpro_action_b")
    assert found_by_action_b is not None
    assert found_by_action_b.service_name == "testpro"

    # Unknown action
    assert registry.get_profile_for_action("nonexistent") is None

    # Unknown service
    assert registry.get_profile("nope") is None

    # List
    all_profiles = registry.list_profiles()
    assert len(all_profiles) == 1
    assert all_profiles[0].service_name == "testpro"


def test_profile_registry_multiple_services():
    registry = ProfileRegistry()

    p1 = ServiceProfileData(
        profile_name="svc_a",
        service_name="svc_a",
        category="cat1",
        operations=[ProfileOperation(name="svc_a_op", service="svc_a")],
    )
    p2 = ServiceProfileData(
        profile_name="svc_b",
        service_name="svc_b",
        category="cat2",
        operations=[ProfileOperation(name="svc_b_op", service="svc_b")],
    )

    registry.register(p1)
    registry.register(p2)

    assert registry.has_profile("svc_a")
    assert registry.has_profile("svc_b")
    assert len(registry.list_profiles()) == 2

    assert registry.get_profile_for_action("svc_a_op").service_name == "svc_a"
    assert registry.get_profile_for_action("svc_b_op").service_name == "svc_b"


# ---------------------------------------------------------------------------
# ProfileLoader discover
# ---------------------------------------------------------------------------


def test_profile_loader_discover():
    loader = ProfileLoader(PROFILES_DIR)
    names = loader.discover()
    assert "jira" in names
    assert "shopify" in names
    assert len(names) >= 2


def test_profile_loader_load():
    loader = ProfileLoader(PROFILES_DIR)
    profile = loader.load("jira")
    assert profile is not None
    assert profile.service_name == "jira"
    assert len(profile.operations) == 7

    shopify = loader.load("shopify")
    assert shopify is not None
    assert shopify.service_name == "shopify"


def test_profile_loader_load_nonexistent():
    loader = ProfileLoader(PROFILES_DIR)
    assert loader.load("nonexistent_service_xyz") is None


def test_profile_loader_list_profiles():
    loader = ProfileLoader(PROFILES_DIR)
    profiles = loader.list_profiles()
    assert len(profiles) >= 2
    names = [p.service_name for p in profiles]
    assert "jira" in names
    assert "shopify" in names


def test_profile_loader_no_dir():
    loader = ProfileLoader(Path("/tmp/nonexistent_terrarium_profiles_xyz"))
    assert loader.discover() == []
    assert loader.load("anything") is None
    assert loader.list_profiles() == []


def test_profile_loader_none_dir():
    loader = ProfileLoader(None)
    assert loader.discover() == []
    assert loader.load("anything") is None
    assert loader.list_profiles() == []


# ---------------------------------------------------------------------------
# ProfileLoader save roundtrip
# ---------------------------------------------------------------------------


def test_profile_loader_save_roundtrip(tmp_path: Path):
    """Save a profile to disk and reload it -- verify roundtrip fidelity."""
    original = ServiceProfileData(
        profile_name="roundtrip",
        service_name="roundtrip",
        category="testing",
        version="1.2.3",
        fidelity_source="bootstrapped",
        operations=[
            ProfileOperation(
                name="roundtrip_create",
                service="roundtrip",
                description="Create a thing",
                http_method="POST",
                http_path="/api/things",
                parameters={"name": {"type": "string"}},
                required_params=["name"],
                response_schema={"type": "object", "properties": {"id": {"type": "string"}}},
                creates_entity="thing",
            ),
            ProfileOperation(
                name="roundtrip_get",
                service="roundtrip",
                description="Get a thing",
                http_method="GET",
                http_path="/api/things/{id}",
                parameters={"id": {"type": "string"}},
                required_params=["id"],
                is_read_only=True,
            ),
        ],
        entities=[
            ProfileEntity(
                name="thing",
                identity_field="id",
                fields={"id": {"type": "string"}, "name": {"type": "string"}},
                required=["id"],
            ),
        ],
        state_machines=[
            ProfileStateMachine(
                entity_type="thing",
                field="status",
                transitions={"new": ["active"], "active": ["done"]},
            ),
        ],
        error_modes=[
            ProfileErrorMode(code="THING_NOT_FOUND", when="Thing not found", http_status=404),
        ],
        behavioral_notes=["Things are always round"],
        examples=[
            ProfileExample(
                operation="roundtrip_create",
                request={"name": "ball"},
                response={"id": "thing-1"},
            ),
        ],
        responder_prompt="You simulate a thing service.",
        confidence=0.75,
    )

    # Save
    loader = ProfileLoader(tmp_path)
    saved_path = loader.save(original)
    assert saved_path.exists()
    assert saved_path.name == "roundtrip.profile.yaml"

    # Reload
    reloaded_loader = ProfileLoader(tmp_path)
    reloaded = reloaded_loader.load("roundtrip")
    assert reloaded is not None

    # Verify key fields survived the roundtrip
    assert reloaded.profile_name == original.profile_name
    assert reloaded.service_name == original.service_name
    assert reloaded.category == original.category
    assert reloaded.version == original.version
    assert reloaded.fidelity_source == original.fidelity_source
    assert len(reloaded.operations) == len(original.operations)
    assert reloaded.operations[0].name == original.operations[0].name
    assert reloaded.operations[0].http_method == original.operations[0].http_method
    assert reloaded.operations[0].creates_entity == original.operations[0].creates_entity
    assert reloaded.operations[1].is_read_only == original.operations[1].is_read_only
    assert len(reloaded.entities) == len(original.entities)
    assert reloaded.entities[0].name == original.entities[0].name
    assert reloaded.entities[0].identity_field == original.entities[0].identity_field
    assert len(reloaded.state_machines) == len(original.state_machines)
    assert reloaded.state_machines[0].transitions == original.state_machines[0].transitions
    assert len(reloaded.error_modes) == len(original.error_modes)
    assert reloaded.error_modes[0].code == original.error_modes[0].code
    assert reloaded.behavioral_notes == original.behavioral_notes
    assert len(reloaded.examples) == len(original.examples)
    assert reloaded.responder_prompt == original.responder_prompt
    assert reloaded.confidence == original.confidence

    # The reloaded profile should also convert to a valid surface
    surface = profile_to_surface(reloaded)
    assert surface.service_name == "roundtrip"
    assert len(surface.operations) == 2
    assert "thing" in surface.entity_schemas
