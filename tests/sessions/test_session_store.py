"""Phase 4C Step 5 — SessionStore SQL persistence tests.

Exercises the CRUD surface directly against in-memory SQLite so
the orchestration layer (SessionManager) has a trustworthy
foundation to build on.

Negative ratio: 3/6 = 50%.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from volnix.core.session import (
    SeedStrategy,
    Session,
    SessionStatus,
    SessionType,
)
from volnix.core.types import ActorId, SessionId, WorldId
from volnix.persistence.manager import create_database
from volnix.sessions.store import SessionStore, SlotAssignment


async def _make_store() -> SessionStore:
    db = await create_database(":memory:", wal_mode=False)
    store = SessionStore(db)
    await store.initialize()
    return store


def _sample_session(**overrides) -> Session:
    defaults = {
        "session_id": SessionId("sess-01"),
        "world_id": WorldId("world-1"),
        "session_type": SessionType.BOUNDED,
        "seed": 42,
    }
    defaults.update(overrides)
    return Session(**defaults)


async def test_negative_get_session_missing_returns_none() -> None:
    """``get_session`` returns ``None`` for an unknown id rather
    than raising — callers compose the raise in ``SessionManager``
    where semantic context is available."""
    store = await _make_store()
    assert await store.get_session(SessionId("sess-nope")) is None


async def test_negative_list_sessions_unknown_world_returns_empty() -> None:
    """Filtering by an unknown ``world_id`` returns an empty list,
    not an error — locks the "store is a dumb bag of rows" contract."""
    store = await _make_store()
    await store.insert_session(_sample_session())
    rows = await store.list_sessions(world_id=WorldId("world-nope"))
    assert rows == []


async def test_negative_initialize_is_idempotent_across_calls() -> None:
    """Calling ``initialize`` twice must be a no-op — ``CREATE
    TABLE IF NOT EXISTS`` makes the SQL idempotent and the
    instance-level flag avoids round-trips."""
    store = await _make_store()
    # Second call: must not raise.
    await store.initialize()
    # Third call, same story.
    await store.initialize()
    # And we can still insert + read.
    await store.insert_session(_sample_session())
    got = await store.get_session(SessionId("sess-01"))
    assert got is not None


async def test_positive_insert_update_round_trip() -> None:
    """Full round-trip: insert → get → update → get equals the
    post-update shape. Locks the wire format SessionManager
    depends on."""
    store = await _make_store()
    session = _sample_session()
    await store.insert_session(session)

    got = await store.get_session(session.session_id)
    assert got is not None
    assert got.session_id == session.session_id
    assert got.status is SessionStatus.ACTIVE

    updated = session.model_copy(
        update={"status": SessionStatus.PAUSED, "updated_at": datetime.now(UTC)}
    )
    await store.update_session(updated)
    got2 = await store.get_session(session.session_id)
    assert got2 is not None
    assert got2.status is SessionStatus.PAUSED


async def test_positive_list_sessions_by_world_id_filter() -> None:
    store = await _make_store()
    await store.insert_session(_sample_session())
    await store.insert_session(
        _sample_session(
            session_id=SessionId("sess-02"),
            world_id=WorldId("world-2"),
        )
    )
    await store.insert_session(
        _sample_session(
            session_id=SessionId("sess-03"),
            world_id=WorldId("world-1"),
        )
    )
    rows = await store.list_sessions(world_id=WorldId("world-1"))
    ids = sorted(str(s.session_id) for s in rows)
    assert ids == ["sess-01", "sess-03"]


async def test_positive_pin_slot_and_list_assignments() -> None:
    store = await _make_store()
    await store.insert_session(_sample_session())
    await store.pin_slot(
        SlotAssignment(
            session_id=SessionId("sess-01"),
            slot_name="ceo",
            actor_id=ActorId("actor-A"),
            token="tok-A",
            pinned_at=datetime.now(UTC),
        )
    )
    assignments = await store.list_slot_assignments(SessionId("sess-01"))
    assert len(assignments) == 1
    assert assignments[0].actor_id == ActorId("actor-A")
    assert assignments[0].token == "tok-A"


async def test_negative_iso_required_raises_on_none() -> None:
    """Audit-fold M4: attempting to insert a Session with a
    ``None`` ``updated_at`` (bypassing the model-validator) must
    raise loudly — the column is ``NOT NULL`` and a silent
    coercion would pollute the DB."""
    store = await _make_store()
    # Construct a session then forcefully bypass the validator
    # to null out updated_at. Pydantic's frozen model rejects
    # direct mutation, so use ``model_construct`` (skips validators).
    session = Session.model_construct(
        session_id=SessionId("sess-bad"),
        world_id=WorldId("world-1"),
        session_type=SessionType.BOUNDED,
        status=SessionStatus.ACTIVE,
        seed_strategy=SeedStrategy.INHERIT,
        seed=1,
        start_tick=0,
        end_tick=None,
        created_at=datetime.now(UTC),
        updated_at=None,
        metadata={},
    )
    with pytest.raises(ValueError, match="NOT NULL"):
        await store.insert_session(session)


@pytest.mark.parametrize("invalid_type", ["weekly", "daily", ""])
async def test_negative_session_type_enum_coerced_correctly_on_read(
    invalid_type,
) -> None:
    """``_row_to_session`` calls ``SessionType(stype)`` — an
    invalid string raises ``ValueError``. Guards against a DB row
    manually edited to an unknown discriminator."""
    store = await _make_store()
    await store.insert_session(_sample_session())
    # Manually corrupt the row via raw SQL.
    await store._db.execute(
        "UPDATE sessions SET session_type=? WHERE session_id=?",
        (invalid_type, "sess-01"),
    )
    with pytest.raises((ValueError, ValidationError)):
        await store.get_session(SessionId("sess-01"))
