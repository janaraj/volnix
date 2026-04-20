"""Phase 4C Step 5 — session-type taxonomy tests.

Step 5 ships the taxonomy's PERSISTENCE + round-trip contract.
Behavioural differences (e.g., ``BOUNDED`` vs ``OPEN`` vs
``RESUMABLE`` end-condition semantics) land in Step 6 when
``SimulationRunner`` becomes session-aware.

Negative ratio: 2/3 = 66%.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from volnix.core.session import SessionStatus, SessionType
from volnix.core.types import WorldId
from volnix.persistence.manager import create_database
from volnix.sessions.manager import SessionManager
from volnix.sessions.store import SessionStore


async def _make_manager() -> SessionManager:
    db = await create_database(":memory:", wal_mode=False)
    store = SessionStore(db)
    await store.initialize()
    return SessionManager(store=store)


async def test_negative_unknown_session_type_rejected_at_start() -> None:
    """Caller passing a string outside the ``SessionType`` enum
    members gets a ``ValidationError`` at ``Session`` construction
    time."""
    mgr = await _make_manager()
    with pytest.raises(ValidationError):
        await mgr.start(
            WorldId("w-1"),
            "weekly",  # type: ignore[arg-type]
            world_seed=1,
        )


async def test_negative_resume_does_not_change_session_type(tmp_path) -> None:
    """Resuming a session must preserve its ``session_type`` —
    the type is set at start and immutable across lifecycle
    transitions. Verifies via round-trip through the store."""
    mgr = await _make_manager()
    s = await mgr.start(
        WorldId("w-1"),
        SessionType.RESUMABLE,
        world_seed=1,
    )
    await mgr.pause(s.session_id)
    resumed = await mgr.resume(s.session_id)
    assert resumed.session_type is SessionType.RESUMABLE
    # Re-read from store to confirm.
    refetched = await mgr.get_session(s.session_id)
    assert refetched.session_type is SessionType.RESUMABLE


async def test_positive_three_session_types_round_trip() -> None:
    """Each of the three session types round-trips cleanly
    through ``start → store → get_session``. Locks the wire
    format for all three."""
    mgr = await _make_manager()
    for stype in SessionType:
        s = await mgr.start(
            WorldId(f"w-{stype.value}"),
            stype,
            world_seed=1,
        )
        got = await mgr.get_session(s.session_id)
        assert got.session_type is stype
        assert got.status is SessionStatus.ACTIVE
