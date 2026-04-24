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
from volnix.core.types import SessionId
from volnix.engines.memory.embedder import EmbedderProtocol
from volnix.engines.memory.store import MemoryStoreProtocol
from volnix.llm.types import EmbeddingRequest

# Hybrid reranking fetches ``HYBRID_CANDIDATE_MULTIPLIER * q.top_k``
# candidates from FTS5 so the weighted rerank has room. Capped by
# ``_MAX_TOP_K`` so a caller at the upper bound can't coax a
# 3000-row scan (C2 of Steps 1-5 bug-bounty review).
HYBRID_CANDIDATE_MULTIPLIER: int = 3

# Dense-embedder candidate cap. For dense semantic / hybrid, we
# score every record owned by the actor (there's no FTS5-style
# pre-filter). Capping at ``_MAX_TOP_K`` keeps a pathological "1M
# records per actor" world from blowing up one recall call.
_DENSE_MAX_CANDIDATES: int = _MAX_TOP_K


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
        session_id: SessionId | None = None,
    ) -> MemoryRecall:
        """Route ``query`` to the right retrieval path, scoped to
        ``session_id`` (``tnl/session-scoped-memory.tnl``).

        Args:
            owner_id: scope-owner identity (actor or team).
            query: tagged union from ``core.memory_types``.
            tick: current tick, consumed only by recency-weighted
                  hybrid retrieval. Other modes ignore it.
            session_id: platform Session to scope reads to. ``None``
                reads only session-less rows; otherwise reads only
                that session's rows.

        Raises:
            NotImplementedError: for ``graph`` (Phase 4D), and for
                ``semantic``/``hybrid`` with a non-FTS5 embedder
                (Step 13).
            ValueError: unknown ``query.mode``.
        """
        mode = query.mode
        if mode == "structured":
            return await self._structured(owner_id, query, session_id=session_id)
        if mode == "temporal":
            return await self._temporal(owner_id, query, session_id=session_id)
        if mode == "semantic":
            return await self._semantic(owner_id, query, session_id=session_id)
        if mode == "importance":
            return await self._importance(owner_id, query, session_id=session_id)
        if mode == "hybrid":
            return await self._hybrid(owner_id, query, tick=tick, session_id=session_id)
        if mode == "graph":
            return await self._graph(owner_id, query)
        raise ValueError(f"unknown MemoryQuery.mode: {mode!r}")

    # ------------------------------------------------------------------
    # Mode implementations
    # ------------------------------------------------------------------

    async def _structured(
        self,
        owner_id: str,
        q: StructuredQuery,
        *,
        session_id: SessionId | None = None,
    ) -> MemoryRecall:
        """Tag-filter over semantic records. Returns every match
        (no ``top_k`` on this mode) so ``truncated`` is always False.
        """
        semantic_records = await self._store.list_by_owner(
            owner_id, kind="semantic", session_id=session_id
        )
        matched = [r for r in semantic_records if all(k in r.tags for k in q.keys)]
        matched.sort(key=lambda r: (-r.importance, r.record_id))
        return MemoryRecall(
            query_id=f"structured:{':'.join(q.keys)}",
            records=matched,
            total_matched=len(matched),
            truncated=False,
        )

    async def _temporal(
        self,
        owner_id: str,
        q: TemporalQuery,
        *,
        session_id: SessionId | None = None,
    ) -> MemoryRecall:
        """Tick-window filter, newest-first. Truncates to ``q.limit``."""
        all_records = await self._store.list_by_owner(owner_id, session_id=session_id)
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

    async def _semantic(
        self,
        owner_id: str,
        q: SemanticQuery,
        *,
        session_id: SessionId | None = None,
    ) -> MemoryRecall:
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
            hits = await self._store.fts_search(owner_id, q.text, q.top_k, session_id=session_id)
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

        # Dense-embedder path (PMF 4B Step 13). Cosine-similarity
        # scoring with the embedding cache populated on-miss.
        scored = await self._dense_score(owner_id, q.text, session_id=session_id)
        # Filter by min_score threshold.
        filtered = [(r, s) for r, s in scored if s >= q.min_score]
        # Sort: similarity DESC, record_id ASC tie-break.
        filtered.sort(key=lambda p: (-p[1], p[0].record_id))
        total = len(filtered)
        records = [r for r, _ in filtered[: q.top_k]]
        return MemoryRecall(
            query_id=f"semantic:{self._embedder.provider_id}:{content_hash_of(q.text)[:8]}",
            records=records,
            total_matched=total,
            truncated=len(records) < total,
        )

    async def _importance(
        self,
        owner_id: str,
        q: ImportanceQuery,
        *,
        session_id: SessionId | None = None,
    ) -> MemoryRecall:
        """Threshold-filter + importance-sort + top_k truncation."""
        all_records = await self._store.list_by_owner(owner_id, session_id=session_id)
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

    async def _hybrid(
        self,
        owner_id: str,
        q: HybridQuery,
        *,
        tick: int,
        session_id: SessionId | None = None,
    ) -> MemoryRecall:
        """Weighted combo: semantic + recency + importance.

        FTS5 path: candidates fetched at ``HYBRID_CANDIDATE_MULTIPLIER *
        top_k`` for reranking, clamped to ``_MAX_TOP_K`` (C2 of the
        bug-bounty review). BM25 scores flipped + rescaled to [0, 1].

        Dense path (PMF 4B Step 13): cosine-similarity over all
        owner records (capped at ``_DENSE_MAX_CANDIDATES``). Already
        on [0, 1] — no normalisation needed. Combined with recency +
        importance the same way as the FTS5 path.

        Each signal normalised to ``[0, 1]`` before the weighted
        sum; weights don't need to sum to 1.
        """
        query_id = f"hybrid:{self._embedder.provider_id}:{content_hash_of(q.semantic_text)[:8]}"

        # Fetch candidate (record, semantic_score) pairs — path-specific.
        if self._embedder.provider_id == "fts5":
            candidate_k = min(q.top_k * HYBRID_CANDIDATE_MULTIPLIER, _MAX_TOP_K)
            raw_hits = await self._store.fts_search(
                owner_id, q.semantic_text, candidate_k, session_id=session_id
            )
            if not raw_hits:
                return MemoryRecall(
                    query_id=query_id,
                    records=[],
                    total_matched=0,
                    truncated=False,
                )
            scores = [s for _, s in raw_hits]
            min_s, max_s = min(scores), max(scores)

            def _sem_norm(s: float) -> float:
                if min_s == max_s:
                    return 1.0
                return (max_s - s) / (max_s - min_s)

            normalised = [(r, _sem_norm(s)) for r, s in raw_hits]
        else:
            # Dense path. Cosine is already in [-1, 1] (normalised
            # to [0, 1] by the scoring helper). No min/max rescale
            # needed. Candidate cap = _DENSE_MAX_CANDIDATES.
            normalised = await self._dense_score(owner_id, q.semantic_text, session_id=session_id)
            if not normalised:
                return MemoryRecall(
                    query_id=query_id,
                    records=[],
                    total_matched=0,
                    truncated=False,
                )

        # Recency: 1 / (1 + age_in_ticks). Current-tick records
        # score 1.0; unbounded age decays toward 0.
        def _rec_norm(r: MemoryRecord) -> float:
            age = max(0, tick - r.created_tick)
            return 1.0 / (1.0 + age)

        combined: list[tuple[MemoryRecord, float]] = [
            (
                r,
                q.semantic_weight * sem
                + q.recency_weight * _rec_norm(r)
                + q.importance_weight * r.importance,
            )
            for r, sem in normalised
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

    async def _dense_score(
        self,
        owner_id: str,
        query_text: str,
        *,
        session_id: SessionId | None = None,
    ) -> list[tuple[MemoryRecord, float]]:
        """Embed ``query_text`` + every candidate record for
        ``(owner_id, session_id)``; return
        ``[(record, cosine_sim_in_0_1), ...]``.

        Record embeddings are cached in the store's ``embedding_cache``
        keyed by ``(content_hash, provider_id)`` — first recall pays
        the embed cost, subsequent recalls hit the cache. The cache
        is intentionally content-hash-keyed, not session-keyed, so
        identical content across sessions shares one cached vector.

        Batch-embeds cache misses in a single call (ST + OpenAI both
        handle batches natively, much faster than per-text calls).

        Cosine similarity is rescaled from ``[-1, 1]`` to ``[0, 1]``
        so ``min_score`` thresholds and ``HybridQuery`` weights
        compose cleanly.
        """
        import numpy as np  # numpy ships with sentence-transformers

        records = await self._store.list_by_owner(
            owner_id, limit=_DENSE_MAX_CANDIDATES, session_id=session_id
        )
        if not records:
            return []

        provider_id = self._embedder.provider_id

        # Load cached vectors; collect cache misses for batch embed.
        cached_vectors: dict[int, list[float]] = {}
        miss_indices: list[int] = []
        miss_texts: list[str] = []
        for i, r in enumerate(records):
            blob = await self._store.embedding_cache_get(r.content_hash, provider_id)
            if blob is not None:
                cached_vectors[i] = np.frombuffer(blob, dtype=np.float32).tolist()
            else:
                miss_indices.append(i)
                miss_texts.append(r.content)

        # Batch-embed any misses in one call + populate cache.
        if miss_texts:
            resp = await self._embedder.embed(EmbeddingRequest(texts=miss_texts))
            for local_i, vec in zip(miss_indices, resp.vectors, strict=True):
                cached_vectors[local_i] = vec
                blob = np.asarray(vec, dtype=np.float32).tobytes()
                await self._store.embedding_cache_put(
                    records[local_i].content_hash, provider_id, blob
                )

        # Embed the query (separately — not cached since queries are
        # typically one-shot and rarely repeat byte-for-byte).
        q_resp = await self._embedder.embed(EmbeddingRequest(texts=[query_text]))
        q_vec = np.asarray(q_resp.vectors[0], dtype=np.float32)
        q_norm = float(np.linalg.norm(q_vec))
        if q_norm == 0.0:
            # Degenerate zero-vector query — no meaningful similarity.
            return [(r, 0.0) for r in records]

        # Compute cosine for every record, rescaled to [0, 1].
        scored: list[tuple[MemoryRecord, float]] = []
        for i, r in enumerate(records):
            v = np.asarray(cached_vectors[i], dtype=np.float32)
            v_norm = float(np.linalg.norm(v))
            if v_norm == 0.0:
                scored.append((r, 0.0))
                continue
            cos = float(np.dot(q_vec, v) / (q_norm * v_norm))
            # Rescale [-1, 1] → [0, 1].
            score = (cos + 1.0) / 2.0
            scored.append((r, score))
        return scored

    async def _graph(self, owner_id: str, q: GraphQuery) -> MemoryRecall:
        """Graph traversal — Phase 4D. G11: fail fast, don't silently
        return empty."""
        raise NotImplementedError(
            f"Graph query mode lands in Phase 4D. "
            f"Requested entity={q.entity!r} depth={q.depth} "
            f"(scope={owner_id!r})."
        )
