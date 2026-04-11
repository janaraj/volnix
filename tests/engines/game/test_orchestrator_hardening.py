"""Tests for Cycle B.8.5 hardening fixes — blockers + majors + minors from the review.

Each test maps back to one review finding:

- B1 (agency actor race): lives in test_activate_for_event.py
- B2 (event counter off-by-one on scoring failure): TestCounterStableOnError
- B3 (hardcoded max_activation_messages): lives in test_activate_for_event.py
- M1 (subscription tokens): TestUnsubscribeOnStop
- M2 (error events): TestEngineErrorEvents
- M3 (reactivity window config): lives in test_behavioral_scorer additions
- M4 (ledger lifecycle entries): TestLifecycleLedgerEntries
- M5 (event_id collisions): TestEventIdUniqueness
- m1 (state_summary entity types from config): TestStateSummaryEntityTypes
- m2 (role_to_actor_id map): TestRoleMapResolution
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from volnix.core.events import WorldEvent
from volnix.core.types import ActorId, EventId, ServiceId, Timestamp
from volnix.engines.game.definition import (
    DealDecl,
    FlowConfig,
    GameDefinition,
    GameEntitiesConfig,
    WinCondition,
)
from volnix.engines.game.events import (
    GameEngineErrorEvent,
    GameScoreUpdatedEvent,
    GameTimeoutEvent,
)
from volnix.engines.game.orchestrator import GameOrchestrator

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class CannedStateEngine:
    def __init__(self, canned: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._canned = canned or {}
        self.queries: list[tuple[str, dict[str, Any] | None]] = []
        self.raise_on: set[str] = set()

    async def query_entities(
        self, entity_type: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        self.queries.append((entity_type, filters))
        if entity_type in self.raise_on:
            raise RuntimeError(f"boom on {entity_type}")
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


class RecordingLedger:
    """Minimal ledger that records every append."""

    def __init__(self) -> None:
        self.entries: list[Any] = []
        self.next_id = 1

    async def append(self, entry: Any) -> int:
        self.entries.append(entry)
        seq = self.next_id
        self.next_id += 1
        return seq


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
    max_events: int = 100,
    state_summary_entity_types: list[str] | None = None,
    reactivity_window_events: int = 5,
) -> GameDefinition:
    flow_kwargs: dict[str, Any] = {
        "type": "event_driven",
        "max_wall_clock_seconds": 900,
        "max_events": max_events,
        "stalemate_timeout_seconds": 180,
        "activation_mode": activation_mode,
        "first_mover": first_mover,
        "reactivity_window_events": reactivity_window_events,
    }
    if state_summary_entity_types is not None:
        flow_kwargs["state_summary_entity_types"] = state_summary_entity_types
    return GameDefinition(
        enabled=True,
        mode="negotiation",
        scoring_mode=scoring_mode,  # type: ignore[arg-type]
        flow=FlowConfig(**flow_kwargs),
        entities=GameEntitiesConfig(
            deals=[DealDecl(id="deal-q3", parties=["buyer", "supplier"])],
        ),
        win_conditions=[WinCondition(type="deal_closed")],
    )


async def _init_orchestrator(
    definition: GameDefinition | None = None,
    state_engine: CannedStateEngine | None = None,
    agency: FakeAgency | None = None,
    player_ids: list[str] | None = None,
    run_id: str = "run-harden-001",
    ledger: RecordingLedger | None = None,
) -> tuple[GameOrchestrator, AsyncMock, CannedStateEngine, FakeAgency, RecordingLedger]:
    o = GameOrchestrator()
    bus = _make_bus()
    state = state_engine or CannedStateEngine()
    agency = agency or FakeAgency()
    ledger = ledger or RecordingLedger()
    o._dependencies = {"state": state, "agency": agency}
    # Inject ledger via config (orchestrator reads `_config["_ledger"]`)
    await o.initialize({"_ledger": ledger}, bus)
    await o.configure(
        definition=definition or _make_def(),
        player_actor_ids=player_ids or ["buyer-001", "supplier-001"],
        run_id=run_id,
    )
    return o, bus, state, agency, ledger


def _make_event(
    action: str = "negotiate_propose",
    actor_id: str = "buyer-001",
    service_id: str = "game",
    deal_id: str = "deal-q3",
) -> WorldEvent:
    now = datetime.now(UTC)
    return WorldEvent(
        event_id=EventId(f"evt-{actor_id}-{action}"),
        event_type=f"world.{action}",
        timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
        actor_id=ActorId(actor_id),
        service_id=ServiceId(service_id),
        action=action,
        input_data={"deal_id": deal_id},
    )


# ---------------------------------------------------------------------------
# B2 — event_counter stability under scoring failure
# ---------------------------------------------------------------------------


class TestCounterStableOnError:
    """event_counter must NOT advance when the scorer raises.

    Before the fix, a failing score_event would leave the counter at N
    while the next event was conceptually N+1, permanently skewing the
    ``(max_events - event_number)`` efficiency bonus.
    """

    @pytest.mark.asyncio
    async def test_counter_advances_on_successful_score(self):
        o, _, _, _, _ = await _init_orchestrator()
        await o._on_start()
        assert o._game_state.event_counter == 0
        await o._handle_game_event(_make_event())
        assert o._game_state.event_counter == 1
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_counter_still_advances_when_scorer_raises(self):
        """Behavior: counter DOES advance (each event gets a stable number)."""
        o, _, _, _, _ = await _init_orchestrator()
        await o._on_start()

        class BoomScorer:
            async def score_event(self, ctx):
                raise RuntimeError("boom")

            async def settle(self, **kwargs):
                return None

        o._scorer = BoomScorer()  # type: ignore[assignment]
        await o._handle_game_event(_make_event())
        # Counter advanced to 1 (so the NEXT event is number 2, not 1 again)
        assert o._game_state.event_counter == 1
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_event_number_passed_to_scorer_is_stable(self):
        """Each event gets a unique ascending event_number, even through failures."""
        o, _, _, _, _ = await _init_orchestrator()
        await o._on_start()

        captured: list[int] = []

        class RecordingScorer:
            def __init__(self):
                self.calls = 0

            async def score_event(self, ctx):
                self.calls += 1
                captured.append(ctx.event_number)
                if self.calls == 2:
                    raise RuntimeError("middle failure")

            async def settle(self, **kwargs):
                return None

        o._scorer = RecordingScorer()  # type: ignore[assignment]
        for _ in range(3):
            await o._handle_game_event(_make_event())
        # Three events, three distinct event_numbers: 1, 2, 3 — NOT 1, 2, 2
        assert captured == [1, 2, 3]
        await o._on_stop()


# ---------------------------------------------------------------------------
# M1 — subscription tokens tracked + unsubscribed on stop
# ---------------------------------------------------------------------------


class TestUnsubscribeOnStop:
    """_on_stop unsubscribes every topic registered in _on_start."""

    @pytest.mark.asyncio
    async def test_on_stop_unsubscribes_every_topic(self):
        o, bus, _, _, _ = await _init_orchestrator()
        await o._on_start()
        subscribed = [call.args[0] for call in bus.subscribe.call_args_list]
        # 4 game topics + budget.exhausted + game.timeout = 6
        assert len(subscribed) == 6

        bus.unsubscribe.reset_mock()
        await o._on_stop()
        unsubscribed = [call.args[0] for call in bus.unsubscribe.call_args_list]
        assert sorted(unsubscribed) == sorted(subscribed)

    @pytest.mark.asyncio
    async def test_on_stop_clears_subscription_tokens(self):
        o, _, _, _, _ = await _init_orchestrator()
        await o._on_start()
        assert len(o._subscription_tokens) == 6
        await o._on_stop()
        assert o._subscription_tokens == []

    @pytest.mark.asyncio
    async def test_unsubscribe_failures_are_tolerated(self):
        """A bus.unsubscribe that raises doesn't prevent other topics from being cleaned up."""
        o, bus, _, _, _ = await _init_orchestrator()
        bus.unsubscribe.side_effect = RuntimeError("bus gone")
        await o._on_start()
        # Should not raise
        await o._on_stop()
        # Every attempt was made
        assert bus.unsubscribe.call_count == 6


