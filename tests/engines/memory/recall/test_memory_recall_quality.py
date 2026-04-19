"""Recall-quality harness for the memory engine (Phase 4B Step 4b).

Runs the domain-neutral corpus against whichever embedder the
conftest parametrises in, measures recall@5 per category, and
asserts each category meets a per-embedder threshold.

Design:
- Thresholds live in a single ``THRESHOLDS`` dict. Edits are
  reviewable, diff-able, and blamable.
- Scope-isolation gets a hard-equality check on top of the
  threshold — no cross-owner leak is ever acceptable.
- Precision@5 and MRR have per-category floors too, so we don't
  accidentally regress from "good recall, garbage ranking" to
  "good recall, garbage ranking but somehow passes."
- A meta-test verifies THRESHOLDS covers every category the
  corpus exercises — prevents silent-drop-of-category bug.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.engines.memory.recall.metrics import (
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
)

# The 9 categories the corpus exercises. Kept explicit so a category
# rename in the corpus without a test update fails the meta-test.
CATEGORIES: tuple[str, ...] = (
    "exact_keyword",
    "morphological",
    "multi_keyword",
    "case_folding",
    "diacritics",
    "punctuation",
    "paraphrase",
    "synonym",
    "scope_isolation",
)

# The contract. Any change here requires a test commit.
# Keys: (category, embedder_id) -> minimum recall@5 threshold.
THRESHOLDS: dict[tuple[str, str], float] = {
    ("exact_keyword", "fts5"): 1.00,
    ("morphological", "fts5"): 0.90,
    ("multi_keyword", "fts5"): 0.80,
    ("case_folding", "fts5"): 1.00,
    ("diacritics", "fts5"): 0.90,
    ("punctuation", "fts5"): 0.80,
    ("paraphrase", "fts5"): 0.10,
    ("synonym", "fts5"): 0.00,  # zero-overlap expected; documented baseline
    ("scope_isolation", "fts5"): 1.00,
    # Step 13 appends ("<category>", "sentence-transformers") entries here
    # — same 9 categories, higher thresholds on paraphrase + synonym.
}

# Precision@5 floor — broad, category-agnostic. Any category whose
# recall passes should also show non-zero precision unless we've
# over-scoped relevant_ids.
PRECISION_FLOOR: dict[tuple[str, str], float] = {
    ("exact_keyword", "fts5"): 0.20,  # at least 1 in 5 is relevant
    ("morphological", "fts5"): 0.15,
    ("multi_keyword", "fts5"): 0.15,
    ("case_folding", "fts5"): 0.20,
    ("diacritics", "fts5"): 0.15,
    ("punctuation", "fts5"): 0.15,
    ("paraphrase", "fts5"): 0.00,  # documented weakness
    ("synonym", "fts5"): 0.00,
    ("scope_isolation", "fts5"): 0.20,
}


async def _retrieved_for_query(store, query: dict[str, Any]) -> list[str]:
    """Shared helper — fetch top-5 result IDs in retrieval order."""
    hits = await store.fts_search(query["owner_id"], query["text"], top_k=5)
    return [str(r.record_id) for r, _ in hits]


# ---------------------------------------------------------------------------
# Meta — coverage invariants over the corpus + thresholds
# ---------------------------------------------------------------------------


class TestCorpusCoverage:
    """Catch coverage drops that would otherwise silently skip a
    category. If someone removes all queries of a category or
    forgets to add a THRESHOLD entry, these tests flag it."""

    def test_every_category_has_queries(self, corpus) -> None:
        for cat in CATEGORIES:
            hits = [q for q in corpus["queries"] if q["category"] == cat]
            assert hits, f"corpus has zero queries in category {cat!r}"

    def test_thresholds_cover_every_category_fts5(self) -> None:
        for cat in CATEGORIES:
            assert (cat, "fts5") in THRESHOLDS, f"THRESHOLDS missing ('{cat}', 'fts5')"

    def test_precision_floor_matches_thresholds_keys(self) -> None:
        assert set(PRECISION_FLOOR) == set(THRESHOLDS), (
            "PRECISION_FLOOR and THRESHOLDS must cover identical keys"
        )

    def test_corpus_only_uses_declared_categories(self, corpus) -> None:
        # Typo-in-category would otherwise silently drop queries.
        for q in corpus["queries"]:
            assert q["category"] in CATEGORIES, (
                f"query {q['id']}: unknown category {q['category']!r}"
            )


# ---------------------------------------------------------------------------
# Recall@5 per category (parametrised)
# ---------------------------------------------------------------------------


class TestRecallByCategory:
    @pytest.mark.parametrize("category", CATEGORIES)
    async def test_category_meets_recall_threshold(self, seeded_store, corpus, category) -> None:
        store, embedder_id = seeded_store
        queries = [q for q in corpus["queries"] if q["category"] == category]
        recalls: list[float] = []
        for q in queries:
            retrieved = await _retrieved_for_query(store, q)
            relevant = set(q["relevant_ids"])
            recalls.append(recall_at_k(retrieved, relevant, 5))
        mean = sum(recalls) / len(recalls)
        threshold = THRESHOLDS[(category, embedder_id)]
        assert mean >= threshold, (
            f"[{embedder_id}] {category} mean recall@5 = {mean:.3f} < "
            f"threshold {threshold:.3f}. Per-query: "
            f"{list(zip([q['id'] for q in queries], recalls))}"
        )


# ---------------------------------------------------------------------------
# Precision@5 per category
# ---------------------------------------------------------------------------


class TestPrecisionByCategory:
    @pytest.mark.parametrize("category", CATEGORIES)
    async def test_category_meets_precision_floor(self, seeded_store, corpus, category) -> None:
        store, embedder_id = seeded_store
        queries = [q for q in corpus["queries"] if q["category"] == category]
        precisions: list[float] = []
        for q in queries:
            retrieved = await _retrieved_for_query(store, q)
            relevant = set(q["relevant_ids"])
            precisions.append(precision_at_k(retrieved, relevant, 5))
        mean = sum(precisions) / len(precisions)
        floor = PRECISION_FLOOR[(category, embedder_id)]
        assert mean >= floor, (
            f"[{embedder_id}] {category} mean precision@5 = {mean:.3f} < "
            f"floor {floor:.3f}. Per-query: "
            f"{list(zip([q['id'] for q in queries], precisions))}"
        )


# ---------------------------------------------------------------------------
# MRR — strong-signal categories only
# ---------------------------------------------------------------------------


# Strong-signal categories — FTS5 is expected to rank relevant hits
# high. Paraphrase/synonym are excluded because MRR=0 on miss would
# pass trivially there.
_MRR_CATEGORIES: tuple[str, ...] = (
    "exact_keyword",
    "multi_keyword",
    "case_folding",
    "diacritics",
)
_MRR_FLOOR = 0.50  # first hit should land on average in top 2


class TestMrrForStrongSignalCategories:
    """MRR for categories FTS5 is supposed to handle well. For
    paraphrase/synonym we don't assert MRR — they're expected to
    miss entirely and MRR = 0 on miss would pass trivially."""

    @pytest.mark.parametrize("category", _MRR_CATEGORIES)
    async def test_mrr_at_least_half(self, seeded_store, corpus, category) -> None:
        store, embedder_id = seeded_store
        queries = [q for q in corpus["queries"] if q["category"] == category]
        rrs: list[float] = []
        for q in queries:
            retrieved = await _retrieved_for_query(store, q)
            relevant = set(q["relevant_ids"])
            rrs.append(mean_reciprocal_rank(retrieved, relevant))
        mean = sum(rrs) / len(rrs)
        assert mean >= _MRR_FLOOR, (
            f"[{embedder_id}] {category} MRR = {mean:.3f} < "
            f"{_MRR_FLOOR:.3f}. Per-query: "
            f"{list(zip([q['id'] for q in queries], rrs))}"
        )


# ---------------------------------------------------------------------------
# Scope isolation — HARD check, no cross-owner leak ever
# ---------------------------------------------------------------------------


class TestScopeIsolationHard:
    """Category 9 also needs a hard check — no cross-owner result
    may ever appear. ``>=`` threshold is insufficient; use exact
    equality on leak count. Any failure here is a P0 bug."""

    async def test_zero_cross_owner_leak(self, seeded_store, corpus) -> None:
        store, _ = seeded_store
        for q in corpus["queries"]:
            if q["category"] != "scope_isolation":
                continue
            hits = await store.fts_search(q["owner_id"], q["text"], top_k=5)
            for rec, _ in hits:
                assert rec.owner_id == q["owner_id"], (
                    f"LEAK: query {q['id']} for owner {q['owner_id']} "
                    f"returned record {rec.record_id} belonging to "
                    f"{rec.owner_id}"
                )


# ---------------------------------------------------------------------------
# Determinism — identical corpus + query must produce identical result
# ---------------------------------------------------------------------------


class TestHarnessDeterminism:
    async def test_same_query_returns_identical_order(self, seeded_store, corpus) -> None:
        store, _ = seeded_store
        sample = corpus["queries"][0]
        first = await _retrieved_for_query(store, sample)
        second = await _retrieved_for_query(store, sample)
        assert first == second, (
            f"Non-deterministic retrieval for {sample['id']!r}: {first} vs {second}"
        )
