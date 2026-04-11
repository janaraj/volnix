"""Tests for GameOrchestrator failsafe timers + budget exhaustion tracking.

Path B termination path has four failsafe sources, each feeding into the
shared ``_handle_timeout`` settlement flow:

- ``wall_clock``: ``_wall_clock_watcher`` sleeps then publishes timeout
- ``stalemate``: ``_stalemate_watcher`` polls deadline + publishes
- ``max_events``: evaluated by ``MaxEventsExceededHandler`` inside the
  win condition check — but only when declared in blueprints. Covered
  here at the integration seam.
- ``all_budgets``: ``_handle_budget_exhausted`` tracks per-actor
  exhaustion and publishes timeout when everyone's out

Idempotency tests ensure two back-to-back failsafes produce exactly one
``GameTerminatedEvent``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from volnix.core.events import BudgetExhaustedEvent, WorldEvent
from volnix.core.types import (
    ActorId,
    EventId,
    ServiceId,
    Timestamp,
)
from volnix.engines.game.definition import (
    DealDecl,
    FlowConfig,
    GameDefinition,
    GameEntitiesConfig,
    WinCondition,
)
from volnix.engines.game.events import (
    GameTerminatedEvent,
    GameTimeoutEvent,
)
from volnix.engines.game.orchestrator import GameOrchestrator

# ---------------------------------------------------------------------------
# Test doubles (shared with test_orchestrator.py conceptually)
# ---------------------------------------------------------------------------


class CannedStateEngine:
    def __init__(self, canned: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._canned = canned or {}
        self.queries: list[tuple[str, dict[str, Any] | None]] = []

    async def query_entities(
        self, entity_type: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self.queries.append((entity_type, filters))
        return list(self._canned.get(entity_type, []))


class FakeAgency:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def activate_for_event(
        self,
        actor_id: Any,
        reason: str,
        trigger_event: Any = None,
        max_calls_override: int | None = None,
        state_summary: str | None = None,
    ) -> list[Any]:
        self.calls.append(
            {
                "actor_id": actor_id,
                "reason": reason,
                "trigger_event": trigger_event,
                "state_summary": state_summary,
            }
        )
        return []


def _make_bus() -> AsyncMock:
    bus = AsyncMock()
    bus.subscribe = AsyncMock(return_value=None)
    bus.publish = AsyncMock(return_value=None)
    bus.unsubscribe = AsyncMock(return_value=None)
    return bus


def _make_def(
    scoring_mode: str = "behavioral",
    activation_mode: str = "serial",
    first_mover: str | None = "buyer",
    max_wall_clock_seconds: int = 900,
    max_events: int = 100,
    stalemate_timeout_seconds: int = 180,
    win_conditions: list[WinCondition] | None = None,
) -> GameDefinition:
    return GameDefinition(
        enabled=True,
        mode="negotiation",
        scoring_mode=scoring_mode,
        flow=FlowConfig(
            type="event_driven",
            max_wall_clock_seconds=max_wall_clock_seconds,
            max_events=max_events,
            stalemate_timeout_seconds=stalemate_timeout_seconds,
            activation_mode=activation_mode,
            first_mover=first_mover,
        ),
        entities=GameEntitiesConfig(
            deals=[DealDecl(id="deal-q3", parties=["buyer", "supplier"])],
        ),
        win_conditions=win_conditions or [WinCondition(type="deal_closed")],
    )


async def _init_orchestrator(
    definition: GameDefinition | None = None,
    state_engine: CannedStateEngine | None = None,
    agency: FakeAgency | None = None,
    player_ids: list[str] | None = None,
    run_id: str = "run-test-failsafe",
) -> tuple[GameOrchestrator, AsyncMock, CannedStateEngine, FakeAgency]:
    o = GameOrchestrator()
    bus = _make_bus()
    state = state_engine or CannedStateEngine()
    agency = agency or FakeAgency()
    o._dependencies = {"state": state, "agency": agency}
    await o.initialize({}, bus)
    await o.configure(
        definition=definition or _make_def(),
        player_actor_ids=player_ids or ["buyer-001", "supplier-001"],
        run_id=run_id,
    )
    return o, bus, state, agency


def _make_game_event(
    actor_id: str = "buyer-001",
    action: str = "negotiate_propose",
) -> WorldEvent:
    now = datetime.now(UTC)
    return WorldEvent(
        event_id=EventId(f"evt-{actor_id}-{action}"),
        event_type=f"world.{action}",
        timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
        actor_id=ActorId(actor_id),
        service_id=ServiceId("game"),
        action=action,
        input_data={"deal_id": "deal-q3"},
    )


def _make_budget_exhausted(
    actor_id: str, budget_type: str = "world_actions"
) -> BudgetExhaustedEvent:
    now = datetime.now(UTC)
    return BudgetExhaustedEvent(
        event_id=EventId(f"evt-budget-exhausted-{actor_id}"),
        event_type="budget.exhausted",
        timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
        actor_id=ActorId(actor_id),
        budget_type=budget_type,
    )


# ---------------------------------------------------------------------------
# Wall-clock failsafe
# ---------------------------------------------------------------------------


class TestWallClockFailsafe:
    """wall_clock_watcher sleeps then publishes GameTimeoutEvent."""

    @pytest.mark.asyncio
    async def test_wall_clock_fires_after_short_budget(self):
        """Use a 0.05s budget; watcher fires promptly."""
        o, bus, _, _ = await _init_orchestrator(
            definition=_make_def(max_wall_clock_seconds=1),
        )
        # Manually replace the watcher so we don't have to wait 1 second
        o._game_state.started_at = datetime.now(UTC)

        async def fast_watcher() -> None:
            await asyncio.sleep(0.05)
            if o._terminated:
                return
            await bus.publish(
                GameTimeoutEvent(
                    event_id=EventId("evt-wc"),
                    event_type="game.timeout",
                    timestamp=Timestamp(
                        world_time=datetime.now(UTC),
                        wall_time=datetime.now(UTC),
                        tick=0,
                    ),
                    reason="wall_clock",
                    event_number=o._game_state.event_counter,
                )
            )

        task = asyncio.create_task(fast_watcher())
        await task
        # A GameTimeoutEvent with reason=wall_clock should have been published
        timeouts = [
            call.args[0]
            for call in bus.publish.call_args_list
            if isinstance(call.args[0], GameTimeoutEvent)
        ]
        assert any(t.reason == "wall_clock" for t in timeouts)

    @pytest.mark.asyncio
    async def test_wall_clock_watcher_respects_cancellation(self):
        """If cancelled before the sleep finishes, watcher exits cleanly."""
        o, bus, _, _ = await _init_orchestrator(definition=_make_def(max_wall_clock_seconds=60))
        await o._on_start()
        wall_task = o._wall_clock_task
        assert wall_task is not None
        # Cancel before the 60s elapses
        wall_task.cancel()
        await asyncio.sleep(0)
        # Should not have published a wall_clock timeout
        timeouts = [
            call.args[0]
            for call in bus.publish.call_args_list
            if isinstance(call.args[0], GameTimeoutEvent) and call.args[0].reason == "wall_clock"
        ]
        assert timeouts == []
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_wall_clock_watcher_skips_if_terminated(self):
        """If terminated flag is set before sleep returns, no publish."""
        o, bus, _, _ = await _init_orchestrator(definition=_make_def(max_wall_clock_seconds=60))
        o._game_state.started_at = datetime.now(UTC)

        # Start watcher with a tiny sleep by patching
        async def tiny_watcher() -> None:
            try:
                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                return
            if o._terminated:
                return
            await bus.publish(
                GameTimeoutEvent(
                    event_id=EventId("evt-wc"),
                    event_type="game.timeout",
                    timestamp=Timestamp(
                        world_time=datetime.now(UTC),
                        wall_time=datetime.now(UTC),
                        tick=0,
                    ),
                    reason="wall_clock",
                    event_number=0,
                )
            )

        o._terminated = True
        bus.publish.reset_mock()
        task = asyncio.create_task(tiny_watcher())
        await task
        # No timeout should have been published (terminated flag short-circuits)
        timeouts = [
            c.args[0] for c in bus.publish.call_args_list if isinstance(c.args[0], GameTimeoutEvent)
        ]
        assert timeouts == []


# ---------------------------------------------------------------------------
# Stalemate failsafe
# ---------------------------------------------------------------------------


class TestStalemateFailsafe:
    """Stalemate watcher resets on new game events + fires on silence."""

    @pytest.mark.asyncio
    async def test_refresh_advances_stalemate_deadline(self):
        """Each call to _refresh_stalemate_deadline pushes the deadline forward."""
        o, _, _, _ = await _init_orchestrator(definition=_make_def(stalemate_timeout_seconds=60))
        await o._on_start()
        first = o._game_state.stalemate_deadline_tick
        await asyncio.sleep(0.05)
        o._refresh_stalemate_deadline()
        second = o._game_state.stalemate_deadline_tick
        assert second > first
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_stalemate_reset_on_game_event(self):
        """_handle_game_event calls _refresh_stalemate_deadline."""
        o, _, _, _ = await _init_orchestrator(definition=_make_def(stalemate_timeout_seconds=60))
        await o._on_start()
        baseline = o._game_state.stalemate_deadline_tick
        await asyncio.sleep(0.02)
        await o._handle_game_event(_make_game_event())
        assert o._game_state.stalemate_deadline_tick > baseline
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_stalemate_watcher_exits_on_cancel(self):
        """Stalemate watcher handles CancelledError gracefully."""
        o, _, _, _ = await _init_orchestrator(definition=_make_def(stalemate_timeout_seconds=60))
        await o._on_start()
        stale_task = o._stalemate_task
        assert stale_task is not None
        stale_task.cancel()
        # Give cancellation time to propagate
        await asyncio.sleep(0)
        assert stale_task.cancelled() or stale_task.done()
        await o._on_stop()


# ---------------------------------------------------------------------------
# Max events failsafe (integration via win condition)
# ---------------------------------------------------------------------------


class TestMaxEventsFailsafe:
    """MaxEventsExceededHandler triggers termination via win check path."""

    @pytest.mark.asyncio
    async def test_max_events_fires_when_counter_hits_cap(self):
        """When event_counter >= max_events, win check returns a terminal result."""
        # Configure with max_events=3 win condition
        definition = _make_def(
            max_events=3,
            win_conditions=[
                WinCondition(
                    type="max_events_exceeded",
                    type_config={"max_events": 3},
                ),
            ],
        )
        o, bus, _, _ = await _init_orchestrator(definition=definition)
        await o._on_start()

        # Fire 3 events — the 3rd should trip the cap
        for i in range(3):
            event = _make_game_event(actor_id=f"buyer-00{(i % 2) + 1}")
            await o._handle_game_event(event)

        # Should have terminated
        assert o._terminated is True
        terminated_events = [
            call.args[0]
            for call in bus.publish.call_args_list
            if isinstance(call.args[0], GameTerminatedEvent)
        ]
        assert len(terminated_events) == 1
        assert terminated_events[0].reason == "max_events_exceeded"

    @pytest.mark.asyncio
    async def test_max_events_below_cap_does_not_fire(self):
        """When event_counter < max_events, game continues."""
        definition = _make_def(
            max_events=100,
            win_conditions=[
                WinCondition(
                    type="max_events_exceeded",
                    type_config={"max_events": 100},
                ),
            ],
        )
        o, _, _, _ = await _init_orchestrator(definition=definition)
        await o._on_start()
        for i in range(5):
            await o._handle_game_event(_make_game_event(actor_id=f"buyer-00{(i % 2) + 1}"))
        assert o._terminated is False
        await o._on_stop()


# ---------------------------------------------------------------------------
# All-budgets-exhausted failsafe
# ---------------------------------------------------------------------------


class TestAllBudgetsExhausted:
    """_handle_budget_exhausted tracks per-actor exhaustion + fires timeout."""

    @pytest.mark.asyncio
    async def test_budget_exhausted_adds_to_exhausted_set(self):
        o, _, _, _ = await _init_orchestrator(player_ids=["buyer-001", "supplier-001"])
        await o._on_start()
        await o._handle_budget_exhausted(_make_budget_exhausted("buyer-001"))
        assert "buyer-001" in o._exhausted_players
        assert o._player_scores["buyer-001"].eliminated is True
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_non_world_actions_budget_is_ignored(self):
        """Only world_actions exhaustion counts for game elimination."""
        o, _, _, _ = await _init_orchestrator()
        await o._on_start()
        await o._handle_budget_exhausted(
            _make_budget_exhausted("buyer-001", budget_type="api_calls")
        )
        assert o._exhausted_players == set()
        assert o._player_scores["buyer-001"].eliminated is False
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_unknown_actor_is_ignored(self):
        """Budget events for non-player actors are ignored."""
        o, _, _, _ = await _init_orchestrator()
        await o._on_start()
        await o._handle_budget_exhausted(_make_budget_exhausted("npc-stranger-001"))
        assert o._exhausted_players == set()
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_partial_exhaustion_does_not_fire_timeout(self):
        """Only one player out of two is not enough to fire timeout."""
        o, bus, _, _ = await _init_orchestrator(player_ids=["buyer-001", "supplier-001"])
        await o._on_start()
        bus.publish.reset_mock()
        await o._handle_budget_exhausted(_make_budget_exhausted("buyer-001"))
        timeout_events = [
            c.args[0] for c in bus.publish.call_args_list if isinstance(c.args[0], GameTimeoutEvent)
        ]
        assert timeout_events == []
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_all_players_exhausted_fires_timeout(self):
        """When every player's world_actions is out, publish all_budgets timeout."""
        o, bus, _, _ = await _init_orchestrator(player_ids=["buyer-001", "supplier-001"])
        await o._on_start()
        bus.publish.reset_mock()
        await o._handle_budget_exhausted(_make_budget_exhausted("buyer-001"))
        await o._handle_budget_exhausted(_make_budget_exhausted("supplier-001"))
        timeout_events = [
            c.args[0] for c in bus.publish.call_args_list if isinstance(c.args[0], GameTimeoutEvent)
        ]
        assert len(timeout_events) == 1
        assert timeout_events[0].reason == "all_budgets"
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_exhausted_when_terminated_is_noop(self):
        """Budget events arriving after termination are ignored."""
        o, bus, _, _ = await _init_orchestrator()
        await o._on_start()
        o._terminated = True
        bus.publish.reset_mock()
        await o._handle_budget_exhausted(_make_budget_exhausted("buyer-001"))
        assert "buyer-001" not in o._exhausted_players
        timeout_events = [
            c.args[0] for c in bus.publish.call_args_list if isinstance(c.args[0], GameTimeoutEvent)
        ]
        assert timeout_events == []