# ---------------------------------------------------------------------------
# M2 — GameEngineErrorEvent published on broad-catch failures
# ---------------------------------------------------------------------------


class TestEngineErrorEvents:
    """Every orchestrator broad-catch publishes an observable error event."""

    @pytest.mark.asyncio
    async def test_scorer_failure_publishes_error_event(self):
        o, bus, _, _, _ = await _init_orchestrator()
        await o._on_start()
        bus.publish.reset_mock()

        class BoomScorer:
            async def score_event(self, ctx):
                raise RuntimeError("scorer boom")

            async def settle(self, **kwargs):
                return None

        o._scorer = BoomScorer()  # type: ignore[assignment]
        await o._handle_game_event(_make_event())
        errors = [
            c.args[0]
            for c in bus.publish.call_args_list
            if isinstance(c.args[0], GameEngineErrorEvent)
        ]
        assert len(errors) == 1
        assert errors[0].source == "score_event"
        assert "scorer boom" in errors[0].message
        assert errors[0].exception_type == "RuntimeError"
        assert errors[0].event_number == 1
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_win_check_failure_publishes_error_event(self):
        o, bus, _, _, _ = await _init_orchestrator()
        await o._on_start()
        bus.publish.reset_mock()

        class BoomEvaluator:
            async def check(self, **kwargs):
                raise RuntimeError("evaluator boom")

        o._win_evaluator = BoomEvaluator()  # type: ignore[assignment]
        await o._handle_game_event(_make_event())
        errors = [
            c.args[0]
            for c in bus.publish.call_args_list
            if isinstance(c.args[0], GameEngineErrorEvent)
        ]
        assert any(e.source == "win_check" for e in errors)
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_state_query_failure_publishes_error_event(self):
        state = CannedStateEngine()
        state.raise_on.add("negotiation_deal")
        o, bus, _, _, _ = await _init_orchestrator(state_engine=state)
        await o._on_start()
        bus.publish.reset_mock()

        now = datetime.now(UTC)
        await o._handle_timeout(
            GameTimeoutEvent(
                event_id=EventId("evt-t"),
                event_type="game.timeout",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                reason="wall_clock",
            )
        )
        errors = [
            c.args[0]
            for c in bus.publish.call_args_list
            if isinstance(c.args[0], GameEngineErrorEvent)
        ]
        assert any(e.source == "state_query" for e in errors)

    @pytest.mark.asyncio
    async def test_settle_failure_publishes_error_event(self):
        o, bus, _, _, _ = await _init_orchestrator()
        await o._on_start()
        bus.publish.reset_mock()

        class BoomScorer:
            async def score_event(self, ctx):
                return None

            async def settle(self, **kwargs):
                raise RuntimeError("settle boom")

        o._scorer = BoomScorer()  # type: ignore[assignment]
        now = datetime.now(UTC)
        await o._handle_timeout(
            GameTimeoutEvent(
                event_id=EventId("evt-t"),
                event_type="game.timeout",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                reason="wall_clock",
            )
        )
        errors = [
            c.args[0]
            for c in bus.publish.call_args_list
            if isinstance(c.args[0], GameEngineErrorEvent)
        ]
        assert any(e.source == "settle" for e in errors)

    @pytest.mark.asyncio
    async def test_state_summary_failure_publishes_error_event(self):
        state = CannedStateEngine()
        state.raise_on.add("negotiation_deal")
        o, bus, _, _, _ = await _init_orchestrator(state_engine=state)
        await o._on_start()
        bus.publish.reset_mock()

        summary = await o._build_state_summary()
        assert summary.startswith("Game state at event")  # header still rendered
        errors = [
            c.args[0]
            for c in bus.publish.call_args_list
            if isinstance(c.args[0], GameEngineErrorEvent)
        ]
        assert any(e.source == "state_summary" for e in errors)
        await o._on_stop()


