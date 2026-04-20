"""Phase 4C Step 5 — SessionManager lifecycle tests.

Covers start/pause/resume/end, end-hook semantics (callback list +
bus event), checkpoint guards, seed-strategy derivation, the
audit-fold C3 guarantee that ledger + store agree after a hook
raises, and the post-ship M3 guarantee that ledger failures
propagate (not swallowed).

Negative ratio: 10/18 = 55%.
"""

from __future__ import annotations

from typing import Any

import pytest

from volnix.core.session import (
    SeedStrategy,
    Session,
    SessionStatus,
    SessionType,
)
from volnix.core.types import SessionId, WorldId
from volnix.persistence.manager import create_database
from volnix.sessions.manager import SessionManager
from volnix.sessions.store import SessionStore


class _RecordingBus:
    def __init__(self) -> None:
        self.events: list[Any] = []

    async def publish(self, event: Any) -> None:
        self.events.append(event)


class _RecordingLedger:
    def __init__(self) -> None:
        self.entries: list[Any] = []

    async def append(self, entry: Any) -> int:
        self.entries.append(entry)
        return len(self.entries)


async def _make_manager(
    *, with_bus: bool = True, with_ledger: bool = True
) -> tuple[SessionManager, _RecordingBus | None, _RecordingLedger | None]:
    db = await create_database(":memory:", wal_mode=False)
    store = SessionStore(db)
    await store.initialize()
    bus = _RecordingBus() if with_bus else None
    ledger = _RecordingLedger() if with_ledger else None
    mgr = SessionManager(store=store, bus=bus, ledger=ledger)  # type: ignore[arg-type]
    return mgr, bus, ledger


# ─── Start ────────────────────────────────────────────────────────


async def test_negative_start_requires_world_seed_for_inherit_strategy() -> None:
    mgr, _, _ = await _make_manager()
    with pytest.raises(ValueError, match="world_seed"):
        await mgr.start(
            WorldId("w-1"),
            SessionType.BOUNDED,
            seed_strategy=SeedStrategy.INHERIT,
        )


async def test_negative_start_requires_explicit_seed_for_explicit_strategy() -> None:
    mgr, _, _ = await _make_manager()
    with pytest.raises(ValueError, match="explicit_seed"):
        await mgr.start(
            WorldId("w-1"),
            SessionType.BOUNDED,
            seed_strategy=SeedStrategy.EXPLICIT,
        )


async def test_positive_start_creates_session_with_derived_seed_inherit() -> None:
    mgr, _, _ = await _make_manager()
    session = await mgr.start(
        WorldId("w-1"),
        SessionType.BOUNDED,
        seed_strategy=SeedStrategy.INHERIT,
        world_seed=1234,
    )
    assert isinstance(session, Session)
    assert session.seed == 1234
    assert session.status is SessionStatus.ACTIVE
    assert session.seed_strategy is SeedStrategy.INHERIT


async def test_positive_start_fresh_strategy_uses_stable_hash() -> None:
    """Audit-fold C2: ``FRESH`` must use a stable hash so seeds are
    reproducible across Python processes. Two separate managers
    producing sessions with the SAME session_id + world_seed +
    strategy must yield the same effective seed. We fake this by
    invoking the derivation helper directly with a fixed
    session_id."""
    from volnix.sessions.manager import _derive_seed

    s1 = _derive_seed(
        SeedStrategy.FRESH,
        SessionId("fixed-sess-id"),
        explicit_seed=None,
        world_seed=1000,
    )
    s2 = _derive_seed(
        SeedStrategy.FRESH,
        SessionId("fixed-sess-id"),
        explicit_seed=None,
        world_seed=1000,
    )
    assert s1 == s2
    assert s1 != 1000


async def test_positive_start_appends_ledger_entry_and_publishes_event() -> None:
    mgr, bus, ledger = await _make_manager()
    await mgr.start(
        WorldId("w-1"),
        SessionType.OPEN,
        seed_strategy=SeedStrategy.EXPLICIT,
        seed=99,
    )
    assert ledger is not None and len(ledger.entries) == 1
    assert type(ledger.entries[0]).__name__ == "SessionStartedEntry"
    assert bus is not None and len(bus.events) == 1
    assert type(bus.events[0]).__name__ == "SessionStartedEvent"


