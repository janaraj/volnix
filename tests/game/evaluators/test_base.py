"""Tests for BaseRoundEvaluator — state I/O, ledger integration, player resolution."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from volnix.game.evaluators.base import BaseRoundEvaluator

# ---------------------------------------------------------------------------
# State access initialization
# ---------------------------------------------------------------------------


class TestInitStateAccess:
    def test_success(self):
        evaluator = BaseRoundEvaluator()
        state = MagicMock()
        state._store = MagicMock()
        state._ledger = MagicMock()

        result = evaluator._init_state_access(state)

        assert result is True
        assert evaluator._state_engine is state
        assert evaluator._store is state._store
        assert evaluator._ledger is state._ledger

    def test_none_engine(self):
        evaluator = BaseRoundEvaluator()
        result = evaluator._init_state_access(None)
        assert result is False

    def test_no_store(self):
        evaluator = BaseRoundEvaluator()
        state = MagicMock()
        state._store = None
        result = evaluator._init_state_access(state)
        assert result is False

    def test_no_ledger_still_succeeds(self):
        evaluator = BaseRoundEvaluator()
        state = MagicMock()
        state._store = MagicMock()
        state._ledger = None
        result = evaluator._init_state_access(state)
        assert result is True
        assert evaluator._ledger is None


# ---------------------------------------------------------------------------
# Audited state writes
# ---------------------------------------------------------------------------


class TestCreateEntity:
    async def test_success_with_ledger(self):
        evaluator = BaseRoundEvaluator()
        evaluator._store = AsyncMock()
        evaluator._store.create = AsyncMock()
        evaluator._ledger = AsyncMock()
        evaluator._ledger.append = AsyncMock()

        result = await evaluator._create_entity("test_type", "id-1", {"field": "val"})

        assert result is True
        evaluator._store.create.assert_awaited_once()
        evaluator._ledger.append.assert_awaited_once()
        # Verify ledger entry type
        entry = evaluator._ledger.append.call_args[0][0]
        assert entry.entity_type == "test_type"
        assert entry.operation == "create"
        assert entry.after == {"field": "val"}

    async def test_success_without_ledger(self):
        evaluator = BaseRoundEvaluator()
        evaluator._store = AsyncMock()
        evaluator._store.create = AsyncMock()
        evaluator._ledger = None

        result = await evaluator._create_entity("test_type", "id-1", {"field": "val"})

        assert result is True
        evaluator._store.create.assert_awaited_once()

    async def test_store_failure_returns_false(self):
        evaluator = BaseRoundEvaluator()
        evaluator._store = AsyncMock()
        evaluator._store.create = AsyncMock(side_effect=RuntimeError("DB error"))
        evaluator._ledger = AsyncMock()
        evaluator._ledger.append = AsyncMock()

        result = await evaluator._create_entity("test_type", "id-1", {"field": "val"})

        assert result is False
        evaluator._ledger.append.assert_not_awaited()


class TestUpdateEntity:
    async def test_success_with_ledger(self):
        evaluator = BaseRoundEvaluator()
        evaluator._store = AsyncMock()
        evaluator._store.update = AsyncMock(return_value={"field": "old_val"})
        evaluator._ledger = AsyncMock()
        evaluator._ledger.append = AsyncMock()

        result = await evaluator._update_entity("test_type", "id-1", {"field": "new_val"})

        assert result is True
        evaluator._store.update.assert_awaited_once()
        evaluator._ledger.append.assert_awaited_once()
        entry = evaluator._ledger.append.call_args[0][0]
        assert entry.operation == "update"
        assert entry.before == {"field": "old_val"}
        assert entry.after == {"field": "new_val"}

    async def test_store_failure_returns_false(self):
        evaluator = BaseRoundEvaluator()
        evaluator._store = AsyncMock()
        evaluator._store.update = AsyncMock(side_effect=RuntimeError("not found"))
        evaluator._ledger = AsyncMock()

        result = await evaluator._update_entity("test_type", "id-1", {"field": "val"})

        assert result is False


class TestRecordMutation:
    async def test_ledger_failure_graceful(self):
        evaluator = BaseRoundEvaluator()
        evaluator._ledger = AsyncMock()
        evaluator._ledger.append = AsyncMock(side_effect=RuntimeError("ledger down"))

        # Should not raise
        await evaluator._record_mutation("type", "id", "create", after={"x": 1})


# ---------------------------------------------------------------------------
# Player ID resolution
# ---------------------------------------------------------------------------


class TestResolvePlayerForEntity:
    def test_exact_match(self):
        entity = {"game_owner_id": "buyer-abc"}
        result = BaseRoundEvaluator._resolve_player_for_entity(
            entity, ["buyer-abc", "supplier-xyz"]
        )
        assert result == "buyer-abc"

    def test_prefix_match_owner_shorter(self):
        """Compiler sets 'buyer', runtime ID is 'buyer-abc123'."""
        entity = {"game_owner_id": "buyer"}
        result = BaseRoundEvaluator._resolve_player_for_entity(
            entity, ["buyer-abc123", "supplier-xyz456"]
        )
        assert result == "buyer-abc123"

    def test_prefix_match_owner_longer(self):
        """Runtime ID is prefix of game_owner_id (unlikely but handled)."""
        entity = {"game_owner_id": "buyer-abc123"}
        result = BaseRoundEvaluator._resolve_player_for_entity(
            entity, ["buyer-abc", "supplier-xyz"]
        )
        # "buyer-abc123".startswith("buyer-abc") is False,
        # but "buyer-abc".startswith("buyer-abc123") is False too
        # so we check owner.startswith(pid): "buyer-abc123".startswith("buyer-abc") → True!
        # Wait, that's pid.startswith(owner) check, not the right one.
        # Actually: pid="buyer-abc", owner="buyer-abc123" → pid.startswith(owner)=False, owner.startswith(pid)=True → matches
        assert result == "buyer-abc"

    def test_no_match(self):
        entity = {"game_owner_id": "unknown"}
        result = BaseRoundEvaluator._resolve_player_for_entity(
            entity, ["buyer-abc", "supplier-xyz"]
        )
        assert result == ""

    def test_empty_owner(self):
        entity = {"game_owner_id": ""}
        result = BaseRoundEvaluator._resolve_player_for_entity(entity, ["buyer-abc"])
        assert result == ""

    def test_missing_owner(self):
        entity = {}
        result = BaseRoundEvaluator._resolve_player_for_entity(entity, ["buyer-abc"])
        assert result == ""

    def test_empty_player_list(self):
        entity = {"game_owner_id": "buyer"}
        result = BaseRoundEvaluator._resolve_player_for_entity(entity, [])
        assert result == ""


# ---------------------------------------------------------------------------
# Target-to-player resolution via deals
# ---------------------------------------------------------------------------


class TestResolveTargetsViaDeals:
    def test_exact_game_owner_id(self):
        """When game_owner_id matches exactly, use it."""
        targets = [
            {"game_owner_id": "buyer-abc", "deal_id": "d1"},
            {"game_owner_id": "supplier-xyz", "deal_id": "d1"},
        ]
        deals = [{"id": "d1", "parties": ["buyer", "supplier"]}]
        result = BaseRoundEvaluator._resolve_targets_via_deals(
            targets, deals, ["buyer-abc", "supplier-xyz"]
        )
        assert result["buyer-abc"]["game_owner_id"] == "buyer-abc"
        assert result["supplier-xyz"]["game_owner_id"] == "supplier-xyz"

    def test_fallback_to_deal_parties(self):
        """When game_owner_id is a Slack user ID, fall back to deal parties."""
        targets = [
            {"game_owner_id": "U1001", "deal_id": "d1"},
            {"game_owner_id": "U1001", "deal_id": "d1"},
        ]
        deals = [{"id": "d1", "parties": ["buyer", "supplier"]}]
        result = BaseRoundEvaluator._resolve_targets_via_deals(
            targets, deals, ["buyer-794aad24", "supplier-99b0e8da"]
        )
        assert "buyer-794aad24" in result
        assert "supplier-99b0e8da" in result

    def test_empty_targets(self):
        result = BaseRoundEvaluator._resolve_targets_via_deals([], [], ["p1"])
        assert result == {}

    def test_no_matching_parties(self):
        targets = [{"game_owner_id": "X", "deal_id": "d1"}]
        deals = [{"id": "d1", "parties": ["unknown"]}]
        result = BaseRoundEvaluator._resolve_targets_via_deals(targets, deals, ["buyer-abc"])
        assert result == {}

    def test_partial_match(self):
        """One target matches by game_owner_id, the other needs fallback."""
        targets = [
            {"game_owner_id": "buyer-abc", "deal_id": "d1"},
            {"game_owner_id": "U9999", "deal_id": "d1"},
        ]
        deals = [{"id": "d1", "parties": ["buyer", "supplier"]}]
        # Only buyer matches exactly — but since not ALL match, falls back to deal parties
        result = BaseRoundEvaluator._resolve_targets_via_deals(
            targets, deals, ["buyer-abc", "supplier-xyz"]
        )
        assert "buyer-abc" in result
        assert "supplier-xyz" in result
