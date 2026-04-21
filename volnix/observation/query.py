"""ObservationQuery + UnifiedTimeline (PMF Plan Phase 4C Step 10).

A ``UnifiedTimeline`` is the ordered merge of four sources:

1. ``event`` — committed ``WorldEvent``s from the bus persistence log
2. ``utterance`` — ``LLMUtteranceEntry`` rows from the ledger
3. ``trajectory`` — ``TrajectoryPoint`` projections from
   ``StateEngineProtocol.get_trajectory``
4. ``ledger`` — any other ``LedgerEntry`` subclass the caller
   requests by type

Ordering: ``(tick ASC, source ASC, sequence ASC)``. Stable tie-break
is critical so two replays of the same session produce byte-identical
timelines — that's the replay contract at the observation layer.

``ObservationQuery`` is a fluent builder; construction takes the
infrastructure dependencies (ledger, bus persistence, state engine
**protocol**, NOT the concrete engine) and ``.build()`` executes
the async merge.

Pure data — no persistence, no mutation, no caching. Each
``build()`` queries fresh.
"""

from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from volnix.core.types import ActorId, SessionId


class TimelineSource(enum.StrEnum):
    """Discriminator on ``TimelineEvent.source``. Ordered
    alphabetically to match the ``source ASC`` tiebreaker.
    """

    EVENT = "event"
    LEDGER = "ledger"
    TRAJECTORY = "trajectory"
    UTTERANCE = "utterance"


class TimelineEvent(BaseModel):
    """One row on a :class:`UnifiedTimeline`.

    Attributes:
        source: Which subsystem contributed this row.
        tick: Logical tick at the event's origin.
        sequence: Per-source monotonic sequence (e.g. bus
            ``sequence_id``, ledger row id, trajectory position,
            utterance row sequence). Used for stable within-source
            ordering when ticks collide.
        payload: Raw source object serialised as a dict. Consumers
            introspect via ``payload["event_type"]`` etc. — the
            timeline doesn't re-type the original row.
    """

    model_config = ConfigDict(frozen=True)

    source: TimelineSource
    tick: int
    sequence: int
    payload: dict[str, Any]


class UnifiedTimeline(BaseModel):
    """Immutable ordered merge of multi-source events.

    The list is SORTED at construction time; consumers can rely on
    ordering without re-sorting. ``__iter__``, ``__len__``, and
    ``__getitem__`` are available for ergonomic access.
    """

    model_config = ConfigDict(frozen=True)

    events: list[TimelineEvent] = Field(default_factory=list)

    def __iter__(self):  # type: ignore[override]
        return iter(self.events)

    def __len__(self) -> int:
        return len(self.events)

    def __getitem__(self, idx: int) -> TimelineEvent:
        return self.events[idx]

    def filter(self, *, source: TimelineSource | None = None) -> UnifiedTimeline:
        """Return a new timeline keeping only rows matching the
        filter. Pure — does not mutate ``self``."""
        if source is None:
            return self
        rows = [e for e in self.events if e.source is source]
        return UnifiedTimeline(events=rows)


def _sort_key(e: TimelineEvent) -> tuple[int, str, int]:
    """Stable sort key — ``(tick, source.value, sequence)``. Using
    ``source.value`` (lowercase string) gives alphabetical tiebreak:
    ``event < ledger < trajectory < utterance``.
    """
    return (e.tick, e.source.value, e.sequence)


