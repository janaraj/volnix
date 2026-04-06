"""Tests for volnix.packs.registry — PackRegistry with generic MockPack (never EmailPack)."""

import pytest

from volnix.core.context import ResponseProposal
from volnix.core.errors import DuplicatePackError, PackNotFoundError
from volnix.packs.base import ServicePack
from volnix.packs.registry import PackRegistry

# ---------------------------------------------------------------------------
# MockPack — proves the framework is generic (never uses EmailPack here)
# ---------------------------------------------------------------------------


class MockPack(ServicePack):
    pack_name = "mock"
    category = "test_category"
    fidelity_tier = 1

    def get_tools(self):
        return [
            {
                "name": "mock_action",
                "description": "A mock action",
                "parameters": {
                    "type": "object",
                    "required": ["x"],
                    "properties": {
                        "x": {"type": "integer"},
                    },
                },
            },
        ]

    def get_entity_schemas(self):
        return {
            "mock_entity": {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            },
        }

    def get_state_machines(self):
        return {}

    async def handle_action(self, action, input_data, state):
        return ResponseProposal(response_body={"result": "ok"})


class MockPack2(ServicePack):
    """Second mock pack — proves multi-pack registration."""

    pack_name = "mock2"
    category = "test_category"
    fidelity_tier = 1

    def get_tools(self):
        return [{"name": "mock2_action", "description": "Another mock action"}]

    def get_entity_schemas(self):
        return {}

    def get_state_machines(self):
        return {}

    async def handle_action(self, action, input_data, state):
        return ResponseProposal(response_body={"result": "ok2"})


class EmptyNamePack(ServicePack):
    """Pack with empty name — should be rejected."""

    pack_name = ""
    category = "broken"
    fidelity_tier = 1

    def get_tools(self):
        return []

    def get_entity_schemas(self):
        return {}

    def get_state_machines(self):
        return {}

    async def handle_action(self, action, input_data, state):
        return ResponseProposal()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPackRegistry:
    def test_register_and_get(self):
        """Register a pack and retrieve it by name."""
        registry = PackRegistry()
        pack = MockPack()
        registry.register(pack)
        assert registry.get_pack("mock") is pack

    def test_register_duplicate_raises(self):
        """Registering the same pack_name twice raises DuplicatePackError."""
        registry = PackRegistry()
        registry.register(MockPack())
        with pytest.raises(DuplicatePackError, match="mock"):
            registry.register(MockPack())

    def test_register_empty_name_raises(self):
        """Registering a pack with empty pack_name raises ValueError."""
        registry = PackRegistry()
        with pytest.raises(ValueError, match="non-empty"):
            registry.register(EmptyNamePack())

    def test_get_pack_not_found(self):
        """Getting an unregistered pack raises PackNotFoundError with available list."""
        registry = PackRegistry()
        registry.register(MockPack())
        with pytest.raises(PackNotFoundError, match="nonexistent"):
            registry.get_pack("nonexistent")

    def test_get_pack_for_tool(self):
        """Reverse lookup: tool name -> owning pack."""
        registry = PackRegistry()
        pack = MockPack()
        registry.register(pack)
        assert registry.get_pack_for_tool("mock_action") is pack

    def test_get_pack_for_unknown_tool(self):
        """Looking up an unknown tool raises PackNotFoundError."""
        registry = PackRegistry()
        registry.register(MockPack())
        with pytest.raises(PackNotFoundError, match="no_such_tool"):
            registry.get_pack_for_tool("no_such_tool")

    def test_get_packs_for_category(self):
        """Category lookup returns all packs in that category."""
        registry = PackRegistry()
        registry.register(MockPack())
        registry.register(MockPack2())
        packs = registry.get_packs_for_category("test_category")
        assert len(packs) == 2
        names = {p.pack_name for p in packs}
        assert names == {"mock", "mock2"}

    def test_get_packs_unknown_category(self):
        """Unknown category returns empty list (no error)."""
        registry = PackRegistry()
        assert registry.get_packs_for_category("nonexistent") == []

    def test_list_packs(self):
        """list_packs returns metadata dicts for all registered packs."""
        registry = PackRegistry()
        registry.register(MockPack())
        result = registry.list_packs()
        assert len(result) == 1
        entry = result[0]
        assert entry["pack_name"] == "mock"
        assert entry["category"] == "test_category"
        assert entry["fidelity_tier"] == 1
        assert "mock_action" in entry["tools"]

    def test_list_tools(self):
        """list_tools aggregates tools across all packs."""
        registry = PackRegistry()
        registry.register(MockPack())
        registry.register(MockPack2())
        tools = registry.list_tools()
        tool_names = {t["name"] for t in tools}
        assert "mock_action" in tool_names
        assert "mock2_action" in tool_names
        # Each tool has pack_name and category injected
        for t in tools:
            assert "pack_name" in t
            assert "category" in t

    def test_has_pack_and_has_tool(self):
        """Boolean checks for pack and tool existence."""
        registry = PackRegistry()
        assert not registry.has_pack("mock")
        assert not registry.has_tool("mock_action")
        registry.register(MockPack())
        assert registry.has_pack("mock")
        assert registry.has_tool("mock_action")
        assert not registry.has_pack("nonexistent")
        assert not registry.has_tool("nonexistent")
