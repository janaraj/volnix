"""Tests for GameOrchestrator lifecycle, event handling, and termination paths.

Covers:
- ``_on_initialize``: wires state + agency dependencies; validates Protocol
- ``configure``: selects scorer by mode, builds win-evaluator, initializes player scores
- ``_on_start``: subscribes to GAME_TOOL_EVENT_TYPES, starts failsafes, activates first mover
- ``_handle_game_event``: scores, publishes updates, checks win, activates next player
- ``_next_player_for``: serial/parallel mode routing
- ``_terminate_natural`` (Path A): publishes events without calling settle
- ``_handle_timeout`` (Path B): queries open deals, calls settle, publishes terminated
- ``_on_stop``: cancels tasks, resolves future
- ``await_result``: blocks until future resolved
- ``_resolve_first_mover``: role prefix / exact match / fallback
- ``_build_state_summary``: compact deal summary

Failsafe timer tests (wall_clock / stalemate / all_budgets / idempotency) live in
``test_failsafes.py``.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from volnix.core.events import WorldEvent
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
    PlayerScore,
    WinCondition,
    WinResult,
)
from volnix.engines.game.events import (
    GameActiveStateChangedEvent,
    GameKickstartEvent,
    GameTerminatedEvent,
)
from volnix.engines.game.orchestrator import (
    GAME_TOOL_EVENT_TYPES,
    GameOrchestrator,
    _serialize_standings,
)
from volnix.engines.game.scorers.behavioral import BehavioralScorer
from volnix.engines.game.scorers.competitive import CompetitiveScorer

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class CannedStateEngine:
    """Minimal state engine mock with recorded query log."""

    def __init__(self, canned: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._canned = canned or {}
        self.queries: list[tuple[str, dict[str, Any] | None]] = []

    async def query_entities(
        self, entity_type: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self.queries.append((entity_type, filters))
        return list(self._canned.get(entity_type, []))


class FakeAgency:
    """Records activate_for_event calls without touching agency internals."""

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
                "max_calls_override": max_calls_override,
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
    bonus_per_event: float = 0.14,
    win_conditions: list[WinCondition] | None = None,
    enabled: bool = True,
) -> GameDefinition:
    return GameDefinition(
        enabled=enabled,
        mode="negotiation",
        scoring_mode=scoring_mode,
        flow=FlowConfig(
            type="event_driven",
            max_wall_clock_seconds=max_wall_clock_seconds,
            max_events=max_events,
            stalemate_timeout_seconds=stalemate_timeout_seconds,
            activation_mode=activation_mode,
            first_mover=first_mover,
            bonus_per_event=bonus_per_event,
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
    run_id: str = "run-test-001",
    configure: bool = True,
) -> tuple[GameOrchestrator, AsyncMock, CannedStateEngine, FakeAgency]:
    """Build an initialized (and optionally configured) orchestrator for tests."""
    o = GameOrchestrator()
    bus = _make_bus()
    state = state_engine or CannedStateEngine()
    agency = agency or FakeAgency()
    o._dependencies = {"state": state, "agency": agency}
    await o.initialize({}, bus)
    if configure:
        await o.configure(
            definition=definition or _make_def(),
            player_actor_ids=player_ids or ["buyer-001", "supplier-001"],
            run_id=run_id,
        )
    return o, bus, state, agency


def _make_committed_event(
    action: str = "negotiate_propose",
    actor_id: str = "buyer-001",
    service_id: str = "game",
    deal_id: str = "deal-q3",
    input_data: dict[str, Any] | None = None,
) -> WorldEvent:
    now = datetime.now(UTC)
    return WorldEvent(
        event_id=EventId(f"evt-{actor_id}-{action}"),
        event_type=f"world.{action}",
        timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
        actor_id=ActorId(actor_id),
        service_id=ServiceId(service_id),
        action=action,
        input_data=input_data or {"deal_id": deal_id},
    )


# ---------------------------------------------------------------------------
# Lifecycle — _on_initialize / configure / _on_start basics
# ---------------------------------------------------------------------------


class TestOnInitialize:
    """Dependency wiring is deferred to _on_start under the Cycle B.9 lifecycle.

    ``wire_engines`` populates ``_dependencies`` AFTER ``_on_initialize``
    returns, so ``_on_initialize`` is tolerant of missing deps. The real
    validation (and hard failures) happen in ``_on_start`` which is
    called AFTER ``inject_dependencies`` has run.

    Tests that pre-populate ``_dependencies`` before ``initialize()``
    (i.e. bypassing ``wire_engines``) still get opportunistic resolution
    at init time — this matches the test harness pattern.
    """

    @pytest.mark.asyncio
    async def test_initialize_resolves_pre_populated_deps(self):
        o = GameOrchestrator()
        bus = _make_bus()
        state = CannedStateEngine()
        agency = FakeAgency()
        o._dependencies = {"state": state, "agency": agency}
        await o.initialize({}, bus)
        # Opportunistic resolution when deps are already present
        assert o._bus is bus
        assert o._state is state
        assert o._agency is agency

    @pytest.mark.asyncio
    async def test_initialize_tolerant_of_missing_state(self):
        """Empty _dependencies at init time is OK (wire_engines path)."""
        o = GameOrchestrator()
        o._dependencies = {}
        await o.initialize({}, _make_bus())
        # State is still None — resolved on _on_start
        assert o._state is None

    @pytest.mark.asyncio
    async def test_on_start_raises_when_state_still_missing(self):
        """_on_start IS the hard-fail point for missing state."""
        o = GameOrchestrator()
        o._dependencies = {}  # never populated
        await o.initialize({}, _make_bus())
        await o.configure(
            _make_def(),
            player_actor_ids=["buyer-001", "supplier-001"],
            run_id="run-test",
        )
        with pytest.raises(RuntimeError, match="state"):
            await o._on_start()

    @pytest.mark.asyncio
    async def test_initialize_without_bus_raises(self):
        """Missing bus is always a hard error — the bus is mandatory."""
        o = GameOrchestrator()
        o._dependencies = {"state": CannedStateEngine(), "agency": FakeAgency()}
        with pytest.raises(RuntimeError, match="bus"):
            await o.initialize({}, None)

    @pytest.mark.asyncio
    async def test_initialize_with_bad_agency_raises(self):
        """Agency must implement AgencyActivationProtocol when present."""
        o = GameOrchestrator()

        class NotAnAgency:
            pass

        o._dependencies = {"state": CannedStateEngine(), "agency": NotAnAgency()}
        with pytest.raises(RuntimeError, match="AgencyActivationProtocol"):
            await o.initialize({}, _make_bus())

    @pytest.mark.asyncio
    async def test_initialize_without_agency_does_not_raise(self):
        """Agency may be injected later (before _on_start)."""
        o = GameOrchestrator()
        o._dependencies = {"state": CannedStateEngine()}
        await o.initialize({}, _make_bus())
        assert o._agency is None

    @pytest.mark.asyncio
    async def test_on_start_raises_when_agency_missing_at_configure_time(self):
        """Configured game with no agency → hard fail at _on_start."""
        o = GameOrchestrator()
        o._dependencies = {"state": CannedStateEngine()}
        await o.initialize({}, _make_bus())
        await o.configure(
            _make_def(),
            player_actor_ids=["buyer-001", "supplier-001"],
            run_id="run-test",
        )
        with pytest.raises(RuntimeError, match="agency"):
            await o._on_start()


class TestConfigure:
    """configure() binds definition, scorer, win evaluator, player scores."""

    @pytest.mark.asyncio
    async def test_configure_noop_when_disabled(self):
        o, _, _, _ = await _init_orchestrator(configure=False)
        await o.configure(
            _make_def(enabled=False),
            player_actor_ids=["buyer-001", "supplier-001"],
            run_id="run-disabled",
        )
        assert o._definition is None
        assert o._scorer is None
        assert o._win_evaluator is None

    @pytest.mark.asyncio
    async def test_configure_binds_all_fields(self):
        o, _, _, _ = await _init_orchestrator(configure=False)
        definition = _make_def(scoring_mode="behavioral")
        await o.configure(
            definition=definition,
            player_actor_ids=["buyer-001", "supplier-001"],
            run_id="run-001",
        )
        assert o._definition is definition
        assert o._player_ids == [ActorId("buyer-001"), ActorId("supplier-001")]
        assert o._run_id == "run-001"
        assert set(o._player_scores.keys()) == {"buyer-001", "supplier-001"}
        assert o._win_evaluator is not None

    @pytest.mark.asyncio
    async def test_configure_behavioral_selects_behavioral_scorer(self):
        o, _, _, _ = await _init_orchestrator(configure=False)
        await o.configure(
            _make_def(scoring_mode="behavioral"),
            player_actor_ids=["buyer-001", "supplier-001"],
            run_id="run-b",
        )
        assert isinstance(o._scorer, BehavioralScorer)

    @pytest.mark.asyncio
    async def test_configure_competitive_selects_competitive_scorer(self):
        o, _, _, _ = await _init_orchestrator(configure=False)
        await o.configure(
            _make_def(scoring_mode="competitive", bonus_per_event=0.25),
            player_actor_ids=["buyer-001", "supplier-001"],
            run_id="run-c",
        )
        assert isinstance(o._scorer, CompetitiveScorer)
        # Scorer captured the flow.bonus_per_event
        assert o._scorer._bonus_per_event == 0.25

    @pytest.mark.asyncio
    async def test_configure_resets_runtime_state(self):
        """Re-configuring clears exhausted players, terminated flag, game state."""
        o, _, _, _ = await _init_orchestrator()
        o._terminated = True
        o._exhausted_players = {"buyer-001"}
        o._game_state.event_counter = 42
        await o.configure(
            _make_def(),
            player_actor_ids=["buyer-001", "supplier-001"],
            run_id="run-reset",
        )
        assert o._terminated is False
        assert o._exhausted_players == set()
        assert o._game_state.event_counter == 0


class TestOnStart:
    """_on_start subscribes to bus, starts failsafes, kickstarts first mover."""

    @pytest.mark.asyncio
    async def test_on_start_without_definition_is_noop(self):
        o, bus, _, agency = await _init_orchestrator(configure=False)
        await o._on_start()
        # No subscribe calls, no activation
        assert bus.subscribe.await_count == 0
        assert agency.calls == []

    @pytest.mark.asyncio
    async def test_on_start_subscribes_to_all_game_event_types(self):
        o, bus, _, _ = await _init_orchestrator()
        await o._on_start()
        subscribed_topics = [call.args[0] for call in bus.subscribe.call_args_list]
        for topic in GAME_TOOL_EVENT_TYPES:
            assert topic in subscribed_topics
        assert "budget.exhausted" in subscribed_topics
        assert "game.timeout" in subscribed_topics
        # Cleanup
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_on_start_publishes_active_state_true(self):
        o, bus, _, _ = await _init_orchestrator()
        await o._on_start()
        published_types = [type(call.args[0]).__name__ for call in bus.publish.call_args_list]
        assert "GameActiveStateChangedEvent" in published_types
        assert "GameKickstartEvent" in published_types
        # Find the active state event and confirm active=True
        active_events = [
            call.args[0]
            for call in bus.publish.call_args_list
            if isinstance(call.args[0], GameActiveStateChangedEvent)
        ]
        assert active_events[0].active is True
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_on_start_serial_mode_activates_first_mover_only(self):
        o, _, _, agency = await _init_orchestrator(
            definition=_make_def(
                activation_mode="serial",
                first_mover="buyer",
            ),
            player_ids=["buyer-001", "supplier-001"],
        )
        await o._on_start()
        # Give the fire-and-forget task a chance to run
        await asyncio.sleep(0)
        assert len(agency.calls) == 1
        assert str(agency.calls[0]["actor_id"]) == "buyer-001"
        assert agency.calls[0]["reason"] == "game_kickstart"
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_on_start_parallel_mode_activates_all_players(self):
        o, _, _, agency = await _init_orchestrator(
            definition=_make_def(activation_mode="parallel"),
            player_ids=["buyer-001", "supplier-001", "mediator-001"],
        )
        await o._on_start()
        await asyncio.sleep(0)
        assert len(agency.calls) == 3
        activated_ids = {str(c["actor_id"]) for c in agency.calls}
        assert activated_ids == {"buyer-001", "supplier-001", "mediator-001"}
        assert all(c["reason"] == "game_kickstart" for c in agency.calls)
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_on_start_publishes_kickstart_event_with_metadata(self):
        o, bus, _, _ = await _init_orchestrator(
            definition=_make_def(first_mover="buyer"),
            player_ids=["buyer-001", "supplier-001"],
            run_id="run-kickstart-123",
        )
        await o._on_start()
        kickstart = [
            call.args[0]
            for call in bus.publish.call_args_list
            if isinstance(call.args[0], GameKickstartEvent)
        ]
        assert len(kickstart) == 1
        assert kickstart[0].run_id == "run-kickstart-123"
        assert kickstart[0].first_mover == "buyer-001"
        assert kickstart[0].num_players == 2
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_on_start_creates_result_future(self):
        o, _, _, _ = await _init_orchestrator()
        assert o._result_future is None
        await o._on_start()
        assert o._result_future is not None
        assert not o._result_future.done()
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_on_start_records_started_at(self):
        o, _, _, _ = await _init_orchestrator()
        before = datetime.now(UTC)
        await o._on_start()
        assert o._game_state.started_at is not None
        assert o._game_state.started_at >= before
        await o._on_stop()


# ---------------------------------------------------------------------------
# _resolve_first_mover
# ---------------------------------------------------------------------------


class TestResolveFirstMover:
    """_resolve_first_mover handles role prefix, exact match, fallback."""

    @pytest.mark.asyncio
    async def test_matches_role_prefix(self):
        o, _, _, _ = await _init_orchestrator(
            definition=_make_def(first_mover="buyer"),
            player_ids=["buyer-001", "supplier-001"],
        )
        result = o._resolve_first_mover()
        assert str(result) == "buyer-001"

    @pytest.mark.asyncio
    async def test_matches_exact_actor_id(self):
        o, _, _, _ = await _init_orchestrator(
            definition=_make_def(first_mover="supplier-001"),
            player_ids=["buyer-001", "supplier-001"],
        )
        result = o._resolve_first_mover()
        assert str(result) == "supplier-001"

    @pytest.mark.asyncio
    async def test_fallback_to_first_player_when_no_match(self):
        o, _, _, _ = await _init_orchestrator(
            definition=_make_def(first_mover="mediator"),
            player_ids=["buyer-001", "supplier-001"],
        )
        result = o._resolve_first_mover()
        assert str(result) == "buyer-001"

    @pytest.mark.asyncio
    async def test_fallback_to_first_player_when_none(self):
        o, _, _, _ = await _init_orchestrator(
            definition=_make_def(first_mover=None),
            player_ids=["buyer-001", "supplier-001"],
        )
        result = o._resolve_first_mover()
        assert str(result) == "buyer-001"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_players(self):
        o, _, _, _ = await _init_orchestrator(configure=False)
        # Manually set an empty player list
        o._definition = _make_def(first_mover="buyer")
        o._player_ids = []
        result = o._resolve_first_mover()
        assert result is None


# ---------------------------------------------------------------------------
# _next_player_for
# ---------------------------------------------------------------------------


class TestNextPlayerFor:
    """_next_player_for routes activation across serial/parallel modes."""

    @pytest.mark.asyncio
    async def test_serial_returns_other_player(self):
        o, _, _, _ = await _init_orchestrator(
            definition=_make_def(activation_mode="serial"),
            player_ids=["buyer-001", "supplier-001"],
        )
        event = _make_committed_event(actor_id="buyer-001")
        next_pid = o._next_player_for(event)
        assert str(next_pid) == "supplier-001"

    @pytest.mark.asyncio
    async def test_serial_returns_none_when_alone(self):
        o, _, _, _ = await _init_orchestrator(player_ids=["buyer-001"])
        event = _make_committed_event(actor_id="buyer-001")
        assert o._next_player_for(event) is None

    @pytest.mark.asyncio
    async def test_parallel_returns_none(self):
        o, _, _, _ = await _init_orchestrator(
            definition=_make_def(activation_mode="parallel"),
            player_ids=["buyer-001", "supplier-001"],
        )
        event = _make_committed_event(actor_id="buyer-001")
        assert o._next_player_for(event) is None

    @pytest.mark.asyncio
    async def test_serial_skips_eliminated_player(self):
        o, _, _, _ = await _init_orchestrator(
            player_ids=["buyer-001", "supplier-001", "mediator-001"]
        )
        # Eliminate supplier-001 in place
        o._player_scores["supplier-001"].eliminated = True
        event = _make_committed_event(actor_id="buyer-001")
        # Should skip supplier and return mediator
        next_pid = o._next_player_for(event)
        assert str(next_pid) == "mediator-001"


# ---------------------------------------------------------------------------
# _handle_game_event
# ---------------------------------------------------------------------------


class TestHandleGameEvent:
    """_handle_game_event scores + publishes + checks win + reactivates."""

    @pytest.mark.asyncio
    async def test_ignores_non_world_event(self):
        o, _, _, _ = await _init_orchestrator()
        await o._on_start()
        # An Event (not a WorldEvent) should be ignored
        from volnix.core.events import Event

        now = datetime.now(UTC)
        fake_event = Event(
            event_type="unrelated",
            timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
        )
        await o._handle_game_event(fake_event)
        assert o._game_state.event_counter == 0
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_ignores_non_game_service_event(self):
        o, _, _, _ = await _init_orchestrator()
        await o._on_start()
        event = _make_committed_event(service_id="slack", action="chat.postMessage")
        await o._handle_game_event(event)
        assert o._game_state.event_counter == 0
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_noop_when_terminated(self):
        o, _, _, _ = await _init_orchestrator()
        o._terminated = True
        event = _make_committed_event()
        await o._handle_game_event(event)
        assert o._game_state.event_counter == 0

    @pytest.mark.asyncio
    async def test_increments_event_counter(self):
        o, _, _, _ = await _init_orchestrator()
        await o._on_start()
        event = _make_committed_event()
        await o._handle_game_event(event)
        assert o._game_state.event_counter == 1
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_refreshes_stalemate_deadline(self):
        o, _, _, _ = await _init_orchestrator()
        await o._on_start()
        deadline_before = o._game_state.stalemate_deadline_tick
        await asyncio.sleep(0.02)
        await o._handle_game_event(_make_committed_event())
        assert o._game_state.stalemate_deadline_tick > deadline_before
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_publishes_score_updates_for_all_players(self):
        o, bus, _, _ = await _init_orchestrator()
        await o._on_start()
        bus.publish.reset_mock()
        await o._handle_game_event(_make_committed_event())
        # Should publish one GameScoreUpdatedEvent per player
        from volnix.engines.game.events import GameScoreUpdatedEvent

        score_updates = [
            call.args[0]
            for call in bus.publish.call_args_list
            if isinstance(call.args[0], GameScoreUpdatedEvent)
        ]
        assert len(score_updates) == 2  # two players
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_serial_mode_activates_next_player(self):
        o, _, _, agency = await _init_orchestrator(
            definition=_make_def(activation_mode="serial"),
            player_ids=["buyer-001", "supplier-001"],
        )
        await o._on_start()
        # Let the kickstart activation task run before clearing
        await asyncio.sleep(0)
        agency.calls.clear()
        event = _make_committed_event(actor_id="buyer-001")
        await o._handle_game_event(event)
        await asyncio.sleep(0)
        assert len(agency.calls) == 1
        assert str(agency.calls[0]["actor_id"]) == "supplier-001"
        assert agency.calls[0]["reason"] == "game_event"
        assert agency.calls[0]["trigger_event"] is event
        # State summary injected
        assert agency.calls[0]["state_summary"] is not None
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_parallel_mode_does_not_reactivate(self):
        o, _, _, agency = await _init_orchestrator(
            definition=_make_def(activation_mode="parallel"),
            player_ids=["buyer-001", "supplier-001"],
        )
        await o._on_start()
        await asyncio.sleep(0)
        agency.calls.clear()
        await o._handle_game_event(_make_committed_event(actor_id="buyer-001"))
        await asyncio.sleep(0)
        # No re-activation in parallel mode
        assert agency.calls == []
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_natural_win_terminates(self):
        """Deal closed → _terminate_natural runs → future resolved."""
        # State engine returns an accepted deal so DealClosedHandler fires
        state = CannedStateEngine(
            {
                "negotiation_deal": [
                    {"id": "deal-q3", "status": "accepted", "parties": ["buyer", "supplier"]}
                ]
            }
        )
        o, bus, _, agency = await _init_orchestrator(state_engine=state)
        await o._on_start()
        await asyncio.sleep(0)
        agency.calls.clear()
        bus.publish.reset_mock()

        await o._handle_game_event(_make_committed_event(actor_id="buyer-001"))

        assert o._terminated is True
        # GameTerminatedEvent published
        terminated_events = [
            call.args[0]
            for call in bus.publish.call_args_list
            if isinstance(call.args[0], GameTerminatedEvent)
        ]
        assert len(terminated_events) == 1
        assert terminated_events[0].reason == "deal_closed"
        assert o._result_future is not None and o._result_future.done()

    @pytest.mark.asyncio
    async def test_scorer_exception_is_logged_not_raised(self):
        """If the scorer raises, the orchestrator logs and continues."""
        o, _, _, _ = await _init_orchestrator()
        await o._on_start()

        class BrokenScorer:
            async def score_event(self, ctx):
                raise RuntimeError("scorer blew up")

            async def settle(self, **kwargs):
                return None

        o._scorer = BrokenScorer()  # type: ignore[assignment]
        # Should not raise
        await o._handle_game_event(_make_committed_event())
        assert o._game_state.event_counter == 1
        await o._on_stop()


# ---------------------------------------------------------------------------
# Path A termination (natural win)
# ---------------------------------------------------------------------------


class TestTerminateNatural:
    """_terminate_natural publishes events + resolves future, no settlement."""

    @pytest.mark.asyncio
    async def test_natural_win_publishes_active_false_and_terminated(self):
        o, bus, _, _ = await _init_orchestrator()
        await o._on_start()
        bus.publish.reset_mock()

        win = WinResult(
            winner=ActorId("buyer-001"),
            reason="deal_closed",
            final_standings=[{"actor_id": "buyer-001", "total_score": 42.0}],
        )
        await o._terminate_natural(win)

        # Active state flipped to False
        active_events = [
            call.args[0]
            for call in bus.publish.call_args_list
            if isinstance(call.args[0], GameActiveStateChangedEvent)
        ]
        assert active_events
        assert active_events[-1].active is False

        # GameTerminatedEvent published with winner
        terminated_events = [
            call.args[0]
            for call in bus.publish.call_args_list
            if isinstance(call.args[0], GameTerminatedEvent)
        ]
        assert len(terminated_events) == 1
        assert terminated_events[0].reason == "deal_closed"
        assert terminated_events[0].winner == ActorId("buyer-001")

    @pytest.mark.asyncio
    async def test_natural_win_resolves_result_future(self):
        o, _, _, _ = await _init_orchestrator()
        await o._on_start()
        await o._terminate_natural(WinResult(winner=ActorId("buyer-001"), reason="deal_closed"))
        assert o._result_future is not None
        result = await o._result_future
        assert result.winner == ActorId("buyer-001")
        assert result.reason == "deal_closed"
        assert result.scoring_mode == "behavioral"

    @pytest.mark.asyncio
    async def test_natural_win_does_not_call_settle(self):
        """Path A skips settlement — scorer.settle is never called."""
        o, _, _, _ = await _init_orchestrator()
        await o._on_start()

        settle_called = asyncio.Event()

        class WatcherScorer(BehavioralScorer):
            async def settle(self, **kwargs):
                settle_called.set()

        o._scorer = WatcherScorer()
        await o._terminate_natural(WinResult(reason="deal_closed"))
        assert not settle_called.is_set()

    @pytest.mark.asyncio
    async def test_natural_win_cancels_failsafes(self):
        o, _, _, _ = await _init_orchestrator()
        await o._on_start()
        wall = o._wall_clock_task
        stale = o._stalemate_task
        assert wall is not None and not wall.done()
        assert stale is not None and not stale.done()

        await o._terminate_natural(WinResult(reason="deal_closed"))
        # Give cancellation a chance to propagate
        await asyncio.sleep(0)
        assert wall.done()
        assert stale.done()

    @pytest.mark.asyncio
    async def test_natural_win_idempotent(self):
        """Calling _terminate_natural twice is a no-op on the second call."""
        o, bus, _, _ = await _init_orchestrator()
        await o._on_start()
        await o._terminate_natural(WinResult(reason="deal_closed"))
        # Record publish count after first termination
        first_count = bus.publish.await_count
        # Second call should not re-publish
        await o._terminate_natural(WinResult(reason="deal_closed"))
        assert bus.publish.await_count == first_count


# ---------------------------------------------------------------------------
# Path B termination (timeout)
# ---------------------------------------------------------------------------


class TestHandleTimeout:
    """_handle_timeout queries open deals, calls settle, publishes events."""

    @pytest.mark.asyncio
    async def test_timeout_queries_negotiation_deal(self):
        state = CannedStateEngine(
            {
                "negotiation_deal": [
                    {"id": "deal-q3", "status": "proposed", "parties": ["buyer", "supplier"]}
                ]
            }
        )
        o, _, _, _ = await _init_orchestrator(state_engine=state)
        await o._on_start()

        from volnix.engines.game.events import GameTimeoutEvent

        now = datetime.now(UTC)
        timeout_event = GameTimeoutEvent(
            event_id=EventId("evt-timeout"),
            event_type="game.timeout",
            timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
            reason="wall_clock",
        )
        await o._handle_timeout(timeout_event)

        # State was queried for negotiation_deal
        assert any(q[0] == "negotiation_deal" for q in state.queries)

    @pytest.mark.asyncio
    async def test_timeout_filters_to_open_deals(self):
        """Settle receives only deals with status in {open, proposed, countered}.

        Note: this test uses only non-closed deal statuses because M2
        (B-cleanup.3) added a natural-win priority check at the top of
        ``_handle_timeout``. An ``accepted`` or ``rejected`` deal would
        trigger the natural-win path via ``DealClosedHandler`` /
        ``DealRejectedHandler`` and delegate to ``_terminate_natural``,
        skipping settlement entirely. The ``countered`` status is also
        passed through to settle.
        """
        state = CannedStateEngine(
            {
                "negotiation_deal": [
                    {"id": "deal-a", "status": "open", "parties": ["buyer", "supplier"]},
                    {"id": "deal-b", "status": "proposed", "parties": ["buyer", "supplier"]},
                    {"id": "deal-c", "status": "countered", "parties": ["buyer", "supplier"]},
                    {
                        "id": "deal-d",
                        "status": "random_unknown",
                        "parties": ["buyer", "supplier"],
                    },
                ]
            }
        )
        o, _, _, _ = await _init_orchestrator(state_engine=state)
        await o._on_start()

        captured_open_deals: list[list[dict[str, Any]]] = []

        class CapturingScorer(BehavioralScorer):
            async def settle(self, open_deals, state_engine, player_scores, definition):
                captured_open_deals.append(list(open_deals))

        o._scorer = CapturingScorer()

        from volnix.engines.game.events import GameTimeoutEvent

        now = datetime.now(UTC)
        await o._handle_timeout(
            GameTimeoutEvent(
                event_id=EventId("evt-timeout"),
                event_type="game.timeout",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                reason="stalemate",
            )
        )
        assert len(captured_open_deals) == 1
        deal_ids = {d["id"] for d in captured_open_deals[0]}
        # open + proposed + countered pass through; random_unknown is filtered
        assert deal_ids == {"deal-a", "deal-b", "deal-c"}

    @pytest.mark.asyncio
    async def test_timeout_publishes_game_terminated_with_reason(self):
        o, bus, _, _ = await _init_orchestrator()
        await o._on_start()
        bus.publish.reset_mock()

        from volnix.engines.game.events import GameTimeoutEvent

        now = datetime.now(UTC)
        await o._handle_timeout(
            GameTimeoutEvent(
                event_id=EventId("evt-timeout"),
                event_type="game.timeout",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                reason="wall_clock",
            )
        )
        terminated_events = [
            call.args[0]
            for call in bus.publish.call_args_list
            if isinstance(call.args[0], GameTerminatedEvent)
        ]
        assert len(terminated_events) == 1
        assert terminated_events[0].reason == "wall_clock"
        assert terminated_events[0].winner is None

    @pytest.mark.asyncio
    async def test_timeout_resolves_result_future(self):
        o, _, _, _ = await _init_orchestrator()
        await o._on_start()

        from volnix.engines.game.events import GameTimeoutEvent

        now = datetime.now(UTC)
        await o._handle_timeout(
            GameTimeoutEvent(
                event_id=EventId("evt-timeout"),
                event_type="game.timeout",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                reason="stalemate",
            )
        )
        result = await o._result_future  # type: ignore[misc]
        assert result.reason == "stalemate"
        assert result.winner is None

    @pytest.mark.asyncio
    async def test_timeout_idempotent(self):
        """Two back-to-back timeout events produce one terminated event."""
        o, bus, _, _ = await _init_orchestrator()
        await o._on_start()

        from volnix.engines.game.events import GameTimeoutEvent

        now = datetime.now(UTC)
        timeout_event = GameTimeoutEvent(
            event_id=EventId("evt-timeout"),
            event_type="game.timeout",
            timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
            reason="wall_clock",
        )
        await o._handle_timeout(timeout_event)
        first_count = sum(
            1
            for call in bus.publish.call_args_list
            if isinstance(call.args[0], GameTerminatedEvent)
        )
        # Second call should be a noop
        await o._handle_timeout(timeout_event)
        second_count = sum(
            1
            for call in bus.publish.call_args_list
            if isinstance(call.args[0], GameTerminatedEvent)
        )
        assert first_count == 1
        assert second_count == 1

    @pytest.mark.asyncio
    async def test_scorer_settle_exception_is_logged_not_raised(self):
        """If settle raises, the orchestrator still terminates cleanly."""
        o, _, _, _ = await _init_orchestrator()
        await o._on_start()

        class BrokenScorer:
            async def score_event(self, ctx):
                return None

            async def settle(self, **kwargs):
                raise RuntimeError("settle blew up")

        o._scorer = BrokenScorer()  # type: ignore[assignment]

        from volnix.engines.game.events import GameTimeoutEvent

        now = datetime.now(UTC)
        await o._handle_timeout(
            GameTimeoutEvent(
                event_id=EventId("evt-timeout"),
                event_type="game.timeout",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                reason="stalemate",
            )
        )
        assert o._terminated is True
        assert o._result_future is not None and o._result_future.done()


# ---------------------------------------------------------------------------
# M3 (B-cleanup.3): direct gate.set_active defense-in-depth
# ---------------------------------------------------------------------------


class TestGateFlipDirectInjection:
    """_publish_active_state calls ``gate.set_active`` directly AND via bus.

    M3 (B-cleanup.3): the orchestrator's gate flip used to rely
    exclusively on ``game.active_state_changed`` bus delivery to reach
    the :class:`GameActivePolicy` subscriber. That delivery path is
    correct-by-FIFO-ready-ordering but fragile — any future reorder
    could break it. B-cleanup.3 adds a direct injected-reference call
    to ``gate.set_active`` as the primary mechanism so the flag flips
    synchronously inside the same coroutine, with the bus publish as
    a secondary fan-out for other subscribers.
    """

    @pytest.mark.asyncio
    async def test_publish_active_state_calls_gate_set_active_directly(self):
        from volnix.engines.policy.builtin.game_active import GameActivePolicy

        o, _, _, _ = await _init_orchestrator()
        gate = GameActivePolicy()
        o._dependencies["game_active_gate"] = gate

        # Gate starts inactive
        assert gate.is_active is False

        await o._publish_active_state(active=True)
        # Gate flipped SYNCHRONOUSLY via the direct call (not via bus)
        assert gate.is_active is True

        await o._publish_active_state(active=False)
        assert gate.is_active is False

    @pytest.mark.asyncio
    async def test_publish_active_state_still_emits_bus_event(self):
        """Secondary mechanism: bus event is still published for other subscribers."""
        from volnix.engines.policy.builtin.game_active import GameActivePolicy

        o, bus, _, _ = await _init_orchestrator()
        o._dependencies["game_active_gate"] = GameActivePolicy()
        bus.publish.reset_mock()

        await o._publish_active_state(active=True)

        state_events = [
            call.args[0]
            for call in bus.publish.call_args_list
            if isinstance(call.args[0], GameActiveStateChangedEvent)
        ]
        assert len(state_events) == 1
        assert state_events[0].active is True

    @pytest.mark.asyncio
    async def test_publish_active_state_works_without_injected_gate(self):
        """Absence of the gate dep is not fatal — bus is still the fallback."""
        o, bus, _, _ = await _init_orchestrator()
        # Explicitly ensure the gate is not injected
        o._dependencies.pop("game_active_gate", None)
        bus.publish.reset_mock()

        await o._publish_active_state(active=True)
        # Bus event is still published (GameActivePolicy would flip via bus)
        state_events = [
            call.args[0]
            for call in bus.publish.call_args_list
            if isinstance(call.args[0], GameActiveStateChangedEvent)
        ]
        assert len(state_events) == 1


# ---------------------------------------------------------------------------
# M2 (B-cleanup.3): natural-win priority in _handle_timeout
# ---------------------------------------------------------------------------


class TestNaturalWinPriorityOnTimeout:
    """When a timeout event arrives but a natural win is already met.

    M2 (B-cleanup.3): if a ``world.negotiate_accept`` commits and a
    wall-clock / stalemate timer fires on different bus consumer tasks
    in the same event-loop tick, the orchestrator's ``_handle_timeout``
    must check win conditions first and delegate to
    ``_terminate_natural`` with the deal_closed reason — otherwise the
    game misreports the real outcome as a timeout.
    """

    @pytest.mark.asyncio
    async def test_timeout_with_accepted_deal_reports_deal_closed(self):
        """An accepted deal at timeout time → reason='deal_closed', not the timeout reason."""
        state = CannedStateEngine(
            {
                "negotiation_deal": [
                    {
                        "id": "deal-q3",
                        "status": "accepted",  # natural win condition met
                        "parties": ["buyer", "supplier"],
                    }
                ]
            }
        )
        o, bus, _, _ = await _init_orchestrator(state_engine=state)
        await o._on_start()
        bus.publish.reset_mock()

        from volnix.engines.game.events import GameTimeoutEvent

        now = datetime.now(UTC)
        await o._handle_timeout(
            GameTimeoutEvent(
                event_id=EventId("evt-timeout"),
                event_type="game.timeout",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                reason="wall_clock",  # timeout trying to claim the win
            )
        )

        terminated_events = [
            call.args[0]
            for call in bus.publish.call_args_list
            if isinstance(call.args[0], GameTerminatedEvent)
        ]
        assert len(terminated_events) == 1
        # Reason is the NATURAL win, not the timeout reason
        assert terminated_events[0].reason == "deal_closed"

    @pytest.mark.asyncio
    async def test_timeout_with_rejected_deal_reports_deal_rejected(self):
        """Same pattern for the rejected-deal natural-win path."""
        state = CannedStateEngine(
            {
                "negotiation_deal": [
                    {
                        "id": "deal-q3",
                        "status": "rejected",
                        "parties": ["buyer", "supplier"],
                    }
                ]
            }
        )
        # Must register ``deal_rejected`` win condition explicitly
        # (_make_def's default only registers ``deal_closed``).
        o, bus, _, _ = await _init_orchestrator(
            state_engine=state,
            definition=_make_def(
                win_conditions=[
                    WinCondition(type="deal_closed"),
                    WinCondition(type="deal_rejected"),
                ]
            ),
        )
        await o._on_start()
        bus.publish.reset_mock()

        from volnix.engines.game.events import GameTimeoutEvent

        now = datetime.now(UTC)
        await o._handle_timeout(
            GameTimeoutEvent(
                event_id=EventId("evt-timeout"),
                event_type="game.timeout",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                reason="stalemate",
            )
        )
        terminated_events = [
            call.args[0]
            for call in bus.publish.call_args_list
            if isinstance(call.args[0], GameTerminatedEvent)
        ]
        assert len(terminated_events) == 1
        assert terminated_events[0].reason == "deal_rejected"

    @pytest.mark.asyncio
    async def test_timeout_without_natural_win_still_reports_timeout_reason(self):
        """When no win condition is met, the timeout reason still wins.

        Regression guard: the M2 priority check must NOT swallow the
        timeout path when there's no actual natural win available.
        """
        state = CannedStateEngine(
            {
                "negotiation_deal": [
                    {
                        "id": "deal-q3",
                        "status": "proposed",  # not yet closed
                        "parties": ["buyer", "supplier"],
                    }
                ]
            }
        )
        o, bus, _, _ = await _init_orchestrator(state_engine=state)
        await o._on_start()
        bus.publish.reset_mock()

        from volnix.engines.game.events import GameTimeoutEvent

        now = datetime.now(UTC)
        await o._handle_timeout(
            GameTimeoutEvent(
                event_id=EventId("evt-timeout"),
                event_type="game.timeout",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                reason="wall_clock",
            )
        )
        terminated_events = [
            call.args[0]
            for call in bus.publish.call_args_list
            if isinstance(call.args[0], GameTerminatedEvent)
        ]
        assert len(terminated_events) == 1
        # Reason IS the timeout reason because no natural win is available
        assert terminated_events[0].reason == "wall_clock"


# ---------------------------------------------------------------------------
# _build_state_summary (MF6)
# ---------------------------------------------------------------------------


class TestBuildStateSummary:
    """_build_state_summary renders a compact deal snapshot."""

    @pytest.mark.asyncio
    async def test_summary_contains_event_counter(self):
        o, _, _, _ = await _init_orchestrator()
        o._game_state.event_counter = 7
        summary = await o._build_state_summary()
        assert "event #7" in summary

    @pytest.mark.asyncio
    async def test_summary_includes_each_deal_status(self):
        state = CannedStateEngine(
            {
                "negotiation_deal": [
                    {
                        "id": "deal-q3",
                        "status": "proposed",
                        "last_proposed_by": "buyer-001",
                        "terms": {"price": 85},
                    },
                ]
            }
        )
        o, _, _, _ = await _init_orchestrator(state_engine=state)
        summary = await o._build_state_summary()
        assert "deal-q3" in summary
        assert "status=proposed" in summary
        assert "last_proposed_by=buyer-001" in summary
        assert "price" in summary

    @pytest.mark.asyncio
    async def test_summary_handles_query_exception(self):
        """If state query raises, return partial summary (no crash)."""

        class BrokenStateEngine:
            async def query_entities(self, *args, **kwargs):
                raise RuntimeError("state engine offline")

        o = GameOrchestrator()
        bus = _make_bus()
        o._dependencies = {"state": BrokenStateEngine(), "agency": FakeAgency()}
        await o.initialize({}, bus)
        await o.configure(
            _make_def(),
            player_actor_ids=["buyer-001", "supplier-001"],
            run_id="run-broken",
        )
        summary = await o._build_state_summary()
        # Still has the header, no crash
        assert "event #" in summary


# ---------------------------------------------------------------------------
# _on_stop
# ---------------------------------------------------------------------------


class TestOnStop:
    """_on_stop cancels tasks, drains activations, resolves future."""

    @pytest.mark.asyncio
    async def test_stop_cancels_failsafe_tasks(self):
        o, _, _, _ = await _init_orchestrator()
        await o._on_start()
        wall = o._wall_clock_task
        stale = o._stalemate_task
        await o._on_stop()
        assert wall is None or wall.done()
        assert stale is None or stale.done()

    @pytest.mark.asyncio
    async def test_stop_resolves_pending_future_with_stopped(self):
        o, _, _, _ = await _init_orchestrator()
        await o._on_start()
        assert o._result_future is not None and not o._result_future.done()
        await o._on_stop()
        assert o._result_future.done()
        result = await o._result_future
        assert result.reason == "stopped"

    @pytest.mark.asyncio
    async def test_stop_does_not_overwrite_resolved_future(self):
        o, _, _, _ = await _init_orchestrator()
        await o._on_start()
        await o._terminate_natural(WinResult(reason="deal_closed"))
        # Future is already resolved
        result = await o._result_future  # type: ignore[misc]
        assert result.reason == "deal_closed"
        # Stop must not replace it
        await o._on_stop()
        result_after = await o._result_future  # type: ignore[misc]
        assert result_after.reason == "deal_closed"

    @pytest.mark.asyncio
    async def test_stop_sets_terminated_flag(self):
        o, _, _, _ = await _init_orchestrator()
        await o._on_start()
        await o._on_stop()
        assert o._terminated is True

    @pytest.mark.asyncio
    async def test_stop_is_safe_without_start(self):
        """Calling stop on an un-started orchestrator doesn't crash."""
        o, _, _, _ = await _init_orchestrator(configure=False)
        # No _on_start called; _result_future is None
        await o._on_stop()  # Should not raise


