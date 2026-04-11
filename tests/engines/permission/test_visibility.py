"""Tests for entity-level visibility scoping in Permission Engine.

Covers: rule resolution, $self reference, include_unmatched, wildcard,
backward compatibility (no rules = no filtering).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from volnix.core.types import ActorId, EntityId

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_permission_engine(
    actor_role: str = "customer",
    visibility_rules: list[dict[str, Any]] | None = None,
    entities: dict[str, list[dict[str, Any]]] | None = None,
) -> Any:
    """Create a PermissionEngine with mock state engine."""
    from volnix.engines.permission.engine import PermissionEngine

    engine = PermissionEngine()

    # Mock actor registry
    actor_mock = MagicMock()
    actor_mock.role = actor_role
    actor_mock.permissions = {"read": "all", "write": "all"}

    actor_registry = MagicMock()
    actor_registry.get_or_none.return_value = actor_mock
    engine._actor_registry = actor_registry

    # Mock config
    config_mock = MagicMock()
    config_mock.visibility_rule_entity_type = "visibility_rule"
    engine._typed_config = config_mock

    # Mock state engine
    state_engine = AsyncMock()

    all_data = entities or {}
    all_data["visibility_rule"] = visibility_rules or []

    async def mock_query(entity_type: str, filters: dict | None = None):
        data = all_data.get(entity_type, [])
        if filters:
            return [e for e in data if all(e.get(k) == v for k, v in filters.items())]
        return data

    state_engine.query_entities = mock_query
    engine._dependencies = {"state": state_engine}

    return engine


# ---------------------------------------------------------------------------
# Tests: get_visible_entities
# ---------------------------------------------------------------------------


class TestGetVisibleEntities:
    """Tests for PermissionEngine.get_visible_entities()."""

    @pytest.mark.asyncio
    async def test_no_rules_returns_empty(self):
        """No visibility_rule entities → return [] (backward compat)."""
        engine = _make_permission_engine(visibility_rules=[])
        result = await engine.get_visible_entities(ActorId("actor-1"), "ticket")
        assert result == []

    @pytest.mark.asyncio
    async def test_customer_sees_own_tickets(self):
        """Customer rule with filter_field=requester_id sees only their tickets."""
        rules = [
            {
                "id": "vr_customer_ticket",
                "actor_role": "customer",
                "target_entity_type": "ticket",
                "filter_field": "requester_id",
                "filter_value": "$self.actor_id",
            },
        ]
        tickets = [
            {"id": "t1", "requester_id": "cust-1", "subject": "My issue"},
            {"id": "t2", "requester_id": "cust-2", "subject": "Other issue"},
            {"id": "t3", "requester_id": "cust-1", "subject": "Another issue"},
        ]
        engine = _make_permission_engine(
            actor_role="customer",
            visibility_rules=rules,
            entities={"ticket": tickets},
        )
        result = await engine.get_visible_entities(ActorId("cust-1"), "ticket")
        assert len(result) == 2
        assert EntityId("t1") in result
        assert EntityId("t3") in result

    @pytest.mark.asyncio
    async def test_agent_sees_assigned_plus_unassigned(self):
        """Agent with include_unmatched=True sees assigned + unassigned."""
        rules = [
            {
                "id": "vr_agent_ticket",
                "actor_role": "agent",
                "target_entity_type": "ticket",
                "filter_field": "assignee_id",
                "filter_value": "$self.actor_id",
                "include_unmatched": True,
            },
        ]
        tickets = [
            {"id": "t1", "assignee_id": "agent-1"},
            {"id": "t2", "assignee_id": "agent-2"},
            {"id": "t3", "assignee_id": "agent-1"},
            {"id": "t4", "assignee_id": None},  # unassigned
            {"id": "t5", "assignee_id": ""},  # unassigned
        ]
        engine = _make_permission_engine(
            actor_role="agent",
            visibility_rules=rules,
            entities={"ticket": tickets},
        )
        result = await engine.get_visible_entities(ActorId("agent-1"), "ticket")
        # agent-1 assigned (t1, t3) + unassigned (t4, t5) = 4
        assert len(result) == 4
        assert EntityId("t2") not in result

    @pytest.mark.asyncio
    async def test_supervisor_sees_all(self):
        """Supervisor with filter_field=None sees all entities."""
        rules = [
            {
                "id": "vr_supervisor_all",
                "actor_role": "supervisor",
                "target_entity_type": "*",
                "filter_field": None,
            },
        ]
        tickets = [
            {"id": "t1"},
            {"id": "t2"},
            {"id": "t3"},
            {"id": "t4"},
            {"id": "t5"},
        ]
        engine = _make_permission_engine(
            actor_role="supervisor",
            visibility_rules=rules,
            entities={"ticket": tickets},
        )
        result = await engine.get_visible_entities(ActorId("sup-1"), "ticket")
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_wildcard_entity_type(self):
        """Rule with target_entity_type="*" applies to any entity type."""
        rules = [
            {
                "id": "vr_admin_all",
                "actor_role": "admin",
                "target_entity_type": "*",
                "filter_field": None,
            },
        ]
        emails = [{"id": "e1"}, {"id": "e2"}]
        engine = _make_permission_engine(
            actor_role="admin",
            visibility_rules=rules,
            entities={"email": emails},
        )
        result = await engine.get_visible_entities(ActorId("admin-1"), "email")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_self_reference_resolved(self):
        """$self.actor_id is replaced with actual actor ID."""
        rules = [
            {
                "id": "vr_cust_ticket",
                "actor_role": "customer",
                "target_entity_type": "ticket",
                "filter_field": "requester_id",
                "filter_value": "$self.actor_id",
            },
        ]
        tickets = [
            {"id": "t1", "requester_id": "cust-A"},
            {"id": "t2", "requester_id": "cust-B"},
        ]
        engine = _make_permission_engine(
            actor_role="customer",
            visibility_rules=rules,
            entities={"ticket": tickets},
        )
        result_a = await engine.get_visible_entities(ActorId("cust-A"), "ticket")
        result_b = await engine.get_visible_entities(ActorId("cust-B"), "ticket")
        assert len(result_a) == 1
        assert EntityId("t1") in result_a
        assert len(result_b) == 1
        assert EntityId("t2") in result_b

    @pytest.mark.asyncio
    async def test_no_applicable_rules_returns_empty(self):
        """Rules exist for other entity types but not this one → []."""
        rules = [
            {
                "id": "vr_customer_email",
                "actor_role": "customer",
                "target_entity_type": "email",
                "filter_field": "to",
                "filter_value": "$self.actor_id",
            },
        ]
        engine = _make_permission_engine(
            actor_role="customer",
            visibility_rules=rules,
            entities={"ticket": [{"id": "t1"}]},
        )
        result = await engine.get_visible_entities(ActorId("cust-1"), "ticket")
        assert result == []


# ---------------------------------------------------------------------------
# Tests: has_visibility_rules
# ---------------------------------------------------------------------------


class TestHasVisibilityRules:
    @pytest.mark.asyncio
    async def test_no_rules_returns_false(self):
        engine = _make_permission_engine(visibility_rules=[])
        assert await engine.has_visibility_rules(ActorId("a"), "ticket") is False

    @pytest.mark.asyncio
    async def test_rules_exist_returns_true(self):
        rules = [
            {
                "id": "vr1",
                "actor_role": "customer",
                "target_entity_type": "ticket",
            },
        ]
        engine = _make_permission_engine(
            actor_role="customer",
            visibility_rules=rules,
        )
        assert await engine.has_visibility_rules(ActorId("c1"), "ticket") is True

    @pytest.mark.asyncio
    async def test_rules_for_other_type_returns_false(self):
        rules = [
            {
                "id": "vr1",
                "actor_role": "customer",
                "target_entity_type": "email",
            },
        ]
        engine = _make_permission_engine(
            actor_role="customer",
            visibility_rules=rules,
        )
        assert await engine.has_visibility_rules(ActorId("c1"), "ticket") is False


# ---------------------------------------------------------------------------
# Test harness — structural contracts
# ---------------------------------------------------------------------------


class TestVisibilityHarness:
    """Catch regressions if visibility system is modified."""

    def test_protocol_defines_both_methods(self):
        from volnix.core.protocols import PermissionEngineProtocol

        assert hasattr(PermissionEngineProtocol, "get_visible_entities")
        assert hasattr(PermissionEngineProtocol, "has_visibility_rules")

    def test_permission_engine_implements_both(self):
        from volnix.engines.permission.engine import PermissionEngine

        assert hasattr(PermissionEngine, "get_visible_entities")
        assert hasattr(PermissionEngine, "has_visibility_rules")
        assert hasattr(PermissionEngine, "_resolve_self_ref")

    def test_supply_chain_pattern_buyer_sees_public_and_own(self):
        """P5 gate test: the supply chain scenario visibility pattern.

        Two agents share a single pack (notion) but need hard data
        separation. Pattern: every seeded entity has an ``owner_role``
        field set to "public", "nimbus_buyer", or "haiphong_supplier".
        Per-agent visibility rules produce a UNION of own-private + public.

        This test proves the mechanism works end-to-end for the supply
        chain scenario BEFORE the live run. It's the gate for Phase P5
        of the Clean Rewrite plan.
        """
        import asyncio

        # Two visibility rules for nimbus_buyer: own-private + public
        rules = [
            {
                "id": "vr_buyer_page_own",
                "actor_role": "nimbus_buyer",
                "target_entity_type": "page",
                "filter_field": "owner_role",
                "filter_value": "nimbus_buyer",
            },
            {
                "id": "vr_buyer_page_public",
                "actor_role": "nimbus_buyer",
                "target_entity_type": "page",
                "filter_field": "owner_role",
                "filter_value": "public",
            },
        ]

        pages = [
            # Public pages — visible to everyone
            {"id": "port_haiphong", "owner_role": "public", "status": "open"},
            {"id": "weather_td_18w", "owner_role": "public", "severity": "TD"},
            {"id": "market_comp_day30", "owner_role": "public", "price": 26},
            # Buyer-private pages — only Dana
            {"id": "prod_schedule_a1", "owner_role": "nimbus_buyer", "days_remaining": 5.4},
            {"id": "cfo_authority_pwr7a", "owner_role": "nimbus_buyer", "ceiling": 32},
            # Supplier-private pages — only Linh, MUST NOT leak to Dana
            {
                "id": "haiphong_inventory_pwr7a",
                "owner_role": "haiphong_supplier",
                "available": 25000,
            },
            {"id": "order_book_megagadget", "owner_role": "haiphong_supplier", "qty": 15000},
        ]

        engine = _make_permission_engine(
            actor_role="nimbus_buyer",
            visibility_rules=rules,
            entities={"page": pages},
        )

        result = asyncio.run(engine.get_visible_entities(ActorId("nimbus_buyer"), "page"))

        # Dana sees the 3 public pages + 2 buyer-private = 5 pages
        visible_ids = {str(eid) for eid in result}
        assert "port_haiphong" in visible_ids
        assert "weather_td_18w" in visible_ids
        assert "market_comp_day30" in visible_ids
        assert "prod_schedule_a1" in visible_ids
        assert "cfo_authority_pwr7a" in visible_ids
        # And must NOT see either supplier-private page
        assert "haiphong_inventory_pwr7a" not in visible_ids
        assert "order_book_megagadget" not in visible_ids
        assert len(visible_ids) == 5

    def test_supply_chain_pattern_supplier_sees_public_and_own(self):
        """P5 gate test (symmetric): supplier sees only public + supplier-private.

        Mirror of ``test_supply_chain_pattern_buyer_sees_public_and_own``.
        Asserts that nimbus_buyer private data does NOT leak to the
        supplier when the visibility rules are properly set up.
        """
        import asyncio

        rules = [
            {
                "id": "vr_supplier_page_own",
                "actor_role": "haiphong_supplier",
                "target_entity_type": "page",
                "filter_field": "owner_role",
                "filter_value": "haiphong_supplier",
            },
            {
                "id": "vr_supplier_page_public",
                "actor_role": "haiphong_supplier",
                "target_entity_type": "page",
                "filter_field": "owner_role",
                "filter_value": "public",
            },
        ]

        pages = [
            {"id": "port_haiphong", "owner_role": "public"},
            {"id": "weather_td_18w", "owner_role": "public"},
            {"id": "prod_schedule_a1", "owner_role": "nimbus_buyer"},
            {"id": "cfo_authority_pwr7a", "owner_role": "nimbus_buyer"},
            {"id": "haiphong_inventory_pwr7a", "owner_role": "haiphong_supplier"},
            {"id": "order_book_megagadget", "owner_role": "haiphong_supplier"},
        ]

        engine = _make_permission_engine(
            actor_role="haiphong_supplier",
            visibility_rules=rules,
            entities={"page": pages},
        )

        result = asyncio.run(engine.get_visible_entities(ActorId("haiphong_supplier"), "page"))

        visible_ids = {str(eid) for eid in result}
        # Public (2) + supplier-private (2) = 4
        assert "port_haiphong" in visible_ids
        assert "weather_td_18w" in visible_ids
        assert "haiphong_inventory_pwr7a" in visible_ids
        assert "order_book_megagadget" in visible_ids
        # Buyer-private must NOT leak
        assert "prod_schedule_a1" not in visible_ids
        assert "cfo_authority_pwr7a" not in visible_ids
        assert len(visible_ids) == 4

    def test_supply_chain_pattern_no_rules_means_no_filtering(self):
        """Regression guard: if visibility_rule entities are missing from
        the seed, the engine falls through to returning all entities.

        This is documented backward-compat behavior — the blueprint MUST
        seed visibility_rule entities for the pattern to enforce
        separation. A missing seed would silently expose all data.
        The compile smoke test in Phase P6.1 must verify the seeds exist.
        """
        import asyncio

        engine = _make_permission_engine(
            actor_role="nimbus_buyer",
            visibility_rules=[],  # no rules seeded
            entities={"page": [{"id": "p1"}, {"id": "p2"}]},
        )

        # With no rules, get_visible_entities returns [] (meaning
        # "no filtering" to the caller). _query_with_visibility in
        # the responder then returns all entities. That's backward
        # compat — blueprint authors must remember to seed the rules.
        result = asyncio.run(engine.get_visible_entities(ActorId("nimbus_buyer"), "page"))
        assert result == []

    def test_visibility_rule_type_exists(self):
        from volnix.core.types import VisibilityRule

        rule = VisibilityRule(
            id="test",
            actor_role="test",
            target_entity_type="test",
        )
        assert rule.id == "test"
        assert rule.filter_field is None
        assert rule.include_unmatched is False

    def test_config_has_visibility_rule_entity_type(self):
        from volnix.engines.permission.config import PermissionConfig

        config = PermissionConfig()
        assert config.visibility_rule_entity_type == "visibility_rule"

    def test_visibility_rule_is_frozen(self):
        from volnix.core.types import VisibilityRule

        rule = VisibilityRule(
            id="test",
            actor_role="test",
            target_entity_type="test",
        )
        with pytest.raises(Exception):
            rule.id = "changed"
