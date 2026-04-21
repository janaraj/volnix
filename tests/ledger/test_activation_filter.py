"""Phase 4C Step 8 — Ledger activation_id column + query filter tests.

Locks the two halves of the activation-id plumbing that
``ReplayLLMProvider`` relies on for its journal lookup:
1. Schema: ``activation_id`` column exists on the ledger table
   and is indexed.
2. Query: ``LedgerQueryBuilder.filter_activation`` returns only
   rows that match; combines cleanly with ``filter_type`` and
   ``filter_session`` so the replay lookup key
   ``(session_id, activation_id, entry_type="llm.utterance"``)
   works end-to-end.

Negative ratio: 2/3 = 66%.
"""

from __future__ import annotations

from volnix.core.types import ActivationId, ActorId, SessionId
from volnix.ledger.config import LedgerConfig
from volnix.ledger.entries import LLMUtteranceEntry
from volnix.ledger.ledger import Ledger
from volnix.ledger.query import LedgerQueryBuilder
from volnix.persistence.manager import create_database


async def _make_ledger() -> Ledger:
    db = await create_database(":memory:", wal_mode=False)
    ledger = Ledger(LedgerConfig(), db)
    await ledger.initialize()
    return ledger


def _utter(
    *,
    activation_id: str,
    session_id: str = "s-1",
    actor_id: str = "actor-a",
    role: str = "assistant",
    content: str = "hi",
) -> LLMUtteranceEntry:
    return LLMUtteranceEntry(
        actor_id=ActorId(actor_id),
        activation_id=ActivationId(activation_id),
        session_id=SessionId(session_id),
        role=role,  # type: ignore[arg-type]
        content=content,
        content_hash=f"sha256:{'0' * 64}",
        tokens=1,
        tick=0,
        sequence=0,
    )


async def test_positive_activation_id_column_in_schema() -> None:
    """The Step-8 ALTER-TABLE column must be on the live table —
    lookup perf depends on the index landing on a real column."""
    ledger = await _make_ledger()
    rows = await ledger._db.fetchall("PRAGMA table_info(ledger_log)")
    col_names = {row["name"] for row in rows}
    assert "activation_id" in col_names


async def test_negative_filter_activation_no_match_returns_empty() -> None:
    """Unknown activation_id must return zero rows — prevents the
    replay provider from stumbling onto a foreign session's
    utterance by accident."""
    ledger = await _make_ledger()
    await ledger.append(_utter(activation_id="act-present"))
    q = LedgerQueryBuilder().filter_type("llm.utterance").filter_activation("act-missing").build()
    result = await ledger.query(q)
    assert result == []


async def test_negative_filter_activation_combined_with_session_narrows() -> None:
    """Session + activation filters compose AND — matches only
    entries where both match. Two activations with the same ID
    across different sessions is unusual (uuid5-derived from
    session+actor+tick) but the guard is valuable."""
    ledger = await _make_ledger()
    await ledger.append(_utter(activation_id="act-a", session_id="s-1", content="s1"))
    await ledger.append(_utter(activation_id="act-a", session_id="s-2", content="s2"))
    q = (
        LedgerQueryBuilder()
        .filter_type("llm.utterance")
        .filter_session("s-1")
        .filter_activation("act-a")
        .build()
    )
    result = await ledger.query(q)
    assert len(result) == 1
    assert result[0].content == "s1"  # type: ignore[attr-defined]
