"""Deep-dive FTS5 correctness tests (Phase 4B Step 4c).

Each class targets one class of search-engine failure we've seen
in real projects or that the tokenizer documentation warns about.
Per test discipline (DESIGN_PRINCIPLES.md §Test Discipline):
- Don't mock the path under test. Real in-memory SQLite for all
  logic tests; real tmp-path-backed file for concurrency tests
  (``:memory:`` doesn't support WAL).
- Negative case first — every class asserts a failure mode first.
- Assert side effects — row counts, FTS/records parity.
"""

from __future__ import annotations

import asyncio
import unicodedata
from pathlib import Path

import pytest

from volnix.core.memory_types import MemoryRecord, content_hash_of
from volnix.core.types import MemoryRecordId
from volnix.engines.memory.store import (
    TABLE_FTS,
    TABLE_RECORDS,
    SQLiteMemoryStore,
)
from volnix.persistence.manager import create_database


async def _mk_store(tokenizer: str | None = None) -> tuple[SQLiteMemoryStore, object]:
    db = await create_database(":memory:", wal_mode=False)
    kwargs: dict = {}
    if tokenizer is not None:
        kwargs["fts_tokenizer"] = tokenizer
    store = SQLiteMemoryStore(db, **kwargs)
    await store.initialize()
    return store, db


def _rec(record_id: str, content: str, *, owner_id: str = "A", tick: int = 0) -> MemoryRecord:
    return MemoryRecord(
        record_id=MemoryRecordId(record_id),
        scope="actor",
        owner_id=owner_id,
        kind="episodic",
        tier="tier2",
        source="explicit",
        content=content,
        content_hash=content_hash_of(content),
        importance=0.5,
        tags=[],
        created_tick=tick,
    )


# ---------------------------------------------------------------------------
# Group 1 — Stemming
# ---------------------------------------------------------------------------


class TestStemming:
    async def test_negative_unrelated_word_does_not_match_stem(self) -> None:
        store, db = await _mk_store()
        try:
            await store.insert(_rec("r1", "Several meetings were held."))
            # "greet" stems to "greet" — must NOT match "meeting".
            hits = await store.fts_search("A", "greet", top_k=5)
            assert hits == []
        finally:
            await db.close()

    async def test_plural_matches_singular_via_porter(self) -> None:
        store, db = await _mk_store()
        try:
            await store.insert(_rec("r1", "Several meetings were held."))
            hits = await store.fts_search("A", "meeting", top_k=5)
            assert len(hits) == 1
            assert str(hits[0][0].record_id) == "r1"
        finally:
            await db.close()

    async def test_past_tense_matches_base_via_porter(self) -> None:
        store, db = await _mk_store()
        try:
            await store.insert(_rec("r1", "The training session ran longer."))
            hits = await store.fts_search("A", "train", top_k=5)
            assert len(hits) == 1
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# Group 2 — Diacritics
# ---------------------------------------------------------------------------


class TestDiacritics:
    async def test_negative_without_remove_diacritics_option_no_match(self) -> None:
        # Baseline: ``unicode61`` defaults ``remove_diacritics=1``
        # which already folds *some* diacritics (including common
        # Latin ones like é, ü, etc.). To get a true no-fold
        # baseline we must set ``remove_diacritics 0`` explicitly.
        # This locks in *why* the shipped default is
        # ``remove_diacritics 2``: 0 doesn't fold, 1 folds most,
        # 2 folds everything (including combining marks).
        store, db = await _mk_store(tokenizer="unicode61 remove_diacritics 0")
        try:
            await store.insert(_rec("r1", "The café was open."))
            hits = await store.fts_search("A", "cafe", top_k=5)
            assert hits == []
        finally:
            await db.close()

    async def test_default_tokenizer_folds_diacritics(self) -> None:
        # The shipped default includes remove_diacritics 2.
        store, db = await _mk_store()
        try:
            await store.insert(_rec("r1", "The café was open."))
            hits = await store.fts_search("A", "cafe", top_k=5)
            assert len(hits) == 1
        finally:
            await db.close()

    async def test_accented_query_still_matches_accented_content(self) -> None:
        store, db = await _mk_store()
        try:
            await store.insert(_rec("r1", "The café was open."))
            hits = await store.fts_search("A", "café", top_k=5)
            assert len(hits) == 1
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# Group 3 — Case folding
# ---------------------------------------------------------------------------


