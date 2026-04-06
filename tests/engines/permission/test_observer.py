"""Tests for observer actor type — read-only enforcement.

Harness tests catch regressions if new write actions are added
to packs without updating the observer prefix list.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from volnix.core.types import ActorId, ActorType, StepVerdict


def _make_observer_engine(actor_type: str = "observer") -> tuple:
    """Create PermissionEngine with mock actor of given type."""
    from volnix.engines.permission.engine import PermissionEngine

    engine = PermissionEngine()

    actor_mock = MagicMock()
    actor_mock.role = "market-analyst"
    actor_mock.type = actor_type
    actor_mock.permissions = {"read": "all", "write": "all"}

    registry = MagicMock()
    registry.get_or_none.return_value = actor_mock
    engine._actor_registry = registry

    config_mock = MagicMock()
    config_mock.visibility_rule_entity_type = "visibility_rule"
    config_mock.observer_read_prefixes = [
        "list",
        "get",
        "show",
        "search",
        "read",
        "query",
        "about",
        "hot",
        "new",
        "top",
        "best",
        "popular",
    ]
    engine._typed_config = config_mock
    engine._world_mode = "governed"

    return engine, actor_mock


def _make_ctx(action: str) -> MagicMock:
    """Create a minimal ActionContext mock."""
    ctx = MagicMock()
    ctx.actor_id = ActorId("observer-1")
    ctx.service_id = "tickets"
    ctx.action = action
    return ctx


class TestObserverPermissions:
    @pytest.mark.asyncio
    async def test_observer_can_read(self):
        """Observer can call list/get/search/read actions."""
        engine, _ = _make_observer_engine("observer")
        for action in ["list_tickets", "get_ticket", "search_posts", "query_entities"]:
            ctx = _make_ctx(action)
            result = await engine.execute(ctx)
            assert result.verdict == StepVerdict.ALLOW, (
                f"Observer should be allowed to call '{action}'"
            )

    @pytest.mark.asyncio
    async def test_observer_cannot_write(self):
        """Observer is denied create/update/delete actions."""
        engine, _ = _make_observer_engine("observer")
        for action in ["create_ticket", "update_ticket", "delete_ticket", "submit_order"]:
            ctx = _make_ctx(action)
            result = await engine.execute(ctx)
            assert result.verdict == StepVerdict.DENY, f"Observer should be denied '{action}'"

    @pytest.mark.asyncio
    async def test_observer_denied_event_published(self):
        """Observer denial produces a PermissionDeniedEvent."""
        engine, _ = _make_observer_engine("observer")
        ctx = _make_ctx("create_ticket")
        result = await engine.execute(ctx)
        assert result.verdict == StepVerdict.DENY
        assert len(result.events) >= 1
        assert "Observer" in result.message

    @pytest.mark.asyncio
    async def test_non_observer_unaffected(self):
        """Internal actor with same role is not restricted."""
        engine, actor = _make_observer_engine("human")
        ctx = _make_ctx("create_ticket")
        result = await engine.execute(ctx)
        # human type should NOT trigger observer check
        assert result.verdict != StepVerdict.DENY or "Observer" not in result.message


class TestObserverHarness:
    """Structural contracts — catch regressions."""

    def test_actor_type_has_observer(self):
        """ActorType enum must include OBSERVER."""
        assert hasattr(ActorType, "OBSERVER")
        assert ActorType.OBSERVER == "observer"

    def test_config_has_read_prefixes(self):
        """PermissionConfig must define observer_read_prefixes."""
        from volnix.engines.permission.config import PermissionConfig

        config = PermissionConfig()
        assert isinstance(config.observer_read_prefixes, list)
        assert len(config.observer_read_prefixes) > 0

    def test_common_read_actions_in_prefixes(self):
        """Basic read prefixes must be present."""
        from volnix.engines.permission.config import PermissionConfig

        config = PermissionConfig()
        required = {"list", "get", "search", "read", "query"}
        actual = set(config.observer_read_prefixes)
        assert required.issubset(actual), f"Missing: {required - actual}"
