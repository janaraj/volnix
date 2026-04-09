"""Tests for the GameEngine — game lifecycle, scoring, and win conditions."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from volnix.core.events import Event
from volnix.core.types import Timestamp
from volnix.engines.game.definition import (
    GameDefinition,
    RoundConfig,
    ScoringConfig,
    ScoringMetric,
    WinCondition,
)
from volnix.engines.game.engine import GameEngine


def _make_definition(
    rounds: int = 5,
    mode: str = "competition",
    metrics: list[ScoringMetric] | None = None,
    win_conditions: list[WinCondition] | None = None,
) -> GameDefinition:
    """Build a minimal GameDefinition for testing."""
    return GameDefinition(
        enabled=True,
        mode=mode,
        rounds=RoundConfig(count=rounds),
        scoring=ScoringConfig(
            metrics=metrics or [],
            ranking="descending",
        ),
        win_conditions=win_conditions or [WinCondition(type="rounds_complete")],
    )


def _make_world_event(event_type: str = "world.email_send", actor_id: str = "p1") -> Event:
    """Build a minimal world Event for testing _handle_event."""
    now = datetime.now(UTC)
    return Event(
        event_type=event_type,
        timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
    )


class MockBus:
    """Captures events published to the bus."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    async def publish(self, event: Event) -> None:
        self.events.append(event)

    async def subscribe(self, topic: str, callback: Any) -> None:
        pass

    async def unsubscribe(self, topic: str, callback: Any) -> None:
        pass


class MockEntityStore:
    """Stub store for testing ownership assignment."""

    def __init__(self) -> None:
        self.updates: list[tuple[str, str, dict]] = []

    async def update(self, entity_type: str, entity_id: Any, fields: dict[str, Any]) -> dict:
        self.updates.append((entity_type, str(entity_id), fields))
        return {}