# ---------------------------------------------------------------------------
# M4 — ledger lifecycle entries
# ---------------------------------------------------------------------------


class TestLifecycleLedgerEntries:
    """Orchestrator writes EngineLifecycleEntry records for every transition."""

    @pytest.mark.asyncio
    async def test_start_writes_started_entry(self):
        o, _, _, _, ledger = await _init_orchestrator()
        await o._on_start()
        started_entries = [e for e in ledger.entries if getattr(e, "event_type", None) == "started"]
        assert len(started_entries) == 1
        assert started_entries[0].engine_name == "game"
        assert started_entries[0].details["run_id"] == "run-harden-001"
        assert started_entries[0].details["num_players"] == 2
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_terminate_natural_writes_terminated_entry(self):
        state = CannedStateEngine(
            {
                "negotiation_deal": [
                    {"id": "deal-q3", "status": "accepted", "parties": ["buyer", "supplier"]}
                ]
            }
        )
        o, _, _, _, ledger = await _init_orchestrator(state_engine=state)
        await o._on_start()
        ledger.entries.clear()
        await o._handle_game_event(_make_event(action="negotiate_accept"))
        terminated = [e for e in ledger.entries if getattr(e, "event_type", None) == "terminated"]
        assert len(terminated) == 1
        assert terminated[0].details["path"] == "natural"
        assert terminated[0].details["reason"] == "deal_closed"

    @pytest.mark.asyncio
    async def test_timeout_writes_timed_out_entry(self):
        o, _, _, _, ledger = await _init_orchestrator()
        await o._on_start()
        ledger.entries.clear()
        now = datetime.now(UTC)
        await o._handle_timeout(
            GameTimeoutEvent(
                event_id=EventId("evt-t"),
                event_type="game.timeout",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                reason="wall_clock",
            )
        )
        timed_out = [e for e in ledger.entries if getattr(e, "event_type", None) == "timed_out"]
        assert len(timed_out) == 1
        assert timed_out[0].details["reason"] == "wall_clock"

    @pytest.mark.asyncio
    async def test_ledger_absent_does_not_raise(self):
        """Orchestrator works with or without a ledger injected."""
        o = GameOrchestrator()
        bus = _make_bus()
        state = CannedStateEngine()
        agency = FakeAgency()
        o._dependencies = {"state": state, "agency": agency}
        await o.initialize({}, bus)  # no _ledger key
        await o.configure(
            definition=_make_def(),
            player_actor_ids=["buyer-001", "supplier-001"],
            run_id="run-no-ledger",
        )
        # Should not raise
        await o._on_start()
        await o._on_stop()


