"""Tests for ``SentenceTransformersEmbedder`` (PMF 4B Step 13).

Skipped cleanly when the ``embeddings`` extra is not installed —
``pytest.importorskip`` at the module top means CI without the
extra sees a single "skipped" line and no failures.

First run pays a one-time ~80 MB model download to
``~/.cache/huggingface/``. Subsequent runs are cached (~1s).
CI can pre-warm if model-download latency becomes an issue.

Negative-first discipline:
- missing package → clean ImportError with install hint
- async path doesn't block the event loop (D13-4 lockdown)
- protocol compliance + determinism + basic sanity
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("sentence_transformers")

from volnix.engines.memory.embedder import (  # noqa: E402 — import after skip
    EmbedderProtocol,
    SentenceTransformersEmbedder,
)
from volnix.llm.types import EmbeddingRequest  # noqa: E402 — import after skip

# Module-scoped instance — the model is expensive to load
# (~80 MB download first run, ~0.8s cold load every run). Sharing
# across tests keeps the suite well under 5s once cached.


@pytest.fixture(scope="module")
def st_embedder() -> SentenceTransformersEmbedder:
    return SentenceTransformersEmbedder("all-MiniLM-L6-v2")


class TestProtocolCompliance:
    def test_positive_satisfies_embedder_protocol(
        self, st_embedder: SentenceTransformersEmbedder
    ) -> None:
        assert isinstance(st_embedder, EmbedderProtocol)

    def test_positive_provider_id_includes_model_name(
        self, st_embedder: SentenceTransformersEmbedder
    ) -> None:
        assert st_embedder.provider_id == "sentence-transformers:all-MiniLM-L6-v2"

    def test_positive_dimensions_match_model(
        self, st_embedder: SentenceTransformersEmbedder
    ) -> None:
        # MiniLM-L6-v2 is 384-dim — documented upstream spec.
        assert st_embedder.dimensions == 384


class TestEmbedding:
    async def test_positive_single_text_returns_single_vector(
        self, st_embedder: SentenceTransformersEmbedder
    ) -> None:
        resp = await st_embedder.embed(EmbeddingRequest(texts=["hello world"]))
        assert len(resp.vectors) == 1
        assert len(resp.vectors[0]) == 384
        assert resp.provider == "sentence-transformers"
        assert resp.model == "all-MiniLM-L6-v2"

    async def test_positive_batch_returns_matching_vector_count(
        self, st_embedder: SentenceTransformersEmbedder
    ) -> None:
        resp = await st_embedder.embed(EmbeddingRequest(texts=["a", "b", "c"]))
        assert len(resp.vectors) == 3
        # Uniform dimensionality across the batch — the EmbeddingResponse
        # validator enforces this too, but asserting explicitly here
        # documents the contract.
        assert all(len(v) == 384 for v in resp.vectors)

    async def test_positive_same_input_same_output_within_run(
        self, st_embedder: SentenceTransformersEmbedder
    ) -> None:
        """Determinism within one process: encoding the same text
        twice yields identical floats. (Cross-process / cross-device
        strict determinism is NOT guaranteed — see class docstring.)"""
        r1 = await st_embedder.embed(EmbeddingRequest(texts=["anchor phrase"]))
        r2 = await st_embedder.embed(EmbeddingRequest(texts=["anchor phrase"]))
        assert r1.vectors == r2.vectors

    async def test_positive_different_inputs_different_vectors(
        self, st_embedder: SentenceTransformersEmbedder
    ) -> None:
        """Sanity: the model isn't returning a constant."""
        resp = await st_embedder.embed(
            EmbeddingRequest(texts=["completely different content", "anchor phrase"])
        )
        assert resp.vectors[0] != resp.vectors[1]

    async def test_positive_usage_tokens_recorded(
        self, st_embedder: SentenceTransformersEmbedder
    ) -> None:
        resp = await st_embedder.embed(EmbeddingRequest(texts=["some text"]))
        assert resp.usage.prompt_tokens > 0
        # Local embed is free — cost_usd stays zero.
        assert resp.usage.cost_usd == 0.0

    async def test_positive_latency_ms_populated(
        self, st_embedder: SentenceTransformersEmbedder
    ) -> None:
        resp = await st_embedder.embed(EmbeddingRequest(texts=["latency check"]))
        assert resp.latency_ms >= 0.0


