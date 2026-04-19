"""Unit tests for EmbedderProtocol + FTS5Embedder (Phase 4B Step 4a).

Negative-case first, uniform-dim check, protocol conformance.
The FTS5Embedder is deliberately minimal — the real search happens
in the store. These tests lock in the adapter contract.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from volnix.engines.memory.embedder import EmbedderProtocol, FTS5Embedder
from volnix.llm.types import EmbeddingRequest


class TestEmbedderProtocol:
    def test_fts5_satisfies_protocol(self) -> None:
        assert isinstance(FTS5Embedder(), EmbedderProtocol)

    def test_fts5_provider_id_is_fts5_string(self) -> None:
        # The exact string matters — Recall (Step 5) branches on it.
        # Any rename here must ripple there.
        assert FTS5Embedder().provider_id == "fts5"

    def test_fts5_dimensions_is_placeholder_one(self) -> None:
        # 1 is the documented placeholder (Recall skips vector
        # math when provider_id == "fts5"; this dim is never read
        # for retrieval but may appear in diagnostic output).
        assert FTS5Embedder().dimensions == 1


class TestFts5EmbedderEmbed:
    async def test_negative_empty_request_rejected_by_request_validator(
        self,
    ) -> None:
        # EmbeddingRequest itself rejects empty lists; embedder
        # never sees one. Locks in the layered-validation contract.
        with pytest.raises(ValidationError):
            EmbeddingRequest(texts=[])

    async def test_returns_placeholder_vector_per_text(self) -> None:
        emb = FTS5Embedder()
        r = await emb.embed(EmbeddingRequest(texts=["a", "b", "c"]))
        assert len(r.vectors) == 3
        for v in r.vectors:
            assert v == [0.0]

    async def test_provider_field_in_response(self) -> None:
        emb = FTS5Embedder()
        r = await emb.embed(EmbeddingRequest(texts=["hi"]))
        assert r.provider == "fts5"

    async def test_model_field_is_fts5(self) -> None:
        # Not a real model, but the field must be populated so the
        # ledger/tracker round-trip doesn't carry empty strings.
        emb = FTS5Embedder()
        r = await emb.embed(EmbeddingRequest(texts=["hi"]))
        assert r.model == "fts5"

    async def test_usage_records_nonzero_prompt_tokens(self) -> None:
        # Even though we don't really tokenise, the usage estimator
        # must produce a plausible token count so budget aggregates
        # reflect that an "embedding" was performed.
        emb = FTS5Embedder()
        r = await emb.embed(EmbeddingRequest(texts=["hello world"]))
        assert r.usage.prompt_tokens >= 1
        assert r.usage.completion_tokens == 0
        assert r.error is None


class TestDeterminism:
    async def test_same_input_same_output_across_instances(self) -> None:
        # FTS5Embedder has no state; two instances must produce the
        # identical EmbeddingResponse for identical inputs (the
        # content-hash cache contract relies on this).
        a = await FTS5Embedder().embed(EmbeddingRequest(texts=["hi"]))
        b = await FTS5Embedder().embed(EmbeddingRequest(texts=["hi"]))
        assert a.vectors == b.vectors
        assert a.provider == b.provider
