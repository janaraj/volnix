"""Embedder protocol + concrete adapters (PMF Plan Phase 4B Steps 4 + 13).

Two impls ship in 4B:
  * ``FTS5Embedder`` (default, zero-dep) — Step 4.
  * ``SentenceTransformersEmbedder`` (opt-in via
    ``volnix[embeddings]``) — Step 13.

OpenAI embedder is intentionally deferred (no concrete caller; revisit
if an API-backed embedder earns its place).

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

import asyncio
import time
from typing import ClassVar, Protocol, runtime_checkable

from volnix.llm.types import EmbeddingRequest, EmbeddingResponse, LLMUsage

__all__ = ["EmbedderProtocol", "FTS5Embedder", "SentenceTransformersEmbedder"]


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


class SentenceTransformersEmbedder:
    """Dense embedder backed by the ``sentence-transformers`` library
    (PMF Plan Phase 4B Step 13).

    Opt-in via ``pip install volnix[embeddings]``. The package is not
    imported until construction — importing this module without the
    extra installed is fine; *instantiating* this class is what
    triggers the import.

    **Determinism caveat (D13-6):** SentenceTransformers output is
    deterministic for the same (model, input, device) tuple, but
    byte-level drift between CPU/GPU or across torch versions is
    possible. The memory-engine use case cares about rank-stability
    (similarity ordering), which SentenceTransformers preserves.
    Strict byte-identical two-run replay remains the ``FTS5Embedder``
    path's guarantee, not this one.

    The blocking ``model.encode()`` call is wrapped in
    ``asyncio.to_thread`` (D13-4) so the event loop stays responsive
    during long encodes — ST is CPU/GPU-bound synchronous code and
    calling it directly from an async path would block every
    coroutine for ~10–100ms per request.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        try:
            # Lazy import (D13-2): keeps base ``volnix`` install
            # dep-free. Extras-missing error caught below.
            from sentence_transformers import (  # type: ignore[import-untyped]
                SentenceTransformer,
            )
        except ImportError as e:
            raise ImportError(
                "SentenceTransformersEmbedder requires the "
                "`sentence-transformers` package. Install via "
                "`pip install volnix[embeddings]` or "
                "`uv sync --extra embeddings`."
            ) from e
        self._model_name = model_name
        self._model = SentenceTransformer(model_name)
        self._dim = int(self._model.get_sentence_embedding_dimension())
        self._provider_id = f"sentence-transformers:{model_name}"

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def dimensions(self) -> int:
        return self._dim

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        start = time.monotonic()
        # D13-4: wrap the synchronous encode() in ``asyncio.to_thread``
        # so the event loop stays responsive. D13-9: batch in one call.
        # D13-10: show_progress_bar=False keeps CI clean;
        # convert_to_numpy=True gives cheap .tolist() for serialisation.
        vectors = await asyncio.to_thread(
            self._model.encode,
            list(request.texts),
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        latency_ms = (time.monotonic() - start) * 1000.0
        prompt_tokens = sum(max(1, len(t) // 4) for t in request.texts)
        return EmbeddingResponse(
            vectors=[row.tolist() for row in vectors],
            model=self._model_name,
            provider="sentence-transformers",
            usage=LLMUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                total_tokens=prompt_tokens,
                cost_usd=0.0,
            ),
            latency_ms=latency_ms,
        )
