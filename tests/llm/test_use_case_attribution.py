"""Tests for ``LLMCallEntry.use_case`` attribution
(``tnl/llm-call-entry-use-case-attribution.tnl``).

Locks: tracker accepts use_case kwarg, forwards to LLMCallEntry;
default empty string preserves legacy behavior; router forwards
its use_case argument through to the tracker call.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from volnix.llm.config import LLMConfig, LLMProviderEntry
from volnix.llm.providers.mock import MockLLMProvider
from volnix.llm.registry import ProviderRegistry
from volnix.llm.router import LLMRouter
from volnix.llm.tracker import UsageTracker
from volnix.llm.types import LLMRequest, LLMResponse, LLMUsage


def _make_response() -> LLMResponse:
    return LLMResponse(
        content="ok",
        usage=LLMUsage(prompt_tokens=10, completion_tokens=5),
        model="mock",
        provider="mock",
        latency_ms=1.0,
    )


def _make_router(tracker: UsageTracker) -> LLMRouter:
    config = LLMConfig(
        defaults=LLMProviderEntry(type="mock", default_model="mock-1"),
        providers={"mock": LLMProviderEntry(type="mock")},
        routing={},
    )
    registry = ProviderRegistry()
    registry.register("mock", MockLLMProvider())
    return LLMRouter(config=config, registry=registry, tracker=tracker)


# ─── UsageTracker plumbing ─────────────────────────────────────────


class TestUsageTrackerForwardsUseCase:
    @pytest.mark.asyncio
    async def test_positive_use_case_lands_on_ledger_entry(self) -> None:
        """TNL: ``record(..., use_case="x")`` MUST stamp the value
        verbatim onto ``LLMCallEntry.use_case``."""
        ledger = AsyncMock()
        ledger.append = AsyncMock(return_value=1)
        tracker = UsageTracker(ledger=ledger)
        await tracker.record(
            LLMRequest(user_content="hi"),
            _make_response(),
            "test_engine",
            use_case="character_response",
        )
        ledger.append.assert_awaited_once()
        entry = ledger.append.call_args[0][0]
        assert entry.use_case == "character_response"

    @pytest.mark.asyncio
    async def test_negative_default_use_case_is_empty_string(self) -> None:
        """TNL: omitting ``use_case`` MUST land empty string on the
        entry, matching the field's pre-attribution default."""
        ledger = AsyncMock()
        ledger.append = AsyncMock(return_value=1)
        tracker = UsageTracker(ledger=ledger)
        await tracker.record(
            LLMRequest(user_content="hi"),
            _make_response(),
            "test_engine",
        )
        entry = ledger.append.call_args[0][0]
        assert entry.use_case == ""

    @pytest.mark.asyncio
    async def test_positive_use_case_is_kwarg_only(self) -> None:
        """TNL: ``use_case`` MUST be keyword-only — caller cannot
        pass it positionally (would conflict with ``actor_id``).
        Verifying by attempting positional call and expecting
        TypeError."""
        ledger = AsyncMock()
        ledger.append = AsyncMock(return_value=1)
        tracker = UsageTracker(ledger=ledger)
        with pytest.raises(TypeError):
            # Positional after engine_name would be actor_id;
            # use_case as keyword-only enforces clarity.
            await tracker.record(
                LLMRequest(user_content="hi"),
                _make_response(),
                "engine",
                None,  # actor_id positional
                "character_response",  # MUST be rejected — keyword-only
            )


# ─── LLMRouter forwarding ──────────────────────────────────────────


class TestLLMRouterForwardsUseCase:
    @pytest.mark.asyncio
    async def test_positive_route_use_case_reaches_ledger(self) -> None:
        """TNL: ``router.route(..., use_case=X)`` MUST forward X
        through to the tracker, which stamps it on the entry."""
        ledger = AsyncMock()
        ledger.append = AsyncMock(return_value=1)
        tracker = UsageTracker(ledger=ledger)
        router = _make_router(tracker)
        await router.route(
            LLMRequest(user_content="hi"),
            engine_name="my_engine",
            use_case="agency_personality",
        )
        ledger.append.assert_awaited_once()
        entry = ledger.append.call_args[0][0]
        assert entry.use_case == "agency_personality"

    @pytest.mark.asyncio
    async def test_positive_router_default_use_case_is_default_string(
        self,
    ) -> None:
        """TNL Phase 0 oracle: callers that omit ``use_case`` get
        the router's default value ``"default"`` on the ledger
        entry. This is a single-character behavioral delta from
        pre-change empty-string default."""
        ledger = AsyncMock()
        ledger.append = AsyncMock(return_value=1)
        tracker = UsageTracker(ledger=ledger)
        router = _make_router(tracker)
        await router.route(
            LLMRequest(user_content="hi"),
            engine_name="my_engine",
        )
        entry = ledger.append.call_args[0][0]
        # Router default is "default", not "" — TNL flagged this
        # explicitly in the Phase 0 oracle clause.
        assert entry.use_case == "default"
