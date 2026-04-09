"""Tests for TurnManager."""

from __future__ import annotations

from volnix.game.turn_manager import TurnManager, TurnOrder


class TestFixedOrder:
    def test_fixed_order_returns_same_order(self):
        tm = TurnManager(["p1", "p2", "p3"], order=TurnOrder.FIXED)

        order1 = tm.get_order()
        order2 = tm.get_order()

        assert order1 == ["p1", "p2", "p3"]
        assert order2 == ["p1", "p2", "p3"]


class TestRoundRobin:
    def test_round_robin_rotates(self):
        tm = TurnManager(["p1", "p2", "p3"], order=TurnOrder.ROUND_ROBIN)

        first = tm.get_order()
        second = tm.get_order()
        third = tm.get_order()

        assert first == ["p1", "p2", "p3"]
        assert second == ["p2", "p3", "p1"]
        assert third == ["p3", "p1", "p2"]


class TestRandomOrder:
    def test_random_order_seeded_reproducible(self):
        tm1 = TurnManager(["p1", "p2", "p3", "p4"], order=TurnOrder.RANDOM, seed=42)
        tm2 = TurnManager(["p1", "p2", "p3", "p4"], order=TurnOrder.RANDOM, seed=42)

        order1 = tm1.get_order()
        order2 = tm2.get_order()

        assert order1 == order2


class TestElimination:
    def test_eliminate_removes_player(self):
        tm = TurnManager(["p1", "p2", "p3"], order=TurnOrder.FIXED)

        tm.eliminate("p2")

        assert tm.active_players == ["p1", "p3"]
        assert tm.player_count == 2
        assert tm.get_order() == ["p1", "p3"]

    def test_is_eliminated(self):
        tm = TurnManager(["p1", "p2", "p3"], order=TurnOrder.FIXED)

        assert tm.is_eliminated("p1") is False
        tm.eliminate("p1")
        assert tm.is_eliminated("p1") is True


class TestEdgeCases:
    def test_empty_players_returns_empty(self):
        tm = TurnManager([], order=TurnOrder.FIXED)

        assert tm.get_order() == []
        assert tm.player_count == 0

    def test_reset_restores_all_players(self):
        tm = TurnManager(["p1", "p2", "p3"], order=TurnOrder.FIXED)

        tm.eliminate("p1")
        tm.eliminate("p2")
        assert tm.player_count == 1

        tm.reset()

        assert tm.active_players == ["p1", "p2", "p3"]
        assert tm.player_count == 3