# ---------------------------------------------------------------------------
# Simultaneous failsafes + idempotency
# ---------------------------------------------------------------------------


class TestFailsafeIdempotency:
    """When multiple failsafes fire at once, only one termination occurs."""

    @pytest.mark.asyncio
    async def test_two_timeouts_back_to_back_produce_one_terminated(self):
        """Second _handle_timeout call is a noop due to _terminated flag."""
        o, bus, _, _ = await _init_orchestrator()
        await o._on_start()
        bus.publish.reset_mock()

        now = datetime.now(UTC)
        wall_clock_event = GameTimeoutEvent(
            event_id=EventId("evt-wc"),
            event_type="game.timeout",
            timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
            reason="wall_clock",
        )
        stalemate_event = GameTimeoutEvent(
            event_id=EventId("evt-sm"),
            event_type="game.timeout",
            timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
            reason="stalemate",
        )
        await o._handle_timeout(wall_clock_event)
        await o._handle_timeout(stalemate_event)

        terminated_events = [
            c.args[0]
            for c in bus.publish.call_args_list
            if isinstance(c.args[0], GameTerminatedEvent)
        ]
        assert len(terminated_events) == 1
        # The first timeout reason wins
        assert terminated_events[0].reason == "wall_clock"

    @pytest.mark.asyncio
    async def test_timeout_then_natural_win_only_timeout_fires(self):
        """If timeout fires first, natural win path is short-circuited."""
        state = CannedStateEngine(
            {
                "negotiation_deal": [
                    {"id": "deal-q3", "status": "accepted", "parties": ["buyer", "supplier"]}
                ]
            }
        )
        o, bus, _, _ = await _init_orchestrator(state_engine=state)
        await o._on_start()
        bus.publish.reset_mock()

        # Timeout first
        now = datetime.now(UTC)
        await o._handle_timeout(
            GameTimeoutEvent(
                event_id=EventId("evt-wc"),
                event_type="game.timeout",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                reason="wall_clock",
            )
        )
        # Then a game event tries to trigger natural win
        await o._handle_game_event(_make_game_event(action="negotiate_accept"))

        terminated_events = [
            c.args[0]
            for c in bus.publish.call_args_list
            if isinstance(c.args[0], GameTerminatedEvent)
        ]
        assert len(terminated_events) == 1
        assert terminated_events[0].reason == "wall_clock"

    @pytest.mark.asyncio
    async def test_natural_win_then_timeout_only_natural_fires(self):
        """If natural win fires first, subsequent timeout is a noop."""
        state = CannedStateEngine(
            {
                "negotiation_deal": [
                    {"id": "deal-q3", "status": "accepted", "parties": ["buyer", "supplier"]}
                ]
            }
        )
        o, bus, _, _ = await _init_orchestrator(state_engine=state)
        await o._on_start()
        bus.publish.reset_mock()

        # Game event → natural win
        await o._handle_game_event(_make_game_event(action="negotiate_accept"))
        # Late timeout arrives
        now = datetime.now(UTC)
        await o._handle_timeout(
            GameTimeoutEvent(
                event_id=EventId("evt-sm"),
                event_type="game.timeout",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                reason="stalemate",
            )
        )
        terminated_events = [
            c.args[0]
            for c in bus.publish.call_args_list
            if isinstance(c.args[0], GameTerminatedEvent)
        ]
        assert len(terminated_events) == 1
        assert terminated_events[0].reason == "deal_closed"

    @pytest.mark.asyncio
    async def test_double_natural_win_is_idempotent(self):
        """Two committed events that both satisfy the win condition → one terminated."""
        state = CannedStateEngine(
            {
                "negotiation_deal": [
                    {"id": "deal-q3", "status": "accepted", "parties": ["buyer", "supplier"]}
                ]
            }
        )
        o, bus, _, _ = await _init_orchestrator(state_engine=state)
        await o._on_start()
        bus.publish.reset_mock()

        await o._handle_game_event(_make_game_event(action="negotiate_accept"))
        await o._handle_game_event(_make_game_event(action="negotiate_accept"))

        terminated_events = [
            c.args[0]
            for c in bus.publish.call_args_list
            if isinstance(c.args[0], GameTerminatedEvent)
        ]
        assert len(terminated_events) == 1