# ---------------------------------------------------------------------------
# await_result
# ---------------------------------------------------------------------------


class TestAwaitResult:
    """await_result blocks until game_terminated."""

    @pytest.mark.asyncio
    async def test_await_result_raises_before_start(self):
        o, _, _, _ = await _init_orchestrator(configure=False)
        with pytest.raises(RuntimeError, match="result future"):
            await o.await_result()

    @pytest.mark.asyncio
    async def test_await_result_returns_game_result(self):
        o, _, _, _ = await _init_orchestrator()
        await o._on_start()
        await o._terminate_natural(WinResult(winner=ActorId("buyer-001"), reason="deal_closed"))
        result = await o.await_result()
        assert result.winner == ActorId("buyer-001")
        assert result.reason == "deal_closed"


# ---------------------------------------------------------------------------
# _serialize_standings helper
# ---------------------------------------------------------------------------


class TestSerializeStandings:
    """_serialize_standings returns descending-by-score list."""

    def test_standings_ordered_by_total_score_descending(self):
        scores: dict[str, PlayerScore] = {
            "a-001": PlayerScore(actor_id=ActorId("a-001"), total_score=10.0),
            "b-001": PlayerScore(actor_id=ActorId("b-001"), total_score=30.0),
            "c-001": PlayerScore(actor_id=ActorId("c-001"), total_score=20.0),
        }
        result = _serialize_standings(scores)
        assert [r["actor_id"] for r in result] == ["b-001", "c-001", "a-001"]

    def test_standings_include_eliminated_flag(self):
        scores = {
            "a-001": PlayerScore(actor_id=ActorId("a-001"), total_score=5.0, eliminated=True),
        }
        result = _serialize_standings(scores)
        assert result[0]["eliminated"] is True
