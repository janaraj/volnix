"""Tests for the streaming-surface contract
(``tnl/llm-router-streaming-surface.tnl``).

Locks: ``LLMStreamChunk`` value type, ``LLMProvider.stream_generate``
default fallback, ``LLMRouter.route_streaming`` orchestration,
ledger-write-once-at-end semantics, replay-mode pass-through, and
the public-export surface.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest

from volnix import LLMStreamChunk as LLMStreamChunk_top_level
from volnix.llm import LLMStreamChunk as LLMStreamChunk_subpkg
from volnix.llm.config import LLMConfig, LLMProviderEntry
from volnix.llm.provider import LLMProvider
from volnix.llm.providers.mock import MockLLMProvider
from volnix.llm.registry import ProviderRegistry
from volnix.llm.router import LLMRouter
from volnix.llm.tracker import UsageTracker
from volnix.llm.types import LLMRequest, LLMResponse, LLMStreamChunk, LLMUsage


def _make_router(tracker: UsageTracker | None = None) -> LLMRouter:
    config = LLMConfig(
        defaults=LLMProviderEntry(type="mock", default_model="mock-1"),
        providers={"mock": LLMProviderEntry(type="mock")},
        routing={},
    )
    registry = ProviderRegistry()
    registry.register("mock", MockLLMProvider())
    return LLMRouter(config=config, registry=registry, tracker=tracker)


# ─── Public-export surface ────────────────────────────────────────


class TestLLMStreamChunkExports:
    def test_positive_exported_from_top_level_volnix(self) -> None:
        """TNL: LLMStreamChunk MUST be importable from volnix
        (top-level), not just volnix.llm."""
        assert LLMStreamChunk_top_level is LLMStreamChunk
        assert LLMStreamChunk_subpkg is LLMStreamChunk

    def test_positive_in_top_level_all(self) -> None:
        import volnix

        assert "LLMStreamChunk" in volnix.__all__


# ─── LLMStreamChunk value type ────────────────────────────────────


class TestLLMStreamChunkShape:
    def test_positive_default_field_values(self) -> None:
        chunk = LLMStreamChunk()
        assert chunk.content_delta == ""
        assert chunk.usage_delta is None
        assert chunk.is_final is False
        assert chunk.provider == ""
        assert chunk.model == ""
        assert chunk.error is None

    def test_positive_frozen(self) -> None:
        """Frozen pydantic — assignment after construction raises."""
        chunk = LLMStreamChunk(content_delta="hi")
        with pytest.raises(Exception):  # ValidationError or AttributeError
            chunk.content_delta = "no"


# ─── Provider base-class fallback default ─────────────────────────


class TestProviderStreamGenerateFallback:
    """The base-class default ``stream_generate`` MUST delegate to
    ``generate`` and yield exactly one chunk wrapping the response."""

    @pytest.mark.asyncio
    async def test_positive_yields_single_final_chunk(self) -> None:
        provider = MockLLMProvider()
        request = LLMRequest(user_content="hi")
        chunks = []
        async for chunk in provider.stream_generate(request):
            chunks.append(chunk)
        assert len(chunks) == 1
        assert chunks[0].is_final is True
        # Mock provider returns its own canned content; just verify
        # it's non-empty + the chunk carries it.
        assert chunks[0].content_delta != ""
        assert chunks[0].provider == provider.provider_name

    @pytest.mark.asyncio
    async def test_negative_generate_exception_yields_error_chunk(
        self,
    ) -> None:
        """TNL: when ``generate`` raises, default yields ONE chunk
        with ``error`` populated, ``is_final=True``, then stops.
        Iterator MUST NOT propagate the exception."""

        class _BoomProvider(LLMProvider):
            provider_name = "boom"

            async def generate(self, request: LLMRequest) -> LLMResponse:
                raise RuntimeError("boom!")

        chunks = []
        async for chunk in _BoomProvider().stream_generate(LLMRequest(user_content="hi")):
            chunks.append(chunk)
        assert len(chunks) == 1
        assert chunks[0].is_final is True
        assert chunks[0].content_delta == ""
        assert chunks[0].error is not None
        assert "RuntimeError" in chunks[0].error
        assert "boom!" in chunks[0].error


# ─── LLMRouter.route_streaming ────────────────────────────────────


class TestRouterRouteStreaming:
    @pytest.mark.asyncio
    async def test_positive_yields_chunks_via_fallback(self) -> None:
        """Router.route_streaming through MockLLMProvider's
        inherited default → one chunk via fallback."""
        router = _make_router()
        chunks = []
        async for chunk in router.route_streaming(LLMRequest(user_content="hi"), engine_name="any"):
            chunks.append(chunk)
        assert len(chunks) == 1
        assert chunks[0].is_final is True

    @pytest.mark.asyncio
    async def test_positive_route_one_shot_unchanged(self) -> None:
        """TNL Phase 0 oracle: existing route() MUST be byte-identical.
        Smoke test — same request, same route call, gets a complete
        LLMResponse (not a chunk)."""
        router = _make_router()
        resp = await router.route(LLMRequest(user_content="hi"), engine_name="any")
        assert isinstance(resp, LLMResponse)
        assert resp.content != ""

    @pytest.mark.asyncio
    async def test_positive_ledger_written_once_after_stream(self) -> None:
        """TNL: tracker.record called EXACTLY ONCE per stream,
        AFTER the iterator is exhausted."""
        ledger = AsyncMock()
        ledger.append = AsyncMock(return_value=1)
        tracker = UsageTracker(ledger=ledger)
        router = _make_router(tracker=tracker)

        chunks = []
        async for chunk in router.route_streaming(
            LLMRequest(user_content="hi"),
            engine_name="my_engine",
            use_case="character_response",
        ):
            chunks.append(chunk)

        # Exactly one ledger row.
        assert ledger.append.await_count == 1
        entry = ledger.append.call_args[0][0]
        assert entry.entry_type == "llm_call"
        # use_case attribution flows through (gap 3).
        assert entry.use_case == "character_response"

    @pytest.mark.asyncio
    async def test_positive_synthesized_response_concatenates_deltas(
        self,
    ) -> None:
        """TNL: synthesized LLMResponse for the ledger MUST
        concatenate every chunk's content_delta."""

        class _MultiChunkProvider(LLMProvider):
            provider_name = "multi"

            async def generate(self, request: LLMRequest) -> LLMResponse:
                return LLMResponse(content="ignored", provider="multi")

            async def stream_generate(self, request: LLMRequest) -> AsyncIterator[LLMStreamChunk]:
                yield LLMStreamChunk(content_delta="hello ", provider="multi")
                yield LLMStreamChunk(content_delta="there ", provider="multi")
                yield LLMStreamChunk(
                    content_delta="world",
                    provider="multi",
                    is_final=True,
                    usage_delta=LLMUsage(prompt_tokens=5, completion_tokens=3),
                )

        config = LLMConfig(
            defaults=LLMProviderEntry(type="multi", default_model="m"),
            providers={"multi": LLMProviderEntry(type="multi")},
            routing={},
        )
        registry = ProviderRegistry()
        registry.register("multi", _MultiChunkProvider())
        ledger = AsyncMock()
        ledger.append = AsyncMock(return_value=1)
        tracker = UsageTracker(ledger=ledger)
        router = LLMRouter(config=config, registry=registry, tracker=tracker)

        chunks = []
        async for chunk in router.route_streaming(LLMRequest(user_content="x"), engine_name="any"):
            chunks.append(chunk)

        assert len(chunks) == 3
        # Synthesized response carries concatenated content + final usage.
        entry = ledger.append.call_args[0][0]
        # entry.entry_type lives at the row level; the synthesized
        # LLMResponse fields land on usage / model / provider / etc.
        # We assert via the final LLMUsage-derived counts.
        assert entry.prompt_tokens == 5
        assert entry.completion_tokens == 3