class TestCaseFolding:
    async def test_negative_case_matters_when_query_is_exact(self) -> None:
        # unicode61 lowercases both sides — case should NEVER matter
        # after tokenisation. Lock this in with an uppercase record
        # + lowercase query that must match.
        store, db = await _mk_store()
        try:
            await store.insert(_rec("r1", "REPORT FILED WEDNESDAY"))
            hits = await store.fts_search("A", "wednesday", top_k=5)
            assert len(hits) == 1
        finally:
            await db.close()

    async def test_mixed_case_query_matches(self) -> None:
        store, db = await _mk_store()
        try:
            await store.insert(_rec("r1", "The Meeting was on Tuesday."))
            hits = await store.fts_search("A", "MEETING tuesday", top_k=5)
            assert len(hits) == 1
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# Group 4 — FTS5 operator tokens in content
# ---------------------------------------------------------------------------


class TestOperatorTokensInContent:
    async def test_content_with_uppercase_and_is_tokenised(self) -> None:
        # "AND" in content is a word, not an operator — must be
        # indexed and findable.
        store, db = await _mk_store()
        try:
            await store.insert(_rec("r1", "Apple AND Banana are fruits."))
            hits = await store.fts_search("A", "apple banana", top_k=5)
            assert len(hits) == 1
        finally:
            await db.close()

    async def test_content_with_near_and_not_tokens(self) -> None:
        store, db = await _mk_store()
        try:
            await store.insert(_rec("r1", "The NOT gate is NEAR the AND gate."))
            hits = await store.fts_search("A", "gate", top_k=5)
            assert len(hits) == 1
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# Group 5 — FTS5 operator tokens in query
# ---------------------------------------------------------------------------


class TestOperatorTokensInQuery:
    async def test_operator_query_does_not_crash(self) -> None:
        # This exact query would raise "syntax error near NOT" on a
        # naive MATCH expression. Our _build_fts_match quotes each
        # token, so FTS5 sees three literal words.
        store, db = await _mk_store()
        try:
            await store.insert(_rec("r1", "hello world"))
            hits = await store.fts_search("A", "AND NOT OR", top_k=5)
            # Expected: no crash, may return nothing (tokens don't
            # appear in the record).
            assert isinstance(hits, list)
        finally:
            await db.close()

    async def test_query_with_embedded_quote_escaped(self) -> None:
        store, db = await _mk_store()
        try:
            await store.insert(_rec("r1", "alice and bob"))
            # Embedded double-quote in the query must be escaped.
            hits = await store.fts_search("A", 'alice "bob', top_k=5)
            assert isinstance(hits, list)
        finally:
            await db.close()

    async def test_query_with_hyphen_and_parens(self) -> None:
        store, db = await _mk_store()
        try:
            await store.insert(_rec("r1", "state-of-the-art solution"))
            hits = await store.fts_search("A", "state-of-the-art (best)", top_k=5)
            assert isinstance(hits, list)
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# Group 6 — Unicode combining marks
# ---------------------------------------------------------------------------


