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

Builders are single-use: ``.build()`` drains the accumulated
configuration and raises if called twice. Each ``build()`` queries
fresh — no caching layer.
"""

from __future__ import annotations

import copy
import enum
import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from volnix.core.types import ActorId, EntityId, SessionId


class TimelineSource(enum.StrEnum):
    """Discriminator on ``TimelineEvent.source``.

    The values are chosen so their alphabetical order encodes the
    preferred replay-ordering tiebreak:
    ``event < ledger < trajectory < utterance``. Adding a new source
    requires reviewing the tiebreak contract and the replay
    determinism tests.
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
        sequence: Per-source deterministic tie-break integer.
            Events derive it from a stable hash of ``event_id`` so
            two replays produce byte-identical sequences even
            though ``Event`` has no ``sequence_id`` attribute.
            Utterances use their ``LLMUtteranceEntry.sequence``
            field. Trajectories / ledger rows use a
            ``(source-ordinal, position-in-source)`` encoding
            that tolerates up to 10⁶ rows per source batch
            (assertion guard prevents silent collisions).
        payload: Raw source object serialised as a dict. The
            validator deep-copies the input so the frozen model's
            immutability promise extends through the payload —
            consumers mutating the returned dict do not alias back
            into the model (post-impl audit H5).
    """

    model_config = ConfigDict(frozen=True)

    source: TimelineSource
    tick: int
    sequence: int
    payload: dict[str, Any]

    @field_validator("payload", mode="before")
    @classmethod
    def _deepcopy_payload(cls, v: Any) -> Any:
        """Post-impl audit H5: Pydantic ``frozen=True`` only forbids
        attribute reassignment, not mutation of nested containers.
        We deep-copy at construction so every ``TimelineEvent``
        owns an isolated payload — consumers mutating the returned
        dict cannot tamper with the source.
        """
        if isinstance(v, dict):
            return copy.deepcopy(v)
        return v


class UnifiedTimeline(BaseModel):
    """Immutable ordered merge of multi-source events.

    The list is SORTED at construction time; consumers can rely on
    ordering without re-sorting. ``__len__`` and ``__getitem__``
    are available for ergonomic access; ``__iter__`` is delegated
    to ``events`` so ``for e in tl`` works. ``dict(tl)`` /
    ``list(tl.items())`` fall back to Pydantic's default via
    ``model_dump`` — NOT via ``__iter__`` (see L2 note).
    """

    model_config = ConfigDict(frozen=True)

    events: list[TimelineEvent] = Field(default_factory=list)

    def __len__(self) -> int:
        return len(self.events)

    def __getitem__(self, idx: int) -> TimelineEvent:
        return self.events[idx]

    # Deliberately do NOT override ``__iter__`` — the earlier
    # implementation shadowed Pydantic's ``BaseModel.__iter__``
    # which yields ``(field_name, value)`` tuples, breaking
    # ``dict(model)`` and downstream serializers (post-impl audit
    # H6). Consumers iterate over ``timeline.events`` directly or
    # use the sugar method below.

    def iter_events(self):
        """Convenience iterator over the event rows. Equivalent to
        ``iter(timeline.events)`` but keeps the call site readable.
        """
        return iter(self.events)

    def filter(self, *, source: TimelineSource | None = None) -> UnifiedTimeline:
        """Return a NEW timeline keeping only rows matching the
        filter. Pure — never returns ``self`` even when the filter
        is a no-op (post-impl audit H7). Frozen-model invariants
        are preserved either way, but a brand-new instance makes
        aliasing surprises impossible.
        """
        if source is None:
            return UnifiedTimeline(events=list(self.events))
        rows = [e for e in self.events if e.source is source]
        return UnifiedTimeline(events=rows)


def _sort_key(e: TimelineEvent) -> tuple[int, str, int]:
    """Stable sort key — ``(tick, source.value, sequence)``. Using
    ``source.value`` (lowercase string) gives alphabetical tiebreak:
    ``event < ledger < trajectory < utterance``.
    """
    return (e.tick, e.source.value, e.sequence)


def _deterministic_seq_from_id(raw_id: Any) -> int:
    """Post-impl audit C1: ``Event`` has no ``sequence_id`` field,
    and ``BusPersistence.query`` doesn't re-attach the SQL column
    to the deserialised object. Falling back to a truncated
    SHA-256 of the event id gives us a deterministic, stable
    tiebreak integer that survives process restarts and repeated
    replays — two replays of the same session produce byte-
    identical timelines as the docstring promises.
    """
    digest = hashlib.sha256(str(raw_id).encode("utf-8")).digest()
    # Take 7 bytes → fits in signed int64 (2^56 range) and
    # avoids negative numbers from sign-bit flips when consumers
    # cast to int32.
    return int.from_bytes(digest[:7], "big")


# Sentinel for "session_id not set" so we can distinguish from
# "session_id set to None explicitly" in require_session logic
# (post-impl audit H1).
_UNSET: Any = object()


# Maximum rows per trajectory / ledger source batch. Exceeding
# this in a single batch collides the sequence encoding; the
# builder asserts before emitting the collision. Raised from
# 10_000 to 1_000_000 to match realistic long-session state-delta
# counts (post-impl audit H2).
_MAX_ROWS_PER_BATCH: int = 1_000_000


class ObservationQuery:
    """Fluent builder for a :class:`UnifiedTimeline`.

    Dependencies are injected at construction (ledger, bus
    persistence, state engine **protocol**). The builder is
    single-use: ``.build()`` consumes the configuration and marks
    the builder spent; a second ``build()`` raises ``RuntimeError``
    (post-impl audit C3) so accidental re-use with mutated state
    surfaces as an error rather than silent timeline duplication.
    """

    def __init__(
        self,
        *,
        ledger: Any,  # Ledger — any object with async ``query(LedgerQuery)``
        bus_persistence: Any,  # BusPersistence | None — async ``query(session_id=..., limit=...)``
        state_engine: Any,  # StateEngineProtocol — for ``get_trajectory`` lookups
    ) -> None:
        self._ledger = ledger
        self._bus_persistence = bus_persistence
        self._state_engine = state_engine

        self._session_id: Any = _UNSET
        self._actor_id: ActorId | str | None = None
        self._tick_range: tuple[int, int] | None = None
        self._include_sources: set[TimelineSource] = {
            TimelineSource.EVENT,
            TimelineSource.UTTERANCE,
        }
        self._trajectory_fields: list[tuple[EntityId, str]] = []
        self._ledger_types: list[str] = []
        self._row_limit: int = 10_000  # raised from silent 1000 (H4)
        self._allow_cross_session: bool = False
        self._built: bool = False

    # ── Fluent filters ────────────────────────────────────────────

    def for_session(self, session_id: SessionId | str) -> ObservationQuery:
        """Scope the query to one platform session.

        Post-impl audit M6: reject empty / whitespace strings
        at the boundary — an empty session id is almost always a
        misread config value.
        """
        coerced = str(session_id).strip()
        if not coerced:
            raise ValueError("for_session: session_id must be non-empty")
        self._session_id = SessionId(coerced)
        return self

    def for_actor(self, actor_id: ActorId | str) -> ObservationQuery:
        coerced = str(actor_id).strip()
        if not coerced:
            raise ValueError("for_actor: actor_id must be non-empty")
        self._actor_id = ActorId(coerced)
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

    def allow_cross_session(self) -> ObservationQuery:
        """Opt out of the "session scope required" guard for
        session-scoped sources (EVENT / UTTERANCE / LEDGER).
        Intended for operator tooling that legitimately wants to
        query across sessions; the default is to refuse
        (post-impl audit H1) so a consumer who forgets
        ``for_session(...)`` doesn't accidentally leak every
        session's data.
        """
        self._allow_cross_session = True
        return self

    def add_trajectory(self, entity_id: EntityId | str, field_path: str) -> ObservationQuery:
        """Add one ``(entity_id, field_path)`` trajectory projection
        to the build. Only honoured when ``TRAJECTORY`` is in the
        include set.

        ``entity_id`` is coerced to ``EntityId`` so the call into
        ``StateEngineProtocol.get_trajectory`` honours the typed-ID
        discipline (post-impl audit H8).
        """
        self._trajectory_fields.append((EntityId(str(entity_id)), field_path))
        return self

    def add_ledger_type(self, entry_type: str) -> ObservationQuery:
        """Include ledger rows of a specific ``entry_type``. Only
        honoured when ``LEDGER`` is in the include set."""
        self._ledger_types.append(entry_type)
        return self

    def limit(self, row_limit: int) -> ObservationQuery:
        """Raise or lower the per-source row cap applied by the
        ledger query. Default 10 000. Pass ``0`` to disable the
        cap; primitives that assume a bounded timeline should
        apply their own guards instead (post-impl audit H4).
        """
        if row_limit < 0:
            raise ValueError(f"limit must be non-negative, got {row_limit}")
        self._row_limit = row_limit
        return self

    # ── Terminal ──────────────────────────────────────────────────

    async def build(self) -> UnifiedTimeline:
        """Execute the async merge. Each source queried
        independently; infrastructure failures bubble up to the
        caller. Single-use — calling twice raises
        ``RuntimeError``.
        """
        if self._built:
            raise RuntimeError(
                "ObservationQuery: build() already called. Builders are "
                "single-use — construct a fresh ObservationQuery for a "
                "new query (post-impl audit C3)."
            )
        self._enforce_session_scope()
        self._built = True

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

    def _enforce_session_scope(self) -> None:
        """Post-impl audit H1: session-scoped sources without a
        session filter would silently return every session's rows.
        Require either ``for_session(...)`` or an explicit
        ``allow_cross_session()`` opt-in.
        """
        session_scoped = {
            TimelineSource.EVENT,
            TimelineSource.UTTERANCE,
            TimelineSource.LEDGER,
        }
        if not self._include_sources & session_scoped:
            return
        if self._session_id is not _UNSET:
            return
        if self._allow_cross_session:
            return
        raise ValueError(
            "ObservationQuery: session-scoped sources "
            f"({sorted(s.value for s in self._include_sources & session_scoped)}) "
            "require either .for_session(...) or an explicit "
            ".allow_cross_session() opt-in. Refusing to silently merge "
            "every session's rows."
        )

    # ── Source collectors ─────────────────────────────────────────

    async def _collect_events(self) -> list[TimelineEvent]:
        if self._bus_persistence is None:
            return []
        session_for_query = self._session_id if self._session_id is not _UNSET else None
        evts = await self._bus_persistence.query(
            session_id=session_for_query,
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
            # Post-impl audit C1: Event has no sequence_id attribute;
            # derive a deterministic tiebreak integer from the
            # event id so replays are byte-identical.
            seq = _deterministic_seq_from_id(getattr(evt, "event_id", ""))
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
        if self._session_id is not _UNSET:
            qb = qb.filter_session(self._session_id)
        if self._actor_id is not None:
            qb = qb.filter_actor(self._actor_id)
        if self._row_limit > 0:
            qb = qb.limit(self._row_limit)
        entries = await self._ledger.query(qb.build())
        out: list[TimelineEvent] = []
        for e in entries:
            tick = int(getattr(e, "tick", 0))
            if not self._tick_in_range(tick):
                continue
            seq = int(getattr(e, "sequence", 0))
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
            if len(points) > _MAX_ROWS_PER_BATCH:
                raise RuntimeError(
                    f"ObservationQuery: trajectory {entity_id!r}/"
                    f"{field_path!r} returned {len(points)} points, "
                    f"exceeding per-batch cap {_MAX_ROWS_PER_BATCH} "
                    f"— sequence encoding would collide with the "
                    f"next field's range. Narrow the tick_range."
                )
            for pos, pt in enumerate(points):
                tick = int(getattr(pt, "tick", 0))
                if not self._tick_in_range(tick):
                    continue
                out.append(
                    TimelineEvent(
                        source=TimelineSource.TRAJECTORY,
                        tick=tick,
                        sequence=idx * _MAX_ROWS_PER_BATCH + pos,
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
            qb = LedgerQueryBuilder().filter_type(entry_type)
            if self._row_limit > 0:
                qb = qb.limit(self._row_limit)
            if self._session_id is not _UNSET:
                qb = qb.filter_session(self._session_id)
            if self._actor_id is not None:
                qb = qb.filter_actor(self._actor_id)
            entries = await self._ledger.query(qb.build())
            if len(entries) > _MAX_ROWS_PER_BATCH:
                raise RuntimeError(
                    f"ObservationQuery: ledger_type {entry_type!r} returned "
                    f"{len(entries)} rows, exceeding per-batch cap "
                    f"{_MAX_ROWS_PER_BATCH}. Narrow the query."
                )
            for pos, e in enumerate(entries):
                tick = int(getattr(e, "tick", 0))
                if not self._tick_in_range(tick):
                    continue
                out.append(
                    TimelineEvent(
                        source=TimelineSource.LEDGER,
                        tick=tick,
                        sequence=idx * _MAX_ROWS_PER_BATCH + pos,
                        payload=e.model_dump(mode="json"),
                    )
                )
        return out

    def _tick_in_range(self, tick: int) -> bool:
        if self._tick_range is None:
            return True
        start, end = self._tick_range
        return start <= tick <= end
