"""Phase 4C Step 6 — BusPersistence session_id column + filter.

Locks parity with the ledger: events stamped with session_id
persist it in the indexed column, and ``query_by_session`` /
``query(session_id=...)`` returns only matching rows.

Negative ratio: 2/5 = 40% after post-impl audit M-NEW-1 — see
``test_session_filter.py`` header for the rationale. Step-6 test
corpus ratio stays above 50% across all six files.
"""

from __future__ import annotations

from datetime import UTC, datetime

from volnix.bus.persistence import BusPersistence
from volnix.core.events import Event
from volnix.core.types import SessionId, Timestamp
from volnix.persistence.manager import create_database


async def _make_persistence() -> BusPersistence:
    db = await create_database(":memory:", wal_mode=False)
    bp = BusPersistence(db)
    await bp.initialize()
    return bp


def _event(
    event_type: str = "t",
    session_id: SessionId | None = None,
) -> Event:
    return Event(
        event_type=event_type,
        timestamp=Timestamp(
            world_time=datetime.now(UTC),
            wall_time=datetime.now(UTC),
            tick=0,
        ),
        session_id=session_id,
    )


async def test_negative_session_id_column_in_schema() -> None:
    bp = await _make_persistence()
    rows = await bp._db.fetchall("PRAGMA table_info(event_log)")
    col_names = {row["name"] for row in rows}
    assert "session_id" in col_names


async def test_negative_event_without_session_id_persists_null() -> None:
    bp = await _make_persistence()
    await bp.persist(_event(session_id=None))
    rows = await bp._db.fetchall("SELECT session_id FROM event_log")
    assert len(rows) == 1
    assert rows[0]["session_id"] is None


async def test_positive_event_with_session_id_persists_and_reads_back() -> None:
    bp = await _make_persistence()
    await bp.persist(_event(session_id=SessionId("s-1")))
    rows = await bp._db.fetchall("SELECT session_id FROM event_log")
    assert rows[0]["session_id"] == "s-1"


async def test_positive_query_by_session_returns_only_matching() -> None:
    bp = await _make_persistence()
    await bp.persist(_event(event_type="a", session_id=SessionId("s-1")))
    await bp.persist(_event(event_type="b", session_id=SessionId("s-2")))
    await bp.persist(_event(event_type="c", session_id=None))
    matches = await bp.query_by_session("s-1")
    assert len(matches) == 1
    assert matches[0].event_type == "a"


async def test_positive_query_with_session_and_event_types_both_apply() -> None:
    """Combined filter: session_id AND event_type both filter the
    result. Audit M-NEW-1: renamed from ``test_negative_*`` — it
    asserts a correct positive count, not a rejection."""
    bp = await _make_persistence()
    await bp.persist(_event(event_type="target", session_id=SessionId("s-1")))
    await bp.persist(_event(event_type="other", session_id=SessionId("s-1")))
    await bp.persist(_event(event_type="target", session_id=SessionId("s-2")))
    matches = await bp.query(event_types=["target"], session_id="s-1")
    assert len(matches) == 1
    assert matches[0].event_type == "target"
    assert matches[0].session_id == SessionId("s-1")