class MockStateEngine:
    """Stub state engine that returns canned entity queries."""

    def __init__(self, entities: list[dict[str, Any]] | None = None) -> None:
        self._entities = entities or []
        self._store = MockEntityStore()

    async def query_entities(
        self, entity_type: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return self._entities

    async def list_entity_types(self) -> list[str]:
        return []


@pytest.fixture
def engine() -> GameEngine:
    """Create a GameEngine with a mock bus."""
    e = GameEngine()
    e._bus = MockBus()
    return e


@pytest.fixture
def configured_engine(engine: GameEngine) -> GameEngine:
    """Return a GameEngine already configured with 2 players and 5 rounds."""
    return engine


class TestConfigure:
    async def test_configure_sets_players(self, engine: GameEngine) -> None:
        definition = _make_definition(rounds=5)
        await engine.configure(definition, ["p1", "p2", "p3"])

        assert engine.is_active is True
        assert len(engine.player_scores) == 3
        assert "p1" in engine.player_scores
        assert "p2" in engine.player_scores
        assert "p3" in engine.player_scores
        assert engine.round_state.current_round == 0
        assert engine.round_state.total_rounds == 5
        assert engine.definition is not None
        assert engine.definition.mode == "competition"

    async def test_configure_initializes_scorer_and_evaluator(self, engine: GameEngine) -> None:
        definition = _make_definition(
            metrics=[ScoringMetric(name="speed", weight=2.0)],
        )
        await engine.configure(definition, ["p1"])

        assert engine._scorer is not None
        assert engine._win_evaluator is not None
        assert engine._scorer.weights == {"speed": 2.0}


class TestRoundLifecycle:
    async def test_start_round_advances_state(self, engine: GameEngine) -> None:
        await engine.configure(_make_definition(rounds=5), ["p1", "p2"])

        await engine.start_round()

        assert engine.round_state.current_round == 1
        assert engine.round_state.phase == "in_progress"

    async def test_start_round_publishes_event(self, engine: GameEngine) -> None:
        await engine.configure(_make_definition(), ["p1"])
        bus: MockBus = engine._bus  # type: ignore[assignment]

        await engine.start_round()

        round_events = [e for e in bus.events if e.event_type == "game.round_started"]
        assert len(round_events) == 1
        assert round_events[0].round_number == 1

    async def test_multiple_rounds_advance_sequentially(self, engine: GameEngine) -> None:
        await engine.configure(_make_definition(rounds=10), ["p1"])

        await engine.start_round()
        assert engine.round_state.current_round == 1

        # end_round transitions to between_rounds
        await engine.end_round()
        assert engine.round_state.phase == "between_rounds"

        await engine.start_round()
        assert engine.round_state.current_round == 2

    async def test_start_round_clears_events(self, engine: GameEngine) -> None:
        await engine.configure(_make_definition(), ["p1"])
        engine._dependencies["state"] = MockStateEngine()

        # Simulate some events in round 1 (injected directly)
        await engine.start_round()
        engine._events_this_round.append(_make_world_event())
        assert len(engine._events_this_round) == 1

        # end_round does NOT clear; start_round does
        await engine.end_round()
        await engine.start_round()
        assert len(engine._events_this_round) == 0


class TestEndRound:
    async def test_end_round_computes_scores(self, engine: GameEngine) -> None:
        definition = _make_definition(
            metrics=[
                ScoringMetric(
                    name="actions",
                    source="events",
                    event_type="world.email_send",
                    aggregation="count",
                    weight=1.0,
                ),
            ],
        )
        await engine.configure(definition, ["p1", "p2"])
        engine._dependencies["state"] = MockStateEngine()

        await engine.start_round()

        # Inject world events attributed to p1
        engine._events_this_round = [
            SimpleNamespace(event_type="world.email_send", actor_id="p1", input_data={}),
            SimpleNamespace(event_type="world.email_send", actor_id="p1", input_data={}),
            SimpleNamespace(event_type="world.email_send", actor_id="p2", input_data={}),
        ]

        standings = await engine.end_round()

        assert len(standings) == 2
        # p1 had 2 events, p2 had 1
        p1_standing = next(s for s in standings if s["actor_id"] == "p1")
        p2_standing = next(s for s in standings if s["actor_id"] == "p2")
        assert p1_standing["total_score"] > p2_standing["total_score"]
        assert p1_standing["rank"] == 1
        assert p2_standing["rank"] == 2

    async def test_end_round_publishes_event(self, engine: GameEngine) -> None:
        await engine.configure(_make_definition(), ["p1"])
        engine._dependencies["state"] = MockStateEngine()
        bus: MockBus = engine._bus  # type: ignore[assignment]

        await engine.start_round()
        await engine.end_round()

        round_ended = [e for e in bus.events if e.event_type == "game.round_ended"]
        assert len(round_ended) == 1

    async def test_end_round_no_scorer_raises(self, engine: GameEngine) -> None:
        # Don't configure -- no scorer; should raise
        with pytest.raises(RuntimeError, match="Game not configured"):
            await engine.end_round()


class TestWinConditions:
    async def test_check_win_conditions_rounds_complete(self, engine: GameEngine) -> None:
        definition = _make_definition(
            rounds=2,
            win_conditions=[WinCondition(type="rounds_complete")],
        )
        await engine.configure(definition, ["p1", "p2"])
        engine._dependencies["state"] = MockStateEngine()

        # Play 2 rounds
        await engine.start_round()
        await engine.end_round()
        await engine.start_round()
        await engine.end_round()

        # After 2 of 2 rounds, set scores to determine winner
        engine._player_scores["p1"].total_score = 100.0
        engine._player_scores["p2"].total_score = 50.0

        # Advance round_state to reflect current_round == total_rounds
        # end_round sets phase=between_rounds; the evaluator checks current_round >= total_rounds
        # current_round is 2 and total_rounds is 2
        result = await engine.check_win_conditions()

        assert result is not None
        assert result.winner == "p1"
        assert result.reason == "rounds_complete"

    async def test_check_win_conditions_no_evaluator_raises(self, engine: GameEngine) -> None:
        # Not configured; should raise
        with pytest.raises(RuntimeError, match="Game not configured"):
            await engine.check_win_conditions()

    async def test_check_win_conditions_publishes_elimination_event(
        self, engine: GameEngine
    ) -> None:
        definition = _make_definition(
            rounds=10,
            win_conditions=[
                WinCondition(type="elimination", metric="health", threshold=10.0, below=True),
            ],
        )
        await engine.configure(definition, ["p1", "p2"])
        engine._dependencies["state"] = MockStateEngine()

        await engine.start_round()
        await engine.end_round()

        # Set up health metrics: p2 below threshold, p1 above
        engine._player_scores["p1"].metrics = {"health": 50.0}
        engine._player_scores["p1"].total_score = 50.0
        engine._player_scores["p2"].metrics = {"health": 5.0}
        engine._player_scores["p2"].total_score = 5.0

        bus: MockBus = engine._bus  # type: ignore[assignment]
        bus.events.clear()

        result = await engine.check_win_conditions()

        # p2 eliminated, p1 last standing
        assert result is not None
        assert result.winner == "p1"
        assert result.reason == "last_standing"
        elim_events = [e for e in bus.events if e.event_type == "game.elimination"]
        assert len(elim_events) == 1
        assert elim_events[0].actor_id == "p2"
        assert elim_events[0].round_number == engine.round_state.current_round

    async def test_check_win_conditions_not_met(self, engine: GameEngine) -> None:
        definition = _make_definition(
            rounds=10,
            win_conditions=[WinCondition(type="rounds_complete")],
        )
        await engine.configure(definition, ["p1"])
        engine._dependencies["state"] = MockStateEngine()

        await engine.start_round()
        await engine.end_round()

        # Only round 1 of 10 -- shouldn't trigger
        result = await engine.check_win_conditions()
        assert result is None


class TestCompleteGame:
    async def test_complete_game_returns_result(self, engine: GameEngine) -> None:
        definition = _make_definition(rounds=3, mode="competition")
        await engine.configure(definition, ["p1", "p2"])
        engine._dependencies["state"] = MockStateEngine()

        await engine.start_round()
        engine._player_scores["p1"].total_score = 200.0
        engine._player_scores["p2"].total_score = 100.0
        await engine.end_round()

        game_result = await engine.complete_game()

        assert game_result.winner == "p1"
        assert game_result.reason == "rounds_complete"
        assert game_result.game_mode == "competition"
        assert game_result.total_rounds_played == 1
        assert len(game_result.final_standings) == 2
        assert engine.is_active is False
        assert engine.round_state.phase == "completed"

    async def test_complete_game_with_win_result(self, engine: GameEngine) -> None:
        definition = _make_definition(rounds=5)
        await engine.configure(definition, ["p1", "p2"])

        from volnix.engines.game.definition import WinResult

        win = WinResult(winner="p2", reason="score_threshold")
        game_result = await engine.complete_game(result=win)

        assert game_result.winner == "p2"
        assert game_result.reason == "score_threshold"

    async def test_complete_game_publishes_event(self, engine: GameEngine) -> None:
        await engine.configure(_make_definition(), ["p1"])
        bus: MockBus = engine._bus  # type: ignore[assignment]

        await engine.complete_game()

        completed = [e for e in bus.events if e.event_type == "game.completed"]
        assert len(completed) == 1


class TestEndRoundWithExternalEvents:
    async def test_end_round_accepts_round_events(self, engine: GameEngine) -> None:
        """round_events parameter is used for scoring instead of _events_this_round."""
        definition = _make_definition(
            metrics=[
                ScoringMetric(
                    name="trades",
                    source="events",
                    event_type="world.create_order",
                    aggregation="count",
                    weight=1.0,
                ),
            ],
        )
        await engine.configure(definition, ["p1", "p2"])
        engine._dependencies["state"] = MockStateEngine()

        await engine.start_round()

        # Pass events externally (as GameRunner would)
        round_events = [
            SimpleNamespace(event_type="world.create_order", actor_id="p1", input_data={}),
            SimpleNamespace(event_type="world.create_order", actor_id="p1", input_data={}),
            SimpleNamespace(event_type="world.create_order", actor_id="p2", input_data={}),
        ]
        standings = await engine.end_round(round_events=round_events)

        p1 = next(s for s in standings if s["actor_id"] == "p1")
        p2 = next(s for s in standings if s["actor_id"] == "p2")
        assert p1["metrics"]["trades"] == 2.0
        assert p2["metrics"]["trades"] == 1.0


class TestEntityOwnership:
    async def test_configure_assigns_ownership(self, engine: GameEngine) -> None:
        """configure() assigns game_owner_id on first N entities via state store."""
        definition = _make_definition(
            metrics=[
                ScoringMetric(
                    name="value",
                    source="state",
                    entity_type="alpaca_account",
                    field="equity",
                ),
            ],
        )
        mock_state = MockStateEngine(
            entities=[
                {"id": "acct_01", "equity": 100000.0},
                {"id": "acct_02", "equity": 100000.0},
                {"id": "acct_03", "equity": 100000.0},
                {"id": "acct_04", "equity": 100000.0},  # extra — should NOT get assigned
            ]
        )
        engine._dependencies["state"] = mock_state
        await engine.configure(definition, ["trader-a", "trader-b", "trader-c"])

        # 3 updates (one per player), NOT 4
        updates = mock_state._store.updates
        assert len(updates) == 3
        assert updates[0] == ("alpaca_account", "acct_01", {"game_owner_id": "trader-a"})
        assert updates[1] == ("alpaca_account", "acct_02", {"game_owner_id": "trader-b"})
        assert updates[2] == ("alpaca_account", "acct_03", {"game_owner_id": "trader-c"})

    async def test_configure_no_state_engine_skips_ownership(self, engine: GameEngine) -> None:
        """Without state engine, no ownership assignment."""
        await engine.configure(_make_definition(), ["p1"])
        assert engine._resolved_entity_types == {}


class TestHandleEvent:
    async def test_handle_event_is_noop(self, engine: GameEngine) -> None:
        """_handle_event is a no-op — events are collected by GameRunner."""
        await engine.configure(_make_definition(), ["p1"])

        world_event = _make_world_event("world.email_send")
        await engine._handle_event(world_event)

        # No-op: events_this_round stays empty (collected by runner instead)
        assert len(engine._events_this_round) == 0


class TestGetStandings:
    async def test_get_standings_sorted(self, engine: GameEngine) -> None:
        await engine.configure(_make_definition(), ["p1", "p2", "p3"])

        engine._player_scores["p1"].total_score = 50.0
        engine._player_scores["p2"].total_score = 150.0
        engine._player_scores["p3"].total_score = 100.0

        standings = await engine.get_standings()

        assert len(standings) == 3
        assert standings[0]["actor_id"] == "p2"
        assert standings[0]["rank"] == 1
        assert standings[0]["total_score"] == 150.0
        assert standings[1]["actor_id"] == "p3"
        assert standings[1]["rank"] == 2
        assert standings[2]["actor_id"] == "p1"
        assert standings[2]["rank"] == 3

    async def test_get_standings_empty_when_no_players(self, engine: GameEngine) -> None:
        standings = await engine.get_standings()
        assert standings == []


class TestStartGame:
    async def test_start_game_publishes_event(self, engine: GameEngine) -> None:
        definition = _make_definition(rounds=5, mode="cooperative")
        await engine.configure(definition, ["p1", "p2"])
        bus: MockBus = engine._bus  # type: ignore[assignment]

        await engine.start_game()

        started = [e for e in bus.events if e.event_type == "game.started"]
        assert len(started) == 1
        assert started[0].game_mode == "cooperative"
        assert set(started[0].player_ids) == {"p1", "p2"}
        assert started[0].total_rounds == 5

    async def test_start_game_no_definition_raises(self, engine: GameEngine) -> None:
        # Not configured; should raise
        with pytest.raises(RuntimeError, match="Game not configured"):
            await engine.start_game()


class TestEngineLifecycle:
    async def test_engine_name(self) -> None:
        engine = GameEngine()
        assert engine.engine_name == "game"

    async def test_subscriptions(self) -> None:
        engine = GameEngine()
        assert engine.subscriptions == []  # events collected by GameRunner, not bus

    async def test_dependencies(self) -> None:
        engine = GameEngine()
        assert "state" in engine.dependencies
        assert "budget" in engine.dependencies

    async def test_initialize_loads_config(self) -> None:
        engine = GameEngine()
        await engine.initialize({"max_rounds": 50, "max_players": 10}, MockBus())

        assert engine._game_config.max_rounds == 50
        assert engine._game_config.max_players == 10

    async def test_initialize_with_empty_config(self) -> None:
        engine = GameEngine()
        await engine.initialize({}, MockBus())

        # Defaults preserved
        assert engine._game_config.max_rounds == 100
        assert engine._game_config.max_players == 20