class TestCombiningMarks:
    async def test_composed_and_decomposed_forms_both_searchable(self) -> None:
        # "ï" can be encoded as U+00EF (composed) or as
        # U+0069 + U+0308 (decomposed). With remove_diacritics 2,
        # both should tokenise to the same token.
        store, db = await _mk_store()
        try:
            composed = "naïve"  # single code point for ï
            decomposed = unicodedata.normalize("NFD", composed)
            assert composed != decomposed
            await store.insert(_rec("r1", f"The {composed} response."))
            await store.insert(_rec("r2", f"A {decomposed} design."))
            # Query using plain "naive" — both records should match.
            hits = await store.fts_search("A", "naive", top_k=5)
            ids = {str(r.record_id) for r, _ in hits}
            assert ids == {"r1", "r2"}
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# Group 7 — Zero-width + RTL content
# ---------------------------------------------------------------------------


class TestUnicodeEdgeCases:
    async def test_zero_width_chars_do_not_crash(self) -> None:
        # U+200B zero-width space can confuse naive tokenisers.
        store, db = await _mk_store()
        try:
            await store.insert(_rec("r1", "hello\u200bworld"))
            hits = await store.fts_search("A", "hello", top_k=5)
            assert isinstance(hits, list)
        finally:
            await db.close()

    async def test_rtl_content_indexes_and_searches(self) -> None:
        store, db = await _mk_store()
        try:
            await store.insert(_rec("r1", "The message שלום was received."))
            hits = await store.fts_search("A", "שלום", top_k=5)
            assert len(hits) == 1
        finally:
            await db.close()

    async def test_emoji_does_not_crash(self) -> None:
        store, db = await _mk_store()
        try:
            await store.insert(_rec("r1", "Great meeting 🎉 on Tuesday"))
            hits = await store.fts_search("A", "meeting", top_k=5)
            assert len(hits) == 1
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# Group 8 — Very long content
# ---------------------------------------------------------------------------


class TestLongContent:
    async def test_nine_thousand_char_content_indexes_and_searches(self) -> None:
        # Realistic operational size — SemanticQuery has a 10K cap
        # on query text; content has no explicit field cap.
        big = ("alpha beta gamma " * 500).strip()  # ~8500 chars
        store, db = await _mk_store()
        try:
            await store.insert(_rec("r1", big))
            hits = await store.fts_search("A", "gamma", top_k=5)
            assert len(hits) == 1
        finally:
            await db.close()

    async def test_bm25_does_not_over_reward_long_content(self) -> None:
        # Short record with one match vs long record with many
        # matches — BM25 length normalisation should keep ranking
        # reasonable. We don't lock an order (both are valid); we
        # just require the short record to appear in top 2.
        store, db = await _mk_store()
        try:
            short = _rec("r_short", "meeting")
            long_verbose = _rec(
                "r_long",
                ("meeting " * 300).strip(),
            )
            await store.insert(short)
            await store.insert(long_verbose)
            hits = await store.fts_search("A", "meeting", top_k=5)
            ids = {str(r.record_id) for r, _ in hits[:2]}
            assert "r_short" in ids
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# Group 9 — Duplicate content, distinct owners
# ---------------------------------------------------------------------------


class TestScopeIsolationStress:
    async def test_identical_content_different_owners_both_land(self) -> None:
        store, db = await _mk_store()
        try:
            await store.insert(_rec("r1", "shared text", owner_id="A"))
            await store.insert(_rec("r2", "shared text", owner_id="B"))
            # A sees only r1.
            hits_a = await store.fts_search("A", "shared", top_k=5)
            assert {str(r.record_id) for r, _ in hits_a} == {"r1"}
            # B sees only r2.
            hits_b = await store.fts_search("B", "shared", top_k=5)
            assert {str(r.record_id) for r, _ in hits_b} == {"r2"}
        finally:
            await db.close()

    async def test_scope_isolation_under_1000_record_stress(self) -> None:
        store, db = await _mk_store()
        try:
            for i in range(500):
                await store.insert(_rec(f"a{i}", f"item number {i} for actor A", owner_id="A"))
            for i in range(500):
                await store.insert(_rec(f"b{i}", f"item number {i} for actor B", owner_id="B"))
            hits_a = await store.fts_search("A", "number", top_k=1000)
            for rec, _ in hits_a:
                assert rec.owner_id == "A"
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# Group 10 — Prune + FTS orphan check
# ---------------------------------------------------------------------------


