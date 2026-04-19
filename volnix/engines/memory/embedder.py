"""Embedder protocol + FTS5 adapter (PMF Plan Phase 4B Step 4a).

Three impls ship in total across Steps 4 and 13:
  * ``FTS5Embedder`` (this file; default, zero-dep).
  * ``SentenceTransformersEmbedder`` (Step 13; opt-in via
    ``volnix[embeddings]``).
  * ``OpenAIEmbedder`` (Step 13; opt-in via LLM router).

The ``Recall`` class (Step 5) branches on ``provider_id``:

    if embedder.provider_id == "fts5":
        await store.fts_search(...)
    else:
        # embed query + cosine against cached vectors
        ...

So ``FTS5Embedder.embed()`` is a no-op returning a single-float
vector to keep the :class:`EmbedderProtocol` surface uniform. The
actual full-text search happens inside
:class:`volnix.engines.memory.store.SQLiteMemoryStore.fts_search`.

This indirection costs one trivial class but buys a clean protocol
contract: downstream code never has to special-case "is this a real
embedder or not" — it asks the embedder for a vector and asks the
store for either FTS5 or vector-similarity retrieval separately.
"""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from volnix.llm.types import EmbeddingRequest, EmbeddingResponse, LLMUsage

__all__ = ["EmbedderProtocol", "FTS5Embedder"]


@runtime_checkable
class EmbedderProtocol(Protocol):
    """Contract every memory embedder satisfies.

    Runtime-checkable so composition + tests can verify conformance
    via ``isinstance(impl, EmbedderProtocol)`` without importing
    concrete classes.
    """

    @property
    def provider_id(self) -> str:
        """Stable identifier branched on by ``Recall``. Values:
        ``"fts5"``, ``"sentence-transformers:<model>"``,
        ``"openai:<model>"``."""
        ...

    @property
    def dimensions(self) -> int:
        """Vector dimensionality produced by :meth:`embed`. For
        ``fts5`` this is a placeholder (``1``) — vector shape is
        never read by the FTS5 retrieval path."""
        ...

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Produce embeddings for the batch in ``request.texts``.

        Implementations should preserve a 1:1 mapping between input
        texts and output vectors — ``response.vectors[i]``
        corresponds to ``request.texts[i]``.
        """
        ...


class FTS5Embedder:
    """Adapter that satisfies ``EmbedderProtocol`` for the FTS5 path.

    Produces no real vectors — returns a single-element placeholder
    per input so the protocol contract holds. The ``Recall`` class
    checks ``provider_id == "fts5"`` and dispatches to FTS5 search
    instead of reading these vectors.

    Stateless: construction has no side effects and all embed()
    calls are deterministic (same input → same output). The
    content-hash cache contract in the store depends on this.
    """

    _PROVIDER_ID: ClassVar[str] = "fts5"
    _DIM: ClassVar[int] = 1  # placeholder — never read by Recall

    @property
    def provider_id(self) -> str:
        return self._PROVIDER_ID

    @property
    def dimensions(self) -> int:
        return self._DIM

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        # Placeholder vectors — FTS5 path doesn't consume them.
        # Estimate tokens (4 chars/token rule-of-thumb) so the
        # usage aggregates indicate an "embedding" was performed —
        # BudgetEngine / UsageTracker treat FTS5 embeds as zero-cost
        # but non-zero activity.
        prompt_tokens = sum(max(1, len(t) // 4) for t in request.texts)
        return EmbeddingResponse(
            vectors=[[0.0] for _ in request.texts],
            model=self._PROVIDER_ID,
            provider=self._PROVIDER_ID,
            usage=LLMUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                total_tokens=prompt_tokens,
                cost_usd=0.0,
            ),
            latency_ms=0.0,
        )
