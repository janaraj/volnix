"""Retrieval-mode dispatcher for the Memory Engine (Phase 4B Step 5).

Consumes :class:`MemoryStoreProtocol` and :class:`EmbedderProtocol`
and translates :class:`MemoryQuery` tagged-union variants into the
right retrieval call. Stateless — the caller (Step 7's MemoryEngine)
passes ``tick`` when recency matters.

Dispatches:
    * ``structured`` — tag-filter over semantic records, sorted by
      importance DESC + record_id ASC.
    * ``temporal``   — tick-window filter, sorted newest-first with
      record_id ASC tie-break.
    * ``semantic``   — FTS5 path via ``store.fts_search`` when
      ``embedder.provider_id == "fts5"``; dense-embedder path raises
      NotImplementedError (Step 13 implements).
    * ``importance`` — filter by ``min_importance`` threshold, sort
      importance DESC.
    * ``hybrid``     — weighted combo of semantic + recency +
      importance. FTS5 branch normalises bm25 by observed min/max;
      dense branch raises (Step 13).
    * ``graph``      — raises NotImplementedError. Phase 4D will
      provide the entity-relationship traversal.

Every list-returning path sorts with a deterministic tie-break on
``record_id`` so same-seed replay produces identical ordering.
"""

from __future__ import annotations

from volnix.core.memory_types import (
    _MAX_TOP_K,
    GraphQuery,
    HybridQuery,
    ImportanceQuery,
    MemoryQuery,
    MemoryRecall,
    MemoryRecord,
    SemanticQuery,
    StructuredQuery,
    TemporalQuery,
    content_hash_of,
)
from volnix.engines.memory.embedder import EmbedderProtocol
from volnix.engines.memory.store import MemoryStoreProtocol

# Hybrid reranking fetches ``HYBRID_CANDIDATE_MULTIPLIER * q.top_k``
# candidates from FTS5 so the weighted rerank has room. Capped by
# ``_MAX_TOP_K`` so a caller at the upper bound can't coax a
# 3000-row scan (C2 of Steps 1-5 bug-bounty review).
HYBRID_CANDIDATE_MULTIPLIER: int = 3