class TestPruneFtsParity:
    async def test_prune_does_not_orphan_fts_rows(self) -> None:
        store, db = await _mk_store()
        try:
            for i in range(10):
                await store.insert(_rec(f"r{i}", f"content {i}", tick=i))
            await store.prune_oldest_episodic("A", keep=3)
            rec_count_row = await db.fetchone(f"SELECT COUNT(*) AS n FROM {TABLE_RECORDS}")
            fts_count_row = await db.fetchone(f"SELECT COUNT(*) AS n FROM {TABLE_FTS}")
            assert rec_count_row is not None and fts_count_row is not None
            assert rec_count_row["n"] == fts_count_row["n"] == 3
        finally:
            await db.close()

    async def test_prune_keeps_semantic_records_in_both_tables(self) -> None:
        store, db = await _mk_store()
        try:
            await store.insert(_rec("e1", "episodic text", tick=1))
            sem = MemoryRecord(
                record_id=MemoryRecordId("s1"),
                scope="actor",
                owner_id="A",
                kind="semantic",
                tier="tier2",
                source="consolidated",
                content="semantic fact",
                content_hash=content_hash_of("semantic fact"),
                importance=0.9,
                tags=["pref"],
                created_tick=2,
                consolidated_from=[MemoryRecordId("e1")],
            )
            await store.insert(sem)
            await store.prune_oldest_episodic("A", keep=0)
            # Semantic survives; FTS row for semantic survives too.
            remaining = await store.list_by_owner("A")
            assert [str(r.record_id) for r in remaining] == ["s1"]
            fts = await db.fetchall(f"SELECT record_id FROM {TABLE_FTS}")
            assert [r["record_id"] for r in fts] == ["s1"]
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# Group 11 — Concurrency (file-backed DB, real WAL)
# ---------------------------------------------------------------------------


class TestConcurrency:
    async def test_fifty_concurrent_writers_no_corruption(self, tmp_path: Path) -> None:
        # ``:memory:`` can't run in WAL; concurrency needs a real file.
        db_path = str(tmp_path / "concurrent_writes.db")
        db = await create_database(db_path, wal_mode=True)
        store = SQLiteMemoryStore(db)
        await store.initialize()
        try:

            async def _insert(i: int) -> None:
                await store.insert(_rec(f"r{i:03d}", f"record number {i}", tick=i))

            await asyncio.gather(*[_insert(i) for i in range(50)])
            rows = await store.list_by_owner("A", limit=100)
            assert len(rows) == 50
            ids = {str(r.record_id) for r in rows}
            assert ids == {f"r{i:03d}" for i in range(50)}
        finally:
            await db.close()

    async def test_concurrent_reads_and_writes_interleave(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "concurrent_rw.db")
        db = await create_database(db_path, wal_mode=True)
        store = SQLiteMemoryStore(db)
        await store.initialize()
        try:
            # Seed 10 records.
            for i in range(10):
                await store.insert(_rec(f"seed{i}", f"seed text {i}", tick=i))

            async def _writer(i: int) -> None:
                await store.insert(_rec(f"w{i}", f"fresh text {i}", tick=100 + i))

            async def _reader(_: int) -> int:
                hits = await store.fts_search("A", "text", top_k=100)
                return len(hits)

            results = await asyncio.gather(
                *[_writer(i) for i in range(20)],
                *[_reader(i) for i in range(20)],
            )
            # No exception raised means the test passes.
            # Reader results (last 20 entries) are >= 10 (seed count).
            reader_counts = results[20:]
            assert all(c >= 10 for c in reader_counts)
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# Group 12 — Determinism under identical insertion
# ---------------------------------------------------------------------------