# ─── Get ──────────────────────────────────────────────────────────


async def test_negative_get_session_missing_raises_session_not_found() -> None:
    from volnix.core.errors import SessionNotFoundError

    mgr, _, _ = await _make_manager()
    with pytest.raises(SessionNotFoundError):
        await mgr.get_session(SessionId("sess-unknown"))


# ─── Pause / Resume ──────────────────────────────────────────────


async def test_negative_pause_already_paused_raises() -> None:
    mgr, _, _ = await _make_manager()
    s = await mgr.start(WorldId("w-1"), world_seed=1)
    await mgr.pause(s.session_id)
    with pytest.raises(ValueError, match="cannot pause"):
        await mgr.pause(s.session_id)


async def test_negative_resume_active_session_raises() -> None:
    mgr, _, _ = await _make_manager()
    s = await mgr.start(WorldId("w-1"), world_seed=1)
    with pytest.raises(ValueError, match="cannot resume"):
        await mgr.resume(s.session_id)


async def test_positive_pause_publishes_bus_event() -> None:
    """Audit-fold H5: pause must publish a ``SessionPausedEvent``
    for bus-consumer symmetry with start/resume/end."""
    mgr, bus, _ = await _make_manager()
    s = await mgr.start(WorldId("w-1"), world_seed=1)
    await mgr.pause(s.session_id, note="awaiting user")
    assert bus is not None
    paused = [e for e in bus.events if type(e).__name__ == "SessionPausedEvent"]
    assert len(paused) == 1
    assert paused[0].note == "awaiting user"


async def test_positive_resume_sets_active_and_publishes_event() -> None:
    mgr, bus, _ = await _make_manager()
    s = await mgr.start(WorldId("w-1"), world_seed=1)
    await mgr.pause(s.session_id)
    resumed = await mgr.resume(s.session_id, tick=42)
    assert resumed.status is SessionStatus.ACTIVE
    assert bus is not None
    ev = [e for e in bus.events if type(e).__name__ == "SessionResumedEvent"]
    assert ev and ev[0].resumed_at_tick == 42


# ─── End ──────────────────────────────────────────────────────────


async def test_negative_end_non_terminal_status_raises() -> None:
    mgr, _, _ = await _make_manager()
    s = await mgr.start(WorldId("w-1"), world_seed=1)
    with pytest.raises(ValueError, match="terminal"):
        await mgr.end(s.session_id, status=SessionStatus.ACTIVE)


async def test_negative_end_already_ended_raises() -> None:
    mgr, _, _ = await _make_manager()
    s = await mgr.start(WorldId("w-1"), world_seed=1)
    await mgr.end(s.session_id)
    with pytest.raises(ValueError, match="already terminal"):
        await mgr.end(s.session_id)


async def test_negative_end_hook_raise_rolls_back_status_and_skips_ledger() -> None:
    """Audit-fold C3: a raising hook rolls the session back to its
    prior status AND the ``SessionEndedEntry`` is NOT appended —
    ledger + store always agree."""
    mgr, bus, ledger = await _make_manager()
    s = await mgr.start(WorldId("w-1"), world_seed=1)

    async def failing_hook(session: Session) -> None:
        raise RuntimeError("boom")

    mgr.register_on_session_end(failing_hook)
    with pytest.raises(RuntimeError, match="boom"):
        await mgr.end(s.session_id)

    # Store rolled back.
    got = await mgr.get_session(s.session_id)
    assert got.status is SessionStatus.ACTIVE
    # No SessionEndedEntry was appended — ledger entry count
    # unchanged from before the end() call.
    assert ledger is not None
    post_entries = [e for e in ledger.entries if type(e).__name__ == "SessionEndedEntry"]
    assert post_entries == []