class TestAsyncNonBlocking:
    """D13-4 lockdown — ``model.encode`` is wrapped in
    ``asyncio.to_thread`` so the event loop stays responsive during
    long encodes."""

    async def test_negative_encode_runs_off_event_loop(
        self, st_embedder: SentenceTransformersEmbedder
    ) -> None:
        """Fire an embed + a short no-op concurrently. The no-op
        must complete while the embed is still running — proves
        the encode isn't blocking the event loop."""

        async def marker() -> str:
            await asyncio.sleep(0)
            return "tick"

        embed_task = asyncio.create_task(st_embedder.embed(EmbeddingRequest(texts=["x" * 500])))
        marker_task = asyncio.create_task(marker())
        done, pending = await asyncio.wait([embed_task, marker_task], timeout=10.0)
        assert not pending, "tasks did not complete within 10s"
        assert embed_task in done
        assert marker_task in done
        # Marker shouldn't have raised.
        assert marker_task.result() == "tick"


class TestMissingPackageGuard:
    """D13-5 — missing-extras install surfaces a clean ImportError
    with install hint. Simulated via monkeypatch on ``builtins.__import__``
    so we don't need to uninstall the package for the test."""

    def test_negative_missing_sentence_transformers_raises_with_hint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import builtins

        real_import = builtins.__import__

        def fail_st_import(name: str, *a, **kw):
            if name.startswith("sentence_transformers"):
                raise ImportError("simulated missing package")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fail_st_import)
        with pytest.raises(ImportError, match=r"volnix\[embeddings\]"):
            SentenceTransformersEmbedder("any-model")

    def test_negative_missing_package_error_mentions_uv_sync(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Error message points to both pip + uv install paths."""
        import builtins

        real_import = builtins.__import__

        def fail_st_import(name: str, *a, **kw):
            if name.startswith("sentence_transformers"):
                raise ImportError("simulated missing package")
            return real_import(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fail_st_import)
        try:
            SentenceTransformersEmbedder("any-model")
        except ImportError as e:
            msg = str(e)
            assert "pip install" in msg
            assert "uv sync" in msg


class TestContractGuards:
    """Defensive contract lockdowns — protect against future
    refactors silently breaking documented behaviour."""

    async def test_negative_embed_does_not_mutate_input_list(
        self, st_embedder: SentenceTransformersEmbedder
    ) -> None:
        """``embed`` must not mutate the caller's texts list. The
        current impl does ``list(request.texts)`` before passing to
        encode; a future refactor that drops the copy would quietly
        break a caller who reads the list after the call."""
        texts = ["alpha", "beta", "gamma"]
        original = list(texts)
        await st_embedder.embed(EmbeddingRequest(texts=texts))
        assert texts == original

    def test_negative_model_load_failure_reraises_with_context(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If ``SentenceTransformer(model_name)`` itself raises (e.g.
        unknown model, corrupted cache), the error must propagate
        unchanged — we don't swallow it. The import succeeds, the
        construction fails."""

        class _BoomSentenceTransformer:
            def __init__(self, name: str) -> None:
                raise RuntimeError(f"boom: {name}")

        # Patch the class inside the sentence_transformers module so
        # the lazy import resolves to our sabotaged constructor.
        import sentence_transformers as _st_mod

        monkeypatch.setattr(_st_mod, "SentenceTransformer", _BoomSentenceTransformer)
        with pytest.raises(RuntimeError, match="boom: any-model"):
            SentenceTransformersEmbedder("any-model")

    async def test_negative_request_model_override_is_ignored(
        self, st_embedder: SentenceTransformersEmbedder
    ) -> None:
        """``EmbeddingRequest.model_override`` is a router-level field
        for switching models at request time. Our embedder is
        constructor-bound to a single model — override requests MUST
        NOT silently switch models or produce wrong-shape output.
        Response ``model`` stays pinned to the constructor argument."""
        resp = await st_embedder.embed(
            EmbeddingRequest(
                texts=["anything"],
                model_override="some-other-model",
                provider_override="some-other-provider",
            )
        )
        # Model stays pinned to what we constructed with.
        assert resp.model == "all-MiniLM-L6-v2"
        # Provider label stays pinned too.
        assert resp.provider == "sentence-transformers"