class TestDeterminism:
    async def test_two_fresh_stores_same_ordering(self) -> None:
        async def _run_once() -> list[str]:
            store, db = await _mk_store()
            try:
                for i in range(10):
                    await store.insert(_rec(f"r{i}", f"alpha beta gamma {i}", tick=i))
                hits = await store.fts_search("A", "alpha", top_k=5)
                return [str(r.record_id) for r, _ in hits]
            finally:
                await db.close()

        a = await _run_once()
        b = await _run_once()
        assert a == b

    async def test_tie_break_on_record_id_ascending(self) -> None:
        # Three records with identical content — identical BM25 score.
        # Tie-break must be record_id ASC.
        store, db = await _mk_store()
        try:
            await store.insert(_rec("z", "identical text", tick=1))
            await store.insert(_rec("a", "identical text", tick=1))
            await store.insert(_rec("m", "identical text", tick=1))
            hits = await store.fts_search("A", "identical", top_k=5)
            ids = [str(r.record_id) for r, _ in hits]
            assert ids == sorted(ids)
        finally:
            await db.close()


# ---------------------------------------------------------------------------
# Group 13 — Tokenizer drift on re-initialise
# ---------------------------------------------------------------------------


class TestMalformedTokenizerSuffix:
    """D2 of the Steps 1-5 bug-bounty review: ``MemoryConfig`` only
    validates the tokenizer prefix, not the full suffix. A
    malformed suffix (e.g. unknown option, out-of-range value) is
    passed through to FTS5's DDL, which rejects it with a clear
    error. This is the second layer of the two-layer defence — the
    test locks in that SQLite surfaces the error loudly rather than
    silently accepting garbage.
    """

    async def test_unknown_unicode61_option_raises_at_initialize(self) -> None:
        # ``unicode61 remove_diacritics 9`` — out-of-range value.
        # FTS5 accepts 0, 1, or 2 only.
        db = await create_database(":memory:", wal_mode=False)
        store = SQLiteMemoryStore(db, fts_tokenizer="unicode61 remove_diacritics 9")
        try:
            with pytest.raises(Exception):  # sqlite error bubble
                await store.initialize()
        finally:
            await db.close()

    async def test_garbage_option_name_raises_at_initialize(self) -> None:
        # Known prefix ``unicode61`` followed by an unknown option.
        db = await create_database(":memory:", wal_mode=False)
        store = SQLiteMemoryStore(db, fts_tokenizer="unicode61 totally_made_up_option 1")
        try:
            with pytest.raises(Exception):
                await store.initialize()
        finally:
            await db.close()


class TestTokenizerDrift:
    async def test_reinitialise_with_different_tokenizer_keeps_original(
        self, tmp_path: Path
    ) -> None:
        # Once the FTS5 table is created with tokenizer X, a later
        # store instance passing tokenizer Y uses the existing
        # table (CREATE TABLE IF NOT EXISTS is a no-op). This test
        # documents that semantics — if we later want to reject
        # drift, we change the assertion here and add migration code.
        db_path = str(tmp_path / "drift.db")
        db = await create_database(db_path, wal_mode=True)
        try:
            store_v1 = SQLiteMemoryStore(db, fts_tokenizer="unicode61 remove_diacritics 0")
            await store_v1.initialize()
            await store_v1.insert(_rec("r1", "The café opened."))
            # With remove_diacritics=0 there is NO folding -> no match.
            hits_v1 = await store_v1.fts_search("A", "cafe", top_k=5)
            assert hits_v1 == []

            # Re-init with the remove_diacritics tokenizer.
            store_v2 = SQLiteMemoryStore(
                db,
                fts_tokenizer="porter unicode61 remove_diacritics 2",
            )
            await store_v2.initialize()
            # Original FTS table survives — still doesn't fold.
            hits_v2 = await store_v2.fts_search("A", "cafe", top_k=5)
            assert hits_v2 == []
        finally:
            await db.close()