class Recall:
    """Stateless retrieval dispatcher."""

    def __init__(
        self,
        *,
        store: MemoryStoreProtocol,
        embedder: EmbedderProtocol,
    ) -> None:
        self._store = store
        self._embedder = embedder

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def dispatch(
        self,
        owner_id: str,
        query: MemoryQuery,
        *,
        tick: int = 0,
    ) -> MemoryRecall:
        """Route ``query`` to the right retrieval path.

        Args:
            owner_id: scope-owner identity (actor or team).
            query: tagged union from ``core.memory_types``.
            tick: current tick, consumed only by recency-weighted
                  hybrid retrieval. Other modes ignore it.

        Raises:
            NotImplementedError: for ``graph`` (Phase 4D), and for
                ``semantic``/``hybrid`` with a non-FTS5 embedder
                (Step 13).
            ValueError: unknown ``query.mode``.
        """
        mode = query.mode
        if mode == "structured":
            return await self._structured(owner_id, query)
        if mode == "temporal":
            return await self._temporal(owner_id, query)
        if mode == "semantic":
            return await self._semantic(owner_id, query)
        if mode == "importance":
            return await self._importance(owner_id, query)
        if mode == "hybrid":
            return await self._hybrid(owner_id, query, tick=tick)
        if mode == "graph":
            return await self._graph(owner_id, query)
        raise ValueError(f"unknown MemoryQuery.mode: {mode!r}")

    # ------------------------------------------------------------------
    # Mode implementations
    # ------------------------------------------------------------------

    async def _structured(self, owner_id: str, q: StructuredQuery) -> MemoryRecall:
        """Tag-filter over semantic records. Returns every match
        (no ``top_k`` on this mode) so ``truncated`` is always False.
        """
        semantic_records = await self._store.list_by_owner(owner_id, kind="semantic")
        matched = [r for r in semantic_records if all(k in r.tags for k in q.keys)]
        matched.sort(key=lambda r: (-r.importance, r.record_id))
        return MemoryRecall(
            query_id=f"structured:{':'.join(q.keys)}",
            records=matched,
            total_matched=len(matched),
            truncated=False,
        )

    async def _temporal(self, owner_id: str, q: TemporalQuery) -> MemoryRecall:
        """Tick-window filter, newest-first. Truncates to ``q.limit``."""
        all_records = await self._store.list_by_owner(owner_id)
        filtered = [
            r
            for r in all_records
            if r.created_tick >= q.tick_start
            and (q.tick_end is None or r.created_tick <= q.tick_end)
        ]
        filtered.sort(key=lambda r: (-r.created_tick, r.record_id))
        total = len(filtered)
        records = filtered[: q.limit]
        return MemoryRecall(
            query_id=f"temporal:{q.tick_start}-{q.tick_end}",
            records=records,
            total_matched=total,
            truncated=len(records) < total,
        )

    async def _semantic(self, owner_id: str, q: SemanticQuery) -> MemoryRecall:
        """Dispatches on embedder provider.

        FTS5: calls ``store.fts_search``. ``min_score`` is **not**
        meaningful on this path — BM25 scores are unbounded and
        negative-is-better, so a user-supplied ``[0.0, 1.0]`` floor
        has no sensible mapping. Rather than silently ignore it
        (C1 of the bug-bounty review), we raise so callers surface
        the contract mismatch. Step 13's dense-embedder path
        honours ``min_score`` cleanly and removes this raise.

        Dense embedders: Step 13.
        """
        if self._embedder.provider_id == "fts5":
            if q.min_score > 0.0:
                raise ValueError(
                    "SemanticQuery.min_score is not supported on the "
                    "FTS5 path (BM25 scores are unbounded — no "
                    "meaningful [0,1] threshold). Pass min_score=0.0 "
                    "or use a dense embedder (Step 13+)."
                )
            hits = await self._store.fts_search(owner_id, q.text, q.top_k)
            records = [r for r, _score in hits]
            return MemoryRecall(
                query_id=f"semantic:fts5:{content_hash_of(q.text)[:8]}",
                records=records,
                # We don't know total_matched beyond top_k from FTS5 —
                # report what we returned. Truncation signal is
                # implicit (fewer callers care about "how many more
                # are there" for FTS5 than for dense).
                total_matched=len(records),
                truncated=False,
            )
        raise NotImplementedError(
            f"semantic retrieval with embedder "
            f"{self._embedder.provider_id!r} lands in Step 13. "
            f"Phase 4B Step 5 ships FTS5 only."
        )

    async def _importance(self, owner_id: str, q: ImportanceQuery) -> MemoryRecall:
        """Threshold-filter + importance-sort + top_k truncation."""
        all_records = await self._store.list_by_owner(owner_id)
        filtered = [r for r in all_records if r.importance >= q.min_importance]
        filtered.sort(key=lambda r: (-r.importance, r.record_id))
        total = len(filtered)
        records = filtered[: q.top_k]
        return MemoryRecall(
            query_id=f"importance:{q.min_importance:.3f}",
            records=records,
            total_matched=total,
            truncated=len(records) < total,
        )

    async def _hybrid(self, owner_id: str, q: HybridQuery, *, tick: int) -> MemoryRecall:
        """Weighted combo: semantic + recency + importance.

        Semantic candidates fetched from FTS5 at ``HYBRID_CANDIDATE_MULTIPLIER *
        top_k`` to give room for reranking, **clamped to
        ``_MAX_TOP_K``** (C2 of the bug-bounty review — at the upper
        ``top_k=1000`` bound a naive ``3*top_k=3000`` call bypasses
        the structural cap). Each signal normalised to ``[0, 1]``
        before the weighted sum; weights don't need to sum to 1.
        """
        if self._embedder.provider_id != "fts5":
            raise NotImplementedError(
                f"hybrid retrieval with embedder {self._embedder.provider_id!r} lands in Step 13."
            )

        candidate_k = min(q.top_k * HYBRID_CANDIDATE_MULTIPLIER, _MAX_TOP_K)
        raw_hits = await self._store.fts_search(owner_id, q.semantic_text, candidate_k)
        query_id = f"hybrid:{content_hash_of(q.semantic_text)[:8]}"
        if not raw_hits:
            return MemoryRecall(
                query_id=query_id,
                records=[],
                total_matched=0,
                truncated=False,
            )

        # Normalise semantic scores. BM25: lower == better match.
        # Flip sign and rescale to [0, 1] over observed min/max.
        scores = [s for _, s in raw_hits]
        min_s, max_s = min(scores), max(scores)

        def _sem_norm(s: float) -> float:
            if min_s == max_s:
                return 1.0
            return (max_s - s) / (max_s - min_s)

        # Recency: 1 / (1 + age_in_ticks). Current-tick records
        # score 1.0; unbounded age decays toward 0.
        def _rec_norm(r: MemoryRecord) -> float:
            age = max(0, tick - r.created_tick)
            return 1.0 / (1.0 + age)

        combined: list[tuple[MemoryRecord, float]] = [
            (
                r,
                q.semantic_weight * _sem_norm(s)
                + q.recency_weight * _rec_norm(r)
                + q.importance_weight * r.importance,
            )
            for r, s in raw_hits
        ]
        # Sort: combined score DESC, record_id ASC for tie-break.
        combined.sort(key=lambda p: (-p[1], p[0].record_id))
        total = len(combined)
        records = [r for r, _ in combined[: q.top_k]]
        return MemoryRecall(
            query_id=query_id,
            records=records,
            total_matched=total,
            truncated=len(records) < total,
        )

    async def _graph(self, owner_id: str, q: GraphQuery) -> MemoryRecall:
        """Graph traversal — Phase 4D. G11: fail fast, don't silently
        return empty."""
        raise NotImplementedError(
            f"Graph query mode lands in Phase 4D. "
            f"Requested entity={q.entity!r} depth={q.depth} "
            f"(scope={owner_id!r})."
        )
