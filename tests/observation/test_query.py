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
    assert [e.tick for e in tl.events] == [2, 5]
    assert all(e.source is TimelineSource.UTTERANCE for e in tl.events)


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
    assert [e.tick for e in tl.events] == [1, 3, 5]
    assert [e.source for e in tl.events] == [
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
    assert [e.source for e in tl.events] == [
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
    assert [e.tick for e in tl.events] == [5]


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


async def test_positive_ledger_source_pulls_typed_rows() -> None:
    """Post-impl audit M7: the LEDGER source path is exercised
    end-to-end. Previously only referenced via the empty-include
    / 4-source tests without directly hitting
    ``_collect_ledger_rows``."""
    ledger = await _make_ledger()
    # Seed two utterance rows — using "llm.utterance" as the
    # ledger type filter lets us pull them via the ledger
    # source without needing a separate entry type.
    await _seed_utterance(ledger, tick=2, activation_id="act-a", content="first")
    await _seed_utterance(ledger, tick=5, activation_id="act-b", content="second")
    q = (
        ObservationQuery(ledger=ledger, bus_persistence=None, state_engine=None)
        .for_session("s-1")
        .include([TimelineSource.LEDGER])
        .add_ledger_type("llm.utterance")
    )
    tl = await q.build()
    assert len(tl) == 2
    assert all(e.source is TimelineSource.LEDGER for e in tl.events)
    assert [e.tick for e in tl.events] == [2, 5]


async def test_negative_actor_filter_excludes_events_without_actor_id() -> None:
    """Post-impl audit L3: events lacking an ``actor_id``
    attribute must be EXCLUDED when a for_actor filter is set.
    Previously the ``actor is not None`` guard silently included
    them."""
    from datetime import UTC, datetime

    from volnix.core.events import Event
    from volnix.core.types import Timestamp

    class _ActorlessBus:
        async def query(self, **kwargs: Any) -> list[Any]:
            # A lifecycle-style event with no actor_id attribute.
            return [
                Event(
                    event_type="lifecycle.started",
                    timestamp=Timestamp(
                        world_time=datetime(2026, 1, 15, tzinfo=UTC),
                        wall_time=datetime.now(UTC),
                        tick=1,
                    ),
                    session_id=SessionId("s-1"),
                )
            ]

    q = (
        ObservationQuery(ledger=None, bus_persistence=_ActorlessBus(), state_engine=None)
        .for_session("s-1")
        .for_actor("alice")
        .include([TimelineSource.EVENT])
    )
    tl = await q.build()
    # Actor-filter set → actor-less events excluded.
    assert len(tl) == 0


# ─── Post-impl audit regression tests ─────────────────────────────


async def test_negative_build_twice_raises() -> None:
    """Post-impl audit C3: builders are single-use. Re-calling
    ``build()`` must surface as an error rather than silently
    duplicating rows from leftover accumulator state."""
    ledger = await _make_ledger()
    q = (
        ObservationQuery(ledger=ledger, bus_persistence=None, state_engine=None)
        .for_session("s-1")
        .include([TimelineSource.UTTERANCE])
    )
    await q.build()
    with pytest.raises(RuntimeError, match="single-use"):
        await q.build()


async def test_negative_session_scope_required_for_event_source() -> None:
    """Post-impl audit H1: forgetting ``for_session`` on a query
    that includes ``EVENT`` (or LEDGER / UTTERANCE) raises —
    prevents silent cross-session data leak."""
    q = ObservationQuery(ledger=None, bus_persistence=None, state_engine=None).include(
        [TimelineSource.EVENT]
    )
    with pytest.raises(ValueError, match="session-scoped"):
        await q.build()


async def test_positive_allow_cross_session_opt_in() -> None:
    """Operator tooling opts in explicitly to cross-session."""
    bus = _StubBusPersistence(
        [_make_event(tick=1, session_id="s-a"), _make_event(tick=2, session_id="s-b")]
    )
    q = (
        ObservationQuery(ledger=None, bus_persistence=bus, state_engine=None)
        .include([TimelineSource.EVENT])
        .allow_cross_session()
    )
    tl = await q.build()
    assert len(tl) == 2


async def test_positive_event_sequence_deterministic_from_event_id() -> None:
    """Post-impl audit C1: events derive ``sequence`` from a
    stable hash of ``event_id`` so two replays produce byte-
    identical timelines — not the pre-cleanup bug where every
    event got ``sequence=0``."""
    bus = _StubBusPersistence([_make_event(tick=1), _make_event(tick=1)])
    q1 = (
        ObservationQuery(ledger=None, bus_persistence=bus, state_engine=None)
        .for_session("s-1")
        .include([TimelineSource.EVENT])
    )
    tl1 = await q1.build()
    # Two distinct events at the same tick — sequences must differ
    # AND be >0 (the old buggy behaviour was 0 for every event).
    seqs = [e.sequence for e in tl1.events]
    assert len(set(seqs)) == 2
    assert all(s > 0 for s in seqs)


async def test_positive_filter_no_source_returns_new_instance() -> None:
    """Post-impl audit H7: ``filter(source=None)`` must return a
    fresh ``UnifiedTimeline`` even on the no-op path, not ``self``."""
    from volnix.observation.query import UnifiedTimeline

    tl = UnifiedTimeline(events=[])
    filtered = tl.filter(source=None)
    assert filtered is not tl
    assert filtered == tl


async def test_negative_payload_mutation_does_not_leak_into_timeline_event() -> None:
    """Post-impl audit H5: the payload field validator deep-copies
    its input so downstream mutation of the emitted dict cannot
    alter the frozen model's stored payload."""
    from volnix.observation.query import TimelineEvent

    source = {"outer": {"inner": "orig"}}
    evt = TimelineEvent(source=TimelineSource.EVENT, tick=0, sequence=0, payload=source)
    source["outer"]["inner"] = "MUTATED"
    assert evt.payload["outer"]["inner"] == "orig"


async def test_positive_add_trajectory_coerces_to_entity_id() -> None:
    """Post-impl audit H8: ``add_trajectory`` accepts raw str for
    ergonomics but coerces to ``EntityId`` so the protocol boundary
    honours typed-ID discipline."""
    from volnix.core.types import EntityId

    recorded: list[Any] = []

    class _Recorder:
        async def get_trajectory(self, entity_id, field_path, tick_range=None) -> list[Any]:
            recorded.append(entity_id)
            return []

    q = (
        ObservationQuery(ledger=None, bus_persistence=None, state_engine=_Recorder())
        .include([TimelineSource.TRAJECTORY])
        .add_trajectory("alice-raw-str", "budget")
    )
    await q.build()
    assert recorded == [EntityId("alice-raw-str")]


async def test_negative_for_session_empty_string_raises() -> None:
    q = ObservationQuery(ledger=None, bus_persistence=None, state_engine=None)
    with pytest.raises(ValueError, match="non-empty"):
        q.for_session("")
    with pytest.raises(ValueError, match="non-empty"):
        q.for_session("   ")


async def test_negative_for_actor_empty_string_raises() -> None:
    q = ObservationQuery(ledger=None, bus_persistence=None, state_engine=None)
    with pytest.raises(ValueError, match="non-empty"):
        q.for_actor("")


async def test_positive_limit_method_overrides_default(tmp_path) -> None:
    """Post-impl audit H4: silent 1000-row truncation replaced by
    a configurable ``.limit(n)``."""
    ledger = await _make_ledger()
    for i in range(15):
        await _seed_utterance(ledger, tick=i, activation_id=f"act-{i}")
    q = (
        ObservationQuery(ledger=ledger, bus_persistence=None, state_engine=None)
        .for_session("s-1")
        .include([TimelineSource.UTTERANCE])
        .limit(5)
    )
    tl = await q.build()
    assert len(tl) == 5


async def test_negative_limit_negative_value_raises() -> None:
    q = ObservationQuery(ledger=None, bus_persistence=None, state_engine=None)
    with pytest.raises(ValueError, match="non-negative"):
        q.limit(-1)


async def test_positive_model_dump_roundtrip_survives_len_override() -> None:
    """Post-impl audit H6 / M9: removing ``__iter__`` override keeps
    Pydantic serialization intact. ``model_dump`` and JSON round-trip
    must work on ``UnifiedTimeline``."""
    from volnix.observation.query import UnifiedTimeline

    tl = UnifiedTimeline(
        events=[TimelineEvent(source=TimelineSource.EVENT, tick=1, sequence=1, payload={"k": "v"})]
    )
    dumped = tl.model_dump(mode="json")
    assert dumped["events"][0]["payload"] == {"k": "v"}
    restored = UnifiedTimeline.model_validate_json(tl.model_dump_json())
    assert restored == tl


async def test_positive_four_source_same_tick_ordering() -> None:
    """Post-impl audit M8: all four sources at the same tick are
    ordered ``event < ledger < trajectory < utterance`` — the
    alphabetical tiebreak contract."""
    from volnix.core.types import EntityId, EventId
    from volnix.engines.state.trajectory import TrajectoryPoint

    ledger = await _make_ledger()
    await _seed_utterance(ledger, tick=5, activation_id="act-u")
    # Seed a ledger row of a different type via another utterance —
    # any LedgerEntry works for sort testing; utterance type filter
    # on the LEDGER source requires matching type.
    from volnix.core.types import ActivationId

    await ledger.append(
        LLMUtteranceEntry(
            actor_id=ActorId("alice"),
            activation_id=ActivationId("act-l"),
            session_id=SessionId("s-1"),
            role="system",
            content="x",
            content_hash=f"sha256:{'0' * 64}",
            tick=5,
            sequence=0,
        )
    )
    bus = _StubBusPersistence([_make_event(tick=5)])
    pt = TrajectoryPoint(
        tick=5,
        value=1,
        event_id=EventId("evt-t"),
        entity_id=EntityId("alice"),
        field_path="budget",
    )
    state = _StubStateEngine({("alice", "budget"): [pt]})
    q = (
        ObservationQuery(ledger=ledger, bus_persistence=bus, state_engine=state)
        .for_session("s-1")
        .include(
            [
                TimelineSource.EVENT,
                TimelineSource.LEDGER,
                TimelineSource.TRAJECTORY,
                TimelineSource.UTTERANCE,
            ]
        )
        .add_trajectory("alice", "budget")
        .add_ledger_type("llm.utterance")
    )
    tl = await q.build()
    # Utterance source and ledger source both resolve from the same
    # ledger type in this synthetic test — we get utterance rows
    # from both collectors. Verify the canonical ordering: EVENT
    # first, then LEDGER, then TRAJECTORY, then UTTERANCE rows.
    seen_order = [e.source for e in tl.events]
    first_pos = {src: seen_order.index(src) for src in set(seen_order)}
    assert first_pos[TimelineSource.EVENT] < first_pos[TimelineSource.LEDGER]
    assert first_pos[TimelineSource.LEDGER] < first_pos[TimelineSource.TRAJECTORY]
    assert first_pos[TimelineSource.TRAJECTORY] < first_pos[TimelineSource.UTTERANCE]