# ---------------------------------------------------------------------------
# M5 — event_id uniqueness
# ---------------------------------------------------------------------------


class TestEventIdUniqueness:
    """All orchestrator-published events get unique IDs (UUID suffix)."""

    @pytest.mark.asyncio
    async def test_score_update_event_ids_are_unique(self):
        o, bus, _, _, _ = await _init_orchestrator()
        await o._on_start()
        bus.publish.reset_mock()

        # Fire two events with same actor at same event_number position
        await o._handle_game_event(_make_event())
        await o._handle_game_event(_make_event())

        score_events = [
            c.args[0]
            for c in bus.publish.call_args_list
            if isinstance(c.args[0], GameScoreUpdatedEvent)
        ]
        ids = [str(e.event_id) for e in score_events]
        assert len(ids) == len(set(ids)), f"duplicate event_ids: {ids}"
        await o._on_stop()

    @pytest.mark.asyncio
    async def test_active_state_event_ids_are_unique_on_toggle(self):
        o, bus, _, _, _ = await _init_orchestrator()
        await o._on_start()
        bus.publish.reset_mock()
        await o._publish_active_state(active=False)
        await o._publish_active_state(active=True)
        await o._publish_active_state(active=False)
        from volnix.engines.game.events import GameActiveStateChangedEvent

        events = [
            c.args[0]
            for c in bus.publish.call_args_list
            if isinstance(c.args[0], GameActiveStateChangedEvent)
        ]
        ids = [str(e.event_id) for e in events]
        assert len(ids) == len(set(ids))

    @pytest.mark.asyncio
    async def test_kickstart_event_id_has_suffix(self):
        o, bus, _, _, _ = await _init_orchestrator()
        await o._on_start()
        from volnix.engines.game.events import GameKickstartEvent

        kickstart = [
            c.args[0]
            for c in bus.publish.call_args_list
            if isinstance(c.args[0], GameKickstartEvent)
        ][0]
        # Deterministic pattern: evt-game-kickstart-{run_id}-{12-hex-suffix}
        assert re.match(
            r"^evt-game-kickstart-run-harden-001-[0-9a-f]{12}$", str(kickstart.event_id)
        )
        await o._on_stop()


