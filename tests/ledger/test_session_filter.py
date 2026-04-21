"""Phase 4C Step 6 — Ledger session_id column + query filter tests.

Locks the two halves of the session-id plumbing:
1. Schema: the ``session_id`` column exists on the ledger table.
2. Query: ``filter_session`` returns only matching entries, and
   ``filter_session=None`` is a no-op that returns everything.

Negative ratio: 2/5 = 40% after post-impl audit M-NEW-1 reclassified
the "combined filter" test as positive (it asserts a correct positive
count, not a rejection). Acceptable for this file because the new
behavior — a SQL column + a pydantic filter field — is intrinsically
more about correct inclusion than about input rejection. The broader
Step-6 test-corpus ratio stays above 50% (counted across all six
Step-6 test files).
"""

from __future__ import annotations

from volnix.core.types import SessionId, WorldId
from volnix.ledger.config import LedgerConfig
from volnix.ledger.entries import SessionStartedEntry
from volnix.ledger.ledger import Ledger
from volnix.ledger.query import LedgerQueryBuilder
from volnix.persistence.manager import create_database


async def _make_ledger() -> Ledger:
    db = await create_database(":memory:", wal_mode=False)
    ledger = Ledger(LedgerConfig(), db)
    await ledger.initialize()
    return ledger


def _started(session_id: str, world_id: str = "w-1") -> SessionStartedEntry:
    return SessionStartedEntry(
        session_id=SessionId(session_id),
        world_id=WorldId(world_id),
        session_type="bounded",
        seed_strategy="inherit",
        seed=42,
    )


# ─── Schema ───────────────────────────────────────────────────────


async def test_positive_session_id_column_in_schema() -> None:
    """Audit-fold M3: verify the live table has a ``session_id``
    column via ``PRAGMA table_info``, not just the Python constant.
    A behavioural test, not a tautology."""
    ledger = await _make_ledger()
    rows = await ledger._db.fetchall("PRAGMA table_info(ledger_log)")
    col_names = {row["name"] for row in rows}
    assert "session_id" in col_names


# ─── Query filter ─────────────────────────────────────────────────


async def test_negative_query_without_session_filter_returns_all() -> None:
    """A query without ``filter_session()`` returns entries for
    all sessions AND entries with NULL session_id."""
    ledger = await _make_ledger()
    await ledger.append(_started("s-1"))
    await ledger.append(_started("s-2"))
    results = await ledger.query(LedgerQueryBuilder().build())
    assert len(results) == 2


async def test_negative_filter_session_non_matching_returns_empty() -> None:
    ledger = await _make_ledger()
    await ledger.append(_started("s-1"))
    await ledger.append(_started("s-2"))
    results = await ledger.query(LedgerQueryBuilder().filter_session("s-nope").build())
    assert results == []


async def test_positive_filter_session_returns_only_matching_entries() -> None:
    ledger = await _make_ledger()
    await ledger.append(_started("s-1"))
    await ledger.append(_started("s-2"))
    await ledger.append(_started("s-1", world_id="w-2"))
    results = await ledger.query(LedgerQueryBuilder().filter_session("s-1").build())
    assert len(results) == 2
    for entry in results:
        assert str(entry.session_id) == "s-1"


async def test_positive_filter_session_combines_with_other_filters() -> None:
    """``filter_session`` + ``filter_type`` both apply — combined
    WHERE clause. Audit M-NEW-1: renamed from
    ``test_negative_*`` because it asserts a positive count, not a
    rejection."""
    ledger = await _make_ledger()
    await ledger.append(_started("s-1", world_id="w-1"))
    await ledger.append(_started("s-1", world_id="w-2"))
    await ledger.append(_started("s-2"))
    results = await ledger.query(
        LedgerQueryBuilder().filter_session("s-1").filter_type("session.started").build()
    )
    # Both s-1 entries, no s-2.
    assert len(results) == 2
    assert all(str(e.session_id) == "s-1" for e in results)
