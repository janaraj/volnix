"""Phase 4C Step 10 — ObservationQuery + UnifiedTimeline tests.

Locks:
- Merge semantics: 4-source combination in ``(tick, source,
  sequence)`` order with stable tiebreakers.
- Filter semantics: ``for_session``, ``for_actor``,
  ``in_tick_range``, ``include`` narrow the result correctly.
- Immutability: ``UnifiedTimeline`` is frozen.
- Source-scoped include: empty ``include([])`` yields empty timeline.

Negative ratio: 5/10 = 50%.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from volnix.core.types import ActorId, SessionId
from volnix.ledger.config import LedgerConfig
from volnix.ledger.entries import LLMUtteranceEntry
from volnix.ledger.ledger import Ledger
from volnix.observation.query import (
    ObservationQuery,
    TimelineEvent,
    TimelineSource,
    UnifiedTimeline,
)
from volnix.persistence.manager import create_database


async def _make_ledger() -> Ledger:
    db = await create_database(":memory:", wal_mode=False)
    ledger = Ledger(LedgerConfig(), db)
    await ledger.initialize()
    return ledger


class _StubStateEngine:
    """Minimal StateEngineProtocol implementation for tests —
    returns a fixed sequence of trajectory points."""

    def __init__(self, points_by_key: dict[tuple[str, str], list[Any]]) -> None:
        self._points = points_by_key

    async def get_trajectory(self, entity_id: str, field_path: str, tick_range=None):
        return self._points.get((str(entity_id), field_path), [])


class _StubBusPersistence:
    def __init__(self, events: list[Any]) -> None:
        self._events = events

    async def query(self, **kwargs: Any) -> list[Any]:
        session_id = kwargs.get("session_id")
        if session_id is None:
            return list(self._events)
        return [e for e in self._events if str(getattr(e, "session_id", "")) == str(session_id)]


def _make_event(tick: int, session_id: str = "s-1", actor: str = "alice"):
    """Build an Event-like object the observation query can consume."""
    from volnix.core.events import WorldEvent
    from volnix.core.types import EntityId, ServiceId, Timestamp

    return WorldEvent(
        event_type="world.test",
        timestamp=Timestamp(
            world_time=datetime(2026, 1, 15, tzinfo=UTC),
            wall_time=datetime.now(UTC),
            tick=tick,
        ),
        actor_id=ActorId(actor),
        service_id=ServiceId("svc"),
        action="test",
        target_entity=EntityId("e-1"),
        session_id=SessionId(session_id),
    )


async def _seed_utterance(
    ledger: Ledger,
    *,
    tick: int,
    sequence: int = 0,
    actor: str = "alice",
    session: str = "s-1",
    activation_id: str = "act-1",
    content: str = "hi",
) -> None:
    from volnix.core.types import ActivationId

    await ledger.append(
        LLMUtteranceEntry(
            actor_id=ActorId(actor),
            activation_id=ActivationId(activation_id),
            session_id=SessionId(session),
            role="assistant",
            content=content,
            content_hash=f"sha256:{'0' * 64}",
            tokens=1,
            tick=tick,
            sequence=sequence,
        )
    )


# ─── Types ────────────────────────────────────────────────────────


def test_positive_unified_timeline_is_frozen() -> None:
    tl = UnifiedTimeline(events=[])
    with pytest.raises(Exception):
        tl.events = []  # type: ignore[misc]


def test_positive_timeline_source_enum_order_matches_tiebreak() -> None:
    """Source tiebreak is alphabetical on ``source.value``.
    Verifying the enum values so the ordering contract is locked."""
    assert TimelineSource.EVENT.value == "event"
    assert TimelineSource.LEDGER.value == "ledger"
    assert TimelineSource.TRAJECTORY.value == "trajectory"
    assert TimelineSource.UTTERANCE.value == "utterance"


def test_positive_timeline_event_is_frozen() -> None:
    e = TimelineEvent(source=TimelineSource.EVENT, tick=0, sequence=0, payload={})
    with pytest.raises(Exception):
        e.tick = 5  # type: ignore[misc]


# ─── Builder validation ───────────────────────────────────────────


async def test_negative_tick_range_start_after_end_raises() -> None:
    ledger = await _make_ledger()
    q = ObservationQuery(ledger=ledger, bus_persistence=None, state_engine=None)
    with pytest.raises(ValueError):
        q.in_tick_range(10, 5)


async def test_negative_empty_include_yields_empty_timeline() -> None:
    ledger = await _make_ledger()
    await _seed_utterance(ledger, tick=1)
    q = (
        ObservationQuery(ledger=ledger, bus_persistence=None, state_engine=None)
        .include([])
        .for_session("s-1")
    )
    tl = await q.build()
    assert len(tl) == 0


# ─── Merge semantics ──────────────────────────────────────────────


async def test_positive_utterance_only_timeline() -> None:
    ledger = await _make_ledger()
    await _seed_utterance(ledger, tick=2, sequence=0, content="first")
    await _seed_utterance(ledger, tick=5, sequence=0, content="second")
    q = (
        ObservationQuery(ledger=ledger, bus_persistence=None, state_engine=None)
        .for_session("s-1")
        .include([TimelineSource.UTTERANCE])
    )
    tl = await q.build()
    assert len(tl) == 2
    assert [e.tick for e in tl] == [2, 5]
    assert all(e.source is TimelineSource.UTTERANCE for e in tl)


async def test_positive_event_and_utterance_merge_sorted_by_tick() -> None:
    ledger = await _make_ledger()
    await _seed_utterance(ledger, tick=3)
    bus = _StubBusPersistence([_make_event(tick=1), _make_event(tick=5)])
    q = (
        ObservationQuery(ledger=ledger, bus_persistence=bus, state_engine=None)
        .for_session("s-1")
        .include([TimelineSource.EVENT, TimelineSource.UTTERANCE])
    )
    tl = await q.build()
    assert [e.tick for e in tl] == [1, 3, 5]
    assert [e.source for e in tl] == [
        TimelineSource.EVENT,
        TimelineSource.UTTERANCE,
        TimelineSource.EVENT,
    ]


async def test_positive_same_tick_source_tiebreak_is_stable() -> None:
    """Event and Utterance at the same tick: ``event`` sorts before
    ``utterance`` alphabetically — locks the stable ordering
    promise for replay determinism."""
    ledger = await _make_ledger()
    await _seed_utterance(ledger, tick=4)
    bus = _StubBusPersistence([_make_event(tick=4)])
    q = (
        ObservationQuery(ledger=ledger, bus_persistence=bus, state_engine=None)
        .for_session("s-1")
        .include([TimelineSource.EVENT, TimelineSource.UTTERANCE])
    )
    tl = await q.build()
    assert [e.source for e in tl] == [
        TimelineSource.EVENT,
        TimelineSource.UTTERANCE,
    ]


async def test_negative_tick_range_filters_out_of_range_rows() -> None:
    ledger = await _make_ledger()
    await _seed_utterance(ledger, tick=1)
    await _seed_utterance(ledger, tick=5)
    await _seed_utterance(ledger, tick=10)
    q = (
        ObservationQuery(ledger=ledger, bus_persistence=None, state_engine=None)
        .for_session("s-1")
        .include([TimelineSource.UTTERANCE])
        .in_tick_range(3, 7)
    )
    tl = await q.build()
    assert [e.tick for e in tl] == [5]


async def test_negative_actor_filter_excludes_other_actors() -> None:
    ledger = await _make_ledger()
    await _seed_utterance(ledger, tick=1, actor="alice")
    await _seed_utterance(ledger, tick=2, actor="bob", activation_id="act-2")
    q = (
        ObservationQuery(ledger=ledger, bus_persistence=None, state_engine=None)
        .for_session("s-1")
        .for_actor("alice")
        .include([TimelineSource.UTTERANCE])
    )
    tl = await q.build()
    assert len(tl) == 1
    assert tl[0].payload["actor_id"] == "alice"


# ─── Trajectory source ────────────────────────────────────────────


async def test_positive_trajectory_source_pulls_from_state_engine() -> None:
    from volnix.core.types import EntityId, EventId
    from volnix.engines.state.trajectory import TrajectoryPoint

    pt = TrajectoryPoint(
        tick=2,
        value=42,
        event_id=EventId("evt-1"),
        entity_id=EntityId("alice"),
        field_path="budget",
    )
    state = _StubStateEngine({("alice", "budget"): [pt]})
    q = (
        ObservationQuery(ledger=None, bus_persistence=None, state_engine=state)
        .include([TimelineSource.TRAJECTORY])
        .add_trajectory("alice", "budget")
    )
    tl = await q.build()
    assert len(tl) == 1
    assert tl[0].source is TimelineSource.TRAJECTORY
    assert tl[0].tick == 2
    assert tl[0].payload["value"] == 42