# ---------------------------------------------------------------------------
# m1 — state_summary entity types come from FlowConfig
# ---------------------------------------------------------------------------


class TestStateSummaryEntityTypes:
    """``_build_state_summary`` queries the entity types declared in FlowConfig."""

    @pytest.mark.asyncio
    async def test_default_queries_negotiation_deal(self):
        state = CannedStateEngine({"negotiation_deal": [{"id": "d1", "status": "open"}]})
        o, _, _, _, _ = await _init_orchestrator(state_engine=state)
        await o._build_state_summary()
        assert any(q[0] == "negotiation_deal" for q in state.queries)

    @pytest.mark.asyncio
    async def test_custom_entity_types_are_queried(self):
        state = CannedStateEngine(
            {
                "auction_lot": [{"id": "lot-1", "status": "open"}],
                "bid_ledger": [{"id": "bid-1", "status": "open"}],
            }
        )
        definition = _make_def(state_summary_entity_types=["auction_lot", "bid_ledger"])
        o, _, _, _, _ = await _init_orchestrator(definition=definition, state_engine=state)
        summary = await o._build_state_summary()
        queried_types = [q[0] for q in state.queries]
        assert "auction_lot" in queried_types
        assert "bid_ledger" in queried_types
        # Negotiation deal should NOT be queried in this config
        assert "negotiation_deal" not in queried_types
        # Summary mentions both rows
        assert "lot-1" in summary
        assert "bid-1" in summary

    @pytest.mark.asyncio
    async def test_timeout_settlement_uses_same_config(self):
        """_handle_timeout queries the same entity types from FlowConfig."""
        state = CannedStateEngine(
            {"auction_lot": [{"id": "lot-1", "status": "open", "parties": []}]}
        )
        definition = _make_def(state_summary_entity_types=["auction_lot"])
        o, _, _, _, _ = await _init_orchestrator(definition=definition, state_engine=state)
        await o._on_start()
        state.queries.clear()

        now = datetime.now(UTC)
        await o._handle_timeout(
            GameTimeoutEvent(
                event_id=EventId("evt-t"),
                event_type="game.timeout",
                timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
                reason="wall_clock",
            )
        )
        queried_types = [q[0] for q in state.queries]
        assert "auction_lot" in queried_types


# ---------------------------------------------------------------------------
# m2 — role_to_actor_id map resolution
# ---------------------------------------------------------------------------


class TestRoleMapResolution:
    @pytest.mark.asyncio
    async def test_role_map_built_at_configure(self):
        o, _, _, _, _ = await _init_orchestrator(player_ids=["buyer-abc", "supplier-xyz"])
        assert "buyer" in o._role_to_actor_id
        assert "supplier" in o._role_to_actor_id
        assert str(o._role_to_actor_id["buyer"]) == "buyer-abc"
        assert str(o._role_to_actor_id["supplier"]) == "supplier-xyz"
        # Exact actor_id lookup also works
        assert str(o._role_to_actor_id["buyer-abc"]) == "buyer-abc"

    @pytest.mark.asyncio
    async def test_first_mover_resolved_by_role(self):
        o, _, _, _, _ = await _init_orchestrator(
            definition=_make_def(first_mover="supplier"),
            player_ids=["buyer-001", "supplier-001"],
        )
        resolved = o._resolve_first_mover()
        assert str(resolved) == "supplier-001"

    @pytest.mark.asyncio
    async def test_first_mover_resolved_by_exact_id(self):
        o, _, _, _, _ = await _init_orchestrator(
            definition=_make_def(first_mover="supplier-001"),
            player_ids=["buyer-001", "supplier-001"],
        )
        resolved = o._resolve_first_mover()
        assert str(resolved) == "supplier-001"

    @pytest.mark.asyncio
    async def test_first_mover_unknown_falls_back_to_first_player(self):
        o, _, _, _, _ = await _init_orchestrator(
            definition=_make_def(first_mover="mediator"),
            player_ids=["buyer-001", "supplier-001"],
        )
        resolved = o._resolve_first_mover()
        assert str(resolved) == "buyer-001"
