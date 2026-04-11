"""Tests for the event-driven win condition handlers.

Exercises ``volnix/engines/game/win_conditions.py`` — the set of
handlers that read ``GameState`` / ``state_engine``. Each handler
tested in isolation, plus the ``WinConditionEvaluator`` filter
behavior between behavioral and competitive modes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from volnix.engines.game.definition import (
    GameState,
    PlayerScore,
    WinCondition,
)
from volnix.engines.game.win_conditions import (
    WIN_CONDITION_HANDLER_REGISTRY,
    AllBudgetsExhaustedHandler,
    DealClosedHandler,
    DealRejectedHandler,
    EliminationHandler,
    MaxEventsExceededHandler,
    ScoreThresholdHandler,
    StalemateHandler,
    WallClockElapsedHandler,
    WinConditionContext,
    WinConditionEvaluator,
)


def _make_scores(
    player_ids: list[str], scores: dict[str, float] | None = None
) -> dict[str, PlayerScore]:
    ps_map: dict[str, PlayerScore] = {}
    for pid in player_ids:
        ps = PlayerScore(actor_id=pid)
        if scores and pid in scores:
            ps.total_score = scores[pid]
            ps.metrics = {"total_points": scores[pid]}
        ps_map[pid] = ps
    return ps_map


def _make_ctx(
    condition: WinCondition,
    scores: dict[str, PlayerScore],
    game_state: GameState | None = None,
    state_engine: AsyncMock | None = None,
    exhausted: set[str] | None = None,
) -> WinConditionContext:
    return WinConditionContext(
        condition=condition,
        scores=scores,
        game_state=game_state or GameState(),
        state_engine=state_engine or AsyncMock(query_entities=AsyncMock(return_value=[])),
        exhausted_players=exhausted or set(),
    )


class TestDealClosedHandler:
    """Fires when any negotiation_deal reaches status=accepted."""

    async def test_returns_none_when_no_deals_in_state(self):
        handler = DealClosedHandler()
        state = AsyncMock()
        state.query_entities = AsyncMock(return_value=[])
        ctx = _make_ctx(
            WinCondition(type="deal_closed"), _make_scores(["a", "b"]), state_engine=state
        )
        assert await handler.check(ctx) is None

    async def test_returns_none_when_deal_is_still_open(self):
        handler = DealClosedHandler()
        state = AsyncMock()
        state.query_entities = AsyncMock(return_value=[{"id": "d1", "status": "open"}])
        ctx = _make_ctx(
            WinCondition(type="deal_closed"), _make_scores(["a", "b"]), state_engine=state
        )
        assert await handler.check(ctx) is None

    async def test_fires_when_deal_is_accepted(self):
        handler = DealClosedHandler()
        state = AsyncMock()
        state.query_entities = AsyncMock(return_value=[{"id": "d1", "status": "accepted"}])
        ctx = _make_ctx(
            WinCondition(type="deal_closed"),
            _make_scores(["a", "b"], {"a": 80.0, "b": 60.0}),
            state_engine=state,
        )
        result = await handler.check(ctx)
        assert result is not None
        assert result.reason == "deal_closed"
        assert result.winner == "a"  # highest score
        assert len(result.final_standings) == 2

    async def test_query_failure_returns_none_not_raise(self):
        handler = DealClosedHandler()
        state = AsyncMock()
        state.query_entities = AsyncMock(side_effect=RuntimeError("db down"))
        ctx = _make_ctx(
            WinCondition(type="deal_closed"), _make_scores(["a", "b"]), state_engine=state
        )
        assert await handler.check(ctx) is None


class TestDealRejectedHandler:
    """Fires when any negotiation_deal reaches status=rejected."""

    async def test_fires_on_rejected_deal(self):
        handler = DealRejectedHandler()
        state = AsyncMock()
        state.query_entities = AsyncMock(return_value=[{"id": "d1", "status": "rejected"}])
        ctx = _make_ctx(
            WinCondition(type="deal_rejected"), _make_scores(["a", "b"]), state_engine=state
        )
        result = await handler.check(ctx)
        assert result is not None
        assert result.reason == "deal_rejected"
        assert result.winner is None  # no winner on rejection


class TestStalemateHandler:
    """No-op on per-event checks; orchestrator drives via timer."""

    async def test_always_returns_none(self):
        handler = StalemateHandler()
        ctx = _make_ctx(WinCondition(type="stalemate_timeout"), _make_scores(["a", "b"]))
        assert await handler.check(ctx) is None


class TestWallClockElapsedHandler:
    """No-op on per-event checks; orchestrator drives via timer."""

    async def test_always_returns_none(self):
        handler = WallClockElapsedHandler()
        ctx = _make_ctx(WinCondition(type="wall_clock_elapsed"), _make_scores(["a", "b"]))
        assert await handler.check(ctx) is None


class TestMaxEventsExceededHandler:
    """Fires when game_state.event_counter >= max_events from type_config."""

    async def test_does_not_fire_under_cap(self):
        handler = MaxEventsExceededHandler()
        ctx = _make_ctx(
            WinCondition(type="max_events_exceeded", type_config={"max_events": 10}),
            _make_scores(["a", "b"]),
            game_state=GameState(event_counter=5),
        )
        assert await handler.check(ctx) is None

    async def test_fires_at_cap(self):
        handler = MaxEventsExceededHandler()
        ctx = _make_ctx(
            WinCondition(type="max_events_exceeded", type_config={"max_events": 10}),
            _make_scores(["a", "b"]),
            game_state=GameState(event_counter=10),
        )
        result = await handler.check(ctx)
        assert result is not None
        assert result.reason == "max_events_exceeded"
        assert result.winner is None

    async def test_fires_above_cap(self):
        handler = MaxEventsExceededHandler()
        ctx = _make_ctx(
            WinCondition(type="max_events_exceeded", type_config={"max_events": 10}),
            _make_scores(["a", "b"]),
            game_state=GameState(event_counter=15),
        )
        result = await handler.check(ctx)
        assert result is not None

    async def test_zero_cap_disables_handler(self):
        handler = MaxEventsExceededHandler()
        ctx = _make_ctx(
            WinCondition(type="max_events_exceeded", type_config={"max_events": 0}),
            _make_scores(["a", "b"]),
            game_state=GameState(event_counter=100),
        )
        assert await handler.check(ctx) is None


class TestAllBudgetsExhaustedHandler:
    """Fires when every game player is in exhausted_players set."""

    async def test_no_exhausted_players(self):
        handler = AllBudgetsExhaustedHandler()
        ctx = _make_ctx(
            WinCondition(type="all_budgets_exhausted"),
            _make_scores(["a", "b"]),
            exhausted=set(),
        )
        assert await handler.check(ctx) is None

    async def test_partial_exhaustion_does_not_fire(self):
        handler = AllBudgetsExhaustedHandler()
        ctx = _make_ctx(
            WinCondition(type="all_budgets_exhausted"),
            _make_scores(["a", "b"]),
            exhausted={"a"},
        )
        assert await handler.check(ctx) is None

    async def test_full_exhaustion_fires(self):
        handler = AllBudgetsExhaustedHandler()
        ctx = _make_ctx(
            WinCondition(type="all_budgets_exhausted"),
            _make_scores(["a", "b"]),
            exhausted={"a", "b"},
        )
        result = await handler.check(ctx)
        assert result is not None
        assert result.reason == "all_budgets_exhausted"
        assert result.winner is None

    async def test_no_scores_no_fire(self):
        """Empty scores map — can't say everyone is exhausted if there's nobody."""
        handler = AllBudgetsExhaustedHandler()
        ctx = _make_ctx(
            WinCondition(type="all_budgets_exhausted"),
            {},
            exhausted=set(),
        )
        assert await handler.check(ctx) is None


class TestScoreThresholdHandler:
    """Competitive-mode: winner is first player whose metric >= threshold."""

    async def test_no_crossers(self):
        handler = ScoreThresholdHandler()
        ctx = _make_ctx(
            WinCondition(type="score_threshold", metric="total_points", threshold=100.0),
            _make_scores(["a", "b"], {"a": 40.0, "b": 50.0}),
        )
        assert await handler.check(ctx) is None

    async def test_single_crosser_wins(self):
        handler = ScoreThresholdHandler()
        ctx = _make_ctx(
            WinCondition(type="score_threshold", metric="total_points", threshold=80.0),
            _make_scores(["a", "b"], {"a": 85.0, "b": 50.0}),
        )
        result = await handler.check(ctx)
        assert result is not None
        assert result.winner == "a"
        assert result.reason == "score_threshold"

    async def test_multiple_crossers_highest_wins(self):
        handler = ScoreThresholdHandler()
        ctx = _make_ctx(
            WinCondition(type="score_threshold", metric="total_points", threshold=70.0),
            _make_scores(["a", "b", "c"], {"a": 75.0, "b": 95.0, "c": 85.0}),
        )
        result = await handler.check(ctx)
        assert result is not None
        assert result.winner == "b"  # highest

    async def test_eliminated_player_skipped(self):
        handler = ScoreThresholdHandler()
        scores = _make_scores(["a", "b"], {"a": 100.0, "b": 50.0})
        scores["a"].eliminated = True
        ctx = _make_ctx(
            WinCondition(type="score_threshold", metric="total_points", threshold=80.0),
            scores,
        )
        # 'a' is eliminated so not counted; 'b' is below threshold
        assert await handler.check(ctx) is None


class TestEliminationHandler:
    """Eliminate players below threshold; last standing wins."""

    async def test_nobody_below_threshold(self):
        handler = EliminationHandler()
        ctx = _make_ctx(
            WinCondition(type="elimination", metric="total_points", threshold=10.0, below=True),
            _make_scores(["a", "b"], {"a": 50.0, "b": 40.0}),
        )
        assert await handler.check(ctx) is None

    async def test_one_eliminated_other_wins(self):
        handler = EliminationHandler()
        scores = _make_scores(["a", "b"], {"a": 50.0, "b": 5.0})
        ctx = _make_ctx(
            WinCondition(type="elimination", metric="total_points", threshold=10.0, below=True),
            scores,
            game_state=GameState(event_counter=7),
        )
        result = await handler.check(ctx)
        assert result is not None
        assert result.winner == "a"
        assert result.reason == "last_standing"
        assert scores["b"].eliminated is True
        assert scores["b"].eliminated_at_event == 7


class TestWinConditionEvaluator:
    """The orchestrator-facing evaluator that runs handlers in order."""

    async def test_empty_conditions_returns_none(self):
        ev = WinConditionEvaluator([], scoring_mode="behavioral")
        result = await ev.check(
            _make_scores(["a", "b"]),
            GameState(),
            AsyncMock(query_entities=AsyncMock(return_value=[])),
        )
        assert result is None

    async def test_behavioral_mode_filters_out_score_threshold(self, caplog):
        """Competitive-only handlers are stripped at construction in behavioral mode."""
        conditions = [
            WinCondition(type="score_threshold", metric="total_points", threshold=10.0),
            WinCondition(type="deal_closed"),
        ]
        ev = WinConditionEvaluator(conditions, scoring_mode="behavioral")
        # score_threshold would fire (everyone crosses zero) but it's filtered out.
        state = AsyncMock()
        state.query_entities = AsyncMock(return_value=[])
        result = await ev.check(
            _make_scores(["a"], {"a": 100.0}),
            GameState(),
            state,
        )
        assert result is None  # score_threshold filtered; deal_closed returned None

    async def test_competitive_mode_keeps_score_threshold(self):
        """In competitive mode, score_threshold handler IS active."""
        conditions = [
            WinCondition(type="score_threshold", metric="total_points", threshold=80.0),
        ]
        ev = WinConditionEvaluator(conditions, scoring_mode="competitive")
        state = AsyncMock()
        state.query_entities = AsyncMock(return_value=[])
        result = await ev.check(
            _make_scores(["a", "b"], {"a": 85.0, "b": 50.0}),
            GameState(),
            state,
        )
        assert result is not None
        assert result.winner == "a"

    async def test_first_match_wins(self):
        """Multiple conditions — evaluator returns the first match."""
        conditions = [
            WinCondition(type="deal_closed"),
            WinCondition(type="max_events_exceeded", type_config={"max_events": 5}),
        ]
        ev = WinConditionEvaluator(conditions, scoring_mode="behavioral")
        state = AsyncMock()
        state.query_entities = AsyncMock(return_value=[{"id": "d1", "status": "accepted"}])
        result = await ev.check(
            _make_scores(["a", "b"], {"a": 80.0}),
            GameState(event_counter=10),  # would also trip max_events
            state,
        )
        assert result is not None
        # deal_closed declared first; returned first
        assert result.reason == "deal_closed"

    async def test_unknown_condition_type_is_skipped(self, caplog):
        conditions = [WinCondition(type="some_unknown_thing")]
        ev = WinConditionEvaluator(conditions, scoring_mode="behavioral")
        state = AsyncMock()
        state.query_entities = AsyncMock(return_value=[])
        result = await ev.check(_make_scores(["a"]), GameState(), state)
        assert result is None


class TestRegistryRegistration:
    """Smoke check the handler registry covers all expected types."""

    def test_registry_contains_all_new_types(self):
        expected = {
            "deal_closed",
            "deal_rejected",
            "stalemate_timeout",
            "wall_clock_elapsed",
            "max_events_exceeded",
            "all_budgets_exhausted",
            "score_threshold",
            "elimination",
        }
        assert set(WIN_CONDITION_HANDLER_REGISTRY.keys()) == expected