async def test_positive_end_completed_publishes_invokes_callbacks() -> None:
    mgr, bus, ledger = await _make_manager()
    s = await mgr.start(WorldId("w-1"), world_seed=1)
    seen: list[Session] = []

    async def hook(session: Session) -> None:
        seen.append(session)

    mgr.register_on_session_end(hook)
    ended = await mgr.end(
        s.session_id,
        status=SessionStatus.COMPLETED,
        end_tick=7,
        reason="goal_reached",
    )
    assert ended.status is SessionStatus.COMPLETED
    assert seen == [ended]
    assert bus is not None
    assert any(type(e).__name__ == "SessionEndedEvent" for e in bus.events)
    assert ledger is not None
    assert any(type(e).__name__ == "SessionEndedEntry" for e in ledger.entries)


async def test_positive_end_abandoned_publishes_event_and_invokes_callbacks() -> None:
    """Audit-fold M7: the ``ABANDONED`` path is symmetric with
    ``COMPLETED`` — it must also fire the bus event AND invoke
    registered callbacks.

    Post-ship audit-fold M-NEW-4: also asserts that a matching
    ``SessionEndedEntry`` with ``status='abandoned'`` lands on the
    ledger — symmetry with the ``COMPLETED`` test which checks the
    ledger, and a guard against the audit's "ledger and event must
    agree" contract."""
    mgr, bus, ledger = await _make_manager()
    s = await mgr.start(WorldId("w-1"), world_seed=1)
    called: list[Session] = []

    async def hook(session: Session) -> None:
        called.append(session)

    mgr.register_on_session_end(hook)
    result = await mgr.end(s.session_id, status=SessionStatus.ABANDONED)
    assert result.status is SessionStatus.ABANDONED
    assert called == [result]
    assert bus is not None
    ev = [e for e in bus.events if type(e).__name__ == "SessionEndedEvent"]
    assert ev and ev[-1].status == "abandoned"
    # M-NEW-4: ledger has a SessionEndedEntry with status=abandoned.
    assert ledger is not None
    ended_entries = [e for e in ledger.entries if type(e).__name__ == "SessionEndedEntry"]
    assert ended_entries and ended_entries[-1].status == "abandoned"


async def test_negative_ledger_failure_propagates_not_swallowed() -> None:
    """Audit-fold M-NEW-1 (Step-5 post-ship): the plan-audit M3
    fix made ``_append_ledger`` propagate exceptions instead of
    swallowing them (DESIGN_PRINCIPLES: "if it didn't produce a
    ledger entry, it didn't happen"). Without a test, a future
    refactor could silently restore the narrow-except pattern
    and break the flight-recorder invariant."""
    from volnix.persistence.manager import create_database
    from volnix.sessions.manager import SessionManager
    from volnix.sessions.store import SessionStore

    class _FailingLedger:
        async def append(self, entry: Any) -> int:
            raise RuntimeError("ledger disk full")

    db = await create_database(":memory:", wal_mode=False)
    store = SessionStore(db)
    await store.initialize()
    mgr = SessionManager(store=store, ledger=_FailingLedger())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="ledger disk full"):
        await mgr.start(WorldId("w-1"), world_seed=1)


# ─── Checkpoint ──────────────────────────────────────────────────


async def test_negative_checkpoint_on_terminated_session_raises() -> None:
    """Audit-fold H6: checkpointing a terminated session would
    pollute audit data."""
    mgr, _, _ = await _make_manager()
    s = await mgr.start(WorldId("w-1"), world_seed=1)
    await mgr.end(s.session_id)
    with pytest.raises(ValueError, match="terminal"):
        await mgr.checkpoint(s.session_id, note="should fail")


async def test_positive_checkpoint_appends_ledger_entry() -> None:
    mgr, _, ledger = await _make_manager()
    s = await mgr.start(WorldId("w-1"), world_seed=1)
    await mgr.checkpoint(s.session_id, tick=5, note="midpoint")
    assert ledger is not None
    checkpoints = [
        e
        for e in ledger.entries
        if type(e).__name__ == "SessionCheckpointEntry" and e.kind.value == "checkpoint"
    ]
    assert len(checkpoints) == 1
    assert checkpoints[0].note == "midpoint"