class ObservationQuery:
    """Fluent builder for a :class:`UnifiedTimeline`.

    Dependencies are injected at construction (ledger, bus
    persistence, state engine **protocol**). The builder is
    stateful during configuration then drained by ``.build()``;
    callers should not reuse a builder after ``.build()``.
    """

    def __init__(
        self,
        *,
        ledger: Any,  # Ledger — query-only; any object with async query(LedgerQuery)
        bus_persistence: Any,  # BusPersistence | None — async query(session_id=..., limit=...)
        state_engine: Any,  # StateEngineProtocol — for get_trajectory lookups
    ) -> None:
        self._ledger = ledger
        self._bus_persistence = bus_persistence
        self._state_engine = state_engine

        self._session_id: SessionId | str | None = None
        self._actor_id: ActorId | str | None = None
        self._tick_range: tuple[int, int] | None = None
        self._include_sources: set[TimelineSource] = {
            TimelineSource.EVENT,
            TimelineSource.UTTERANCE,
        }
        self._trajectory_fields: list[tuple[str, str]] = []
        # List of (entity_id, field_path) tuples — trajectory is
        # entity-scoped so the caller adds each projection explicitly.
        self._ledger_types: list[str] = []

    # ── Fluent filters ────────────────────────────────────────────

    def for_session(self, session_id: SessionId | str) -> ObservationQuery:
        self._session_id = session_id
        return self

    def for_actor(self, actor_id: ActorId | str) -> ObservationQuery:
        self._actor_id = actor_id
        return self

    def in_tick_range(self, start: int, end: int) -> ObservationQuery:
        if start > end:
            raise ValueError(f"tick_range start ({start}) must be <= end ({end})")
        self._tick_range = (start, end)
        return self

    def include(self, sources: list[TimelineSource] | set[TimelineSource]) -> ObservationQuery:
        """Replace the default source set. ``[]`` / ``set()`` yields
        an empty timeline on build (explicit opt-out is allowed)."""
        self._include_sources = set(sources)
        return self

    def add_trajectory(self, entity_id: str, field_path: str) -> ObservationQuery:
        """Add one ``(entity_id, field_path)`` trajectory projection
        to the build. Only honoured when ``TRAJECTORY`` is in the
        include set."""
        self._trajectory_fields.append((entity_id, field_path))
        return self

    def add_ledger_type(self, entry_type: str) -> ObservationQuery:
        """Include ledger rows of a specific ``entry_type``. Only
        honoured when ``LEDGER`` is in the include set."""
        self._ledger_types.append(entry_type)
        return self

    # ── Terminal ──────────────────────────────────────────────────

    async def build(self) -> UnifiedTimeline:
        """Execute the async merge. Each source queried
        independently; failures bubble up (the consumer sees
        infrastructure errors at the boundary, not buried inside
        primitives)."""
        rows: list[TimelineEvent] = []

        if TimelineSource.EVENT in self._include_sources:
            rows.extend(await self._collect_events())
        if TimelineSource.UTTERANCE in self._include_sources:
            rows.extend(await self._collect_utterances())
        if TimelineSource.TRAJECTORY in self._include_sources:
            rows.extend(await self._collect_trajectories())
        if TimelineSource.LEDGER in self._include_sources:
            rows.extend(await self._collect_ledger_rows())

        rows.sort(key=_sort_key)
        return UnifiedTimeline(events=rows)

    # ── Source collectors ─────────────────────────────────────────

    async def _collect_events(self) -> list[TimelineEvent]:
        if self._bus_persistence is None:
            return []
        evts = await self._bus_persistence.query(
            session_id=self._session_id,
        )
        out: list[TimelineEvent] = []
        for evt in evts:
            tick = int(getattr(evt.timestamp, "tick", 0))
            if not self._tick_in_range(tick):
                continue
            if self._actor_id is not None:
                actor = getattr(evt, "actor_id", None)
                if actor is not None and str(actor) != str(self._actor_id):
                    continue
            # sequence: Event id ordering is good enough; fall back
            # to payload hash when ``sequence_id`` isn't present.
            seq = getattr(evt, "sequence_id", 0)
            if not isinstance(seq, int):
                seq = 0
            out.append(
                TimelineEvent(
                    source=TimelineSource.EVENT,
                    tick=tick,
                    sequence=seq,
                    payload=evt.model_dump(mode="json"),
                )
            )
        return out

    async def _collect_utterances(self) -> list[TimelineEvent]:
        if self._ledger is None:
            return []
        from volnix.ledger.query import LedgerQueryBuilder

        qb = LedgerQueryBuilder().filter_type("llm.utterance")
        if self._session_id is not None:
            qb = qb.filter_session(self._session_id)
        if self._actor_id is not None:
            qb = qb.filter_actor(ActorId(str(self._actor_id)))
        qb = qb.limit(1_000)
        entries = await self._ledger.query(qb.build())
        out: list[TimelineEvent] = []
        for e in entries:
            tick = int(getattr(e, "tick", 0) or 0)
            if not self._tick_in_range(tick):
                continue
            seq = int(getattr(e, "sequence", 0) or 0)
            out.append(
                TimelineEvent(
                    source=TimelineSource.UTTERANCE,
                    tick=tick,
                    sequence=seq,
                    payload=e.model_dump(mode="json"),
                )
            )
        return out

    async def _collect_trajectories(self) -> list[TimelineEvent]:
        if self._state_engine is None or not self._trajectory_fields:
            return []
        out: list[TimelineEvent] = []
        for idx, (entity_id, field_path) in enumerate(self._trajectory_fields):
            points = await self._state_engine.get_trajectory(
                entity_id=entity_id,
                field_path=field_path,
                tick_range=self._tick_range,
            )
            # Position within the trajectory contributes to sequence
            # so multiple fields on the same entity don't collide.
            for pos, pt in enumerate(points):
                tick = int(getattr(pt, "tick", 0) or 0)
                if not self._tick_in_range(tick):
                    continue
                out.append(
                    TimelineEvent(
                        source=TimelineSource.TRAJECTORY,
                        tick=tick,
                        sequence=idx * 10_000 + pos,
                        payload=pt.model_dump(mode="json"),
                    )
                )
        return out

    async def _collect_ledger_rows(self) -> list[TimelineEvent]:
        if self._ledger is None or not self._ledger_types:
            return []
        from volnix.ledger.query import LedgerQueryBuilder

        out: list[TimelineEvent] = []
        for idx, entry_type in enumerate(self._ledger_types):
            qb = LedgerQueryBuilder().filter_type(entry_type).limit(1_000)
            if self._session_id is not None:
                qb = qb.filter_session(self._session_id)
            if self._actor_id is not None:
                qb = qb.filter_actor(ActorId(str(self._actor_id)))
            entries = await self._ledger.query(qb.build())
            for pos, e in enumerate(entries):
                tick = int(getattr(e, "tick", 0) or 0)
                if not self._tick_in_range(tick):
                    continue
                out.append(
                    TimelineEvent(
                        source=TimelineSource.LEDGER,
                        tick=tick,
                        sequence=idx * 10_000 + pos,
                        payload=e.model_dump(mode="json"),
                    )
                )
        return out

    def _tick_in_range(self, tick: int) -> bool:
        if self._tick_range is None:
            return True
        start, end = self._tick_range
        return start <= tick <= end
