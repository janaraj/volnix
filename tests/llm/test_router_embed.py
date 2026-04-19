"""Tests for LLMRouter.embed and embedding-provider surface (Phase 4B Step 3.5).

Per test discipline (DESIGN_PRINCIPLES.md §Test Discipline):
- Negative cases first on every validator and routing path.
- Don't mock the path under test — the router, tracker, and providers
  under test are used directly; only the LLM API boundary itself is
  mocked via MockLLMProvider / TestingFakeProvider.
- Observability asserted — every path that reaches a tracker has an
  assertion on what the tracker recorded.
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import pytest
from pydantic import ValidationError

from volnix.llm.config import LLMConfig, LLMProviderEntry, LLMRoutingEntry
from volnix.llm.provider import LLMProvider
from volnix.llm.providers.mock import MockLLMProvider
from volnix.llm.registry import ProviderRegistry
from volnix.llm.router import LLMRouter
from volnix.llm.tracker import UsageTracker
from volnix.llm.types import (
    EmbeddingRequest,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
    LLMUsage,
)

# ---------------------------------------------------------------------------
# EmbeddingRequest / EmbeddingResponse type tests
# ---------------------------------------------------------------------------


class TestEmbeddingRequest:
    def test_negative_empty_texts_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EmbeddingRequest(texts=[])

    def test_negative_empty_string_input_rejected(self) -> None:
        with pytest.raises(ValidationError, match="non-empty string"):
            EmbeddingRequest(texts=["hello", ""])

    def test_negative_over_length_input_rejected(self) -> None:
        with pytest.raises(ValidationError, match="10000"):
            EmbeddingRequest(texts=["x" * 10_001])

    def test_negative_oversized_batch_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EmbeddingRequest(texts=["x"] * 257)

    def test_positive_single_text(self) -> None:
        r = EmbeddingRequest(texts=["hello"])
        assert r.texts == ["hello"]
        assert r.model_override is None

    def test_positive_batch_of_256(self) -> None:
        # Upper bound must be accepted inclusive.
        r = EmbeddingRequest(texts=["x"] * 256)
        assert len(r.texts) == 256


class TestEmbeddingResponse:
    def test_negative_mixed_dimensionality_rejected(self) -> None:
        with pytest.raises(ValidationError, match="expected"):
            EmbeddingResponse(vectors=[[1.0, 2.0], [3.0]])

    def test_positive_empty_vectors_on_error(self) -> None:
        # Error path must be representable — empty vectors + error message.
        r = EmbeddingResponse(vectors=[], model="m", provider="p", error="boom")
        assert r.vectors == []
        assert r.error == "boom"

    def test_positive_uniform_dimensions(self) -> None:
        r = EmbeddingResponse(vectors=[[1.0, 2.0], [3.0, 4.0]])
        assert len(r.vectors) == 2


# ---------------------------------------------------------------------------
# Provider ABC default behavior
# ---------------------------------------------------------------------------


class _BareProvider(LLMProvider):
    """Provider that implements only ``generate`` — ``embed`` falls
    through to the ABC default."""

    provider_name: ClassVar[str] = "bare"

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content="bare")


class TestProviderDefaultEmbed:
    async def test_default_embed_raises_not_implemented(self) -> None:
        provider = _BareProvider()
        with pytest.raises(NotImplementedError, match="does not support embeddings"):
            await provider.embed(EmbeddingRequest(texts=["x"]))

    async def test_error_message_names_the_provider(self) -> None:
        provider = _BareProvider()
        with pytest.raises(NotImplementedError, match="bare"):
            await provider.embed(EmbeddingRequest(texts=["x"]))


# ---------------------------------------------------------------------------
# MockLLMProvider.embed — deterministic vectors
# ---------------------------------------------------------------------------


class TestMockEmbed:
    async def test_same_text_same_vector(self) -> None:
        provider = MockLLMProvider()
        r = await provider.embed(EmbeddingRequest(texts=["hello", "hello"]))
        assert r.error is None
        assert r.vectors[0] == r.vectors[1]

    async def test_different_text_different_vector(self) -> None:
        provider = MockLLMProvider()
        r = await provider.embed(EmbeddingRequest(texts=["hello", "world"]))
        assert r.vectors[0] != r.vectors[1]

    async def test_vectors_are_unit_normalised(self) -> None:
        # Unit norm simplifies cosine similarity downstream; the
        # mock documents this contract, so we lock it in.
        provider = MockLLMProvider()
        r = await provider.embed(EmbeddingRequest(texts=["hello"]))
        norm = sum(x * x for x in r.vectors[0]) ** 0.5
        assert 0.999 < norm < 1.001

    async def test_usage_reports_prompt_tokens(self) -> None:
        provider = MockLLMProvider()
        r = await provider.embed(EmbeddingRequest(texts=["a" * 40]))
        # ~10 tokens at 4 chars/token
        assert r.usage.prompt_tokens >= 1
        assert r.usage.completion_tokens == 0

    async def test_model_override_respected(self) -> None:
        provider = MockLLMProvider()
        r = await provider.embed(
            EmbeddingRequest(texts=["x"], model_override="custom-mock")
        )
        assert r.model == "custom-mock"

    async def test_default_model_when_no_override(self) -> None:
        provider = MockLLMProvider()
        r = await provider.embed(EmbeddingRequest(texts=["x"]))
        assert r.model == "mock-embed-1"


# ---------------------------------------------------------------------------
# LLMRouter.embed — routing + retry + tracker
# ---------------------------------------------------------------------------


def _make_router(
    routing: dict[str, LLMRoutingEntry] | None = None,
    tracker: UsageTracker | None = None,
    provider: LLMProvider | None = None,
    provider_name: str = "mock",
) -> LLMRouter:
    config = LLMConfig(
        defaults=LLMProviderEntry(type=provider_name, default_model="mock-embed-1"),
        providers={provider_name: LLMProviderEntry(type=provider_name)},
        routing=routing or {},
    )
    registry = ProviderRegistry()
    registry.register(provider_name, provider or MockLLMProvider())
    return LLMRouter(config=config, registry=registry, tracker=tracker)


class TestRouterEmbedRouting:
    async def test_defaults_when_no_routing(self) -> None:
        router = _make_router()
        r = await router.embed(EmbeddingRequest(texts=["hi"]), engine_name="memory")
        assert r.error is None
        assert r.provider == "mock"

    async def test_routing_entry_selects_model(self) -> None:
        router = _make_router(
            routing={"memory_embed": LLMRoutingEntry(provider="mock", model="mock-embed-v2")}
        )
        r = await router.embed(
            EmbeddingRequest(texts=["hi"]), engine_name="memory", use_case="embed"
        )
        assert r.model == "mock-embed-v2"

    async def test_request_model_override_wins(self) -> None:
        router = _make_router(
            routing={"memory_embed": LLMRoutingEntry(provider="mock", model="mock-embed-v2")}
        )
        r = await router.embed(
            EmbeddingRequest(texts=["hi"], model_override="per-request-model"),
            engine_name="memory",
            use_case="embed",
        )
        assert r.model == "per-request-model"

    async def test_negative_unknown_provider_raises_key_error(self) -> None:
        # Router points at provider that isn't registered.
        router = _make_router(
            routing={"x_embed": LLMRoutingEntry(provider="nonexistent")},
            provider_name="mock",
        )
        with pytest.raises(KeyError, match="nonexistent"):
            await router.embed(
                EmbeddingRequest(texts=["hi"]),
                engine_name="x",
                use_case="embed",
            )


class TestRouterEmbedNotImplemented:
    async def test_not_implemented_surfaces_as_error_no_retry(self) -> None:
        # Provider that raises NotImplementedError — should NOT retry.
        # Retry on transient errors only; no-impl is config bug.
        start_calls = 0

        class _CountingNoEmbed(_BareProvider):
            async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
                nonlocal start_calls
                start_calls += 1
                raise NotImplementedError("nope")

        router = _make_router(provider=_CountingNoEmbed())
        r = await router.embed(EmbeddingRequest(texts=["hi"]), engine_name="memory")
        assert r.error is not None
        assert "NotImplementedError" in r.error
        assert start_calls == 1  # NOT retried


class TestRouterEmbedRetry:
    async def test_transient_error_retried_then_succeeds(self) -> None:
        # First call returns transient, second succeeds.
        class _FlakyProvider(_BareProvider):
            def __init__(self) -> None:
                self.calls = 0

            async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
                self.calls += 1
                if self.calls == 1:
                    return EmbeddingResponse(
                        vectors=[], model="x", provider="flaky",
                        error="rate limit hit",
                    )
                return EmbeddingResponse(
                    vectors=[[0.1, 0.2]] * len(request.texts),
                    model="x", provider="flaky",
                )

        flaky = _FlakyProvider()
        router = _make_router(provider=flaky)
        r = await router.embed(EmbeddingRequest(texts=["a"]), engine_name="memory")
        assert r.error is None
        assert flaky.calls == 2

    async def test_non_transient_error_not_retried(self) -> None:
        class _OneShotFailProvider(_BareProvider):
            def __init__(self) -> None:
                self.calls = 0

            async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
                self.calls += 1
                return EmbeddingResponse(
                    vectors=[], model="x", provider="oneshot",
                    error="400 Bad Request: invalid input",
                )

        one = _OneShotFailProvider()
        router = _make_router(provider=one)
        r = await router.embed(EmbeddingRequest(texts=["a"]), engine_name="memory")
        assert r.error == "400 Bad Request: invalid input"
        assert one.calls == 1

    async def test_timeout_surfaces_as_error(self) -> None:
        # Provider hangs beyond timeout — router maps to a clean error.
        class _HangProvider(_BareProvider):
            async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
                await asyncio.sleep(60)
                return EmbeddingResponse(vectors=[])

        router = _make_router(provider=_HangProvider())
        # Force short timeout via config
        router._config = router._config.model_copy(
            update={
                "defaults": router._config.defaults.model_copy(
                    update={"timeout_seconds": 0.05}
                ),
                "max_retries": 0,
            }
        )
        r = await router.embed(EmbeddingRequest(texts=["a"]), engine_name="memory")
        assert r.error is not None
        assert "timed out" in r.error


class TestRouterEmbedTracker:
    async def test_tracker_records_embedding_usage(self) -> None:
        tracker = UsageTracker()
        router = _make_router(tracker=tracker)
        await router.embed(
            EmbeddingRequest(texts=["hello world"]),
            engine_name="memory",
            use_case="embed",
        )
        usage = await tracker.get_usage_by_engine("memory")
        assert usage.prompt_tokens > 0
        assert usage.completion_tokens == 0

    async def test_tracker_sums_across_multiple_calls(self) -> None:
        tracker = UsageTracker()
        router = _make_router(tracker=tracker)
        for _ in range(3):
            await router.embed(
                EmbeddingRequest(texts=["hi"]), engine_name="memory"
            )
        usage = await tracker.get_usage_by_engine("memory")
        # 3 calls, each ≥1 token
        assert usage.prompt_tokens >= 3


class TestTrackerRecordEmbedding:
    """UsageTracker.record_embedding writes to ledger symmetrically
    with record() — G10 of the gap analysis (unified budget accounting)."""

    async def test_ledger_receives_llm_call_entry_for_embedding(self) -> None:
        class _LedgerStub:
            def __init__(self) -> None:
                self.entries: list[Any] = []

            async def append(self, entry: Any) -> int:
                self.entries.append(entry)
                return len(self.entries)

        ledger = _LedgerStub()
        tracker = UsageTracker(ledger=ledger)  # type: ignore[arg-type]
        await tracker.record_embedding(
            EmbeddingRequest(texts=["hello"]),
            EmbeddingResponse(
                vectors=[[0.1]],
                model="mock-embed-1",
                provider="mock",
                usage=LLMUsage(
                    prompt_tokens=5, completion_tokens=0,
                    total_tokens=5, cost_usd=0.0001,
                ),
                latency_ms=12.5,
            ),
            engine_name="memory",
        )
        assert len(ledger.entries) == 1
        e = ledger.entries[0]
        assert e.provider == "mock"
        assert e.model == "mock-embed-1"
        assert e.prompt_tokens == 5
        assert e.completion_tokens == 0
        assert e.cost_usd == 0.0001
        assert e.engine_name == "memory"
        assert e.success is True

    async def test_ledger_entry_marks_failure_when_response_has_error(self) -> None:
        class _LedgerStub:
            def __init__(self) -> None:
                self.entries: list[Any] = []

            async def append(self, entry: Any) -> int:
                self.entries.append(entry)
                return len(self.entries)

        ledger = _LedgerStub()
        tracker = UsageTracker(ledger=ledger)  # type: ignore[arg-type]
        await tracker.record_embedding(
            EmbeddingRequest(texts=["hello"]),
            EmbeddingResponse(
                vectors=[], model="m", provider="p", error="boom"
            ),
            engine_name="memory",
        )
        assert ledger.entries[0].success is False


# ---------------------------------------------------------------------------
# Determinism — cross-run same-input same-vector (G14 of the plan)
# ---------------------------------------------------------------------------


class TestDeterminism:
    async def test_mock_embed_is_byte_identical_across_router_instances(self) -> None:
        # Two independent routers with fresh MockLLMProvider should
        # produce identical vectors for identical inputs — the
        # embedding cache contract assumes this.
        r1 = _make_router()
        r2 = _make_router()
        a = await r1.embed(EmbeddingRequest(texts=["canonical"]), engine_name="memory")
        b = await r2.embed(EmbeddingRequest(texts=["canonical"]), engine_name="memory")
        assert a.vectors == b.vectors
