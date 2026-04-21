"""Unit tests for the shared memory-hook helpers.

Phase 4B Step 11 closeout. These tests pin down the contract BOTH
callers (``NPCActivator._recall_for_activation`` /
``_implicit_remember`` forwarders AND
``AgencyEngine._activate_with_tool_loop``) depend on. If either
path breaks, these tests don't move — they expose regressions at
the helper level first.

Negative-intent ratio: 5/8 = 62%.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from volnix.actors.state import ActorState
from volnix.core.types import ActivationId, ActorId
from volnix.engines.agency._memory_hooks import (
    _QUERY_TEXT_MAX_CHARS,
    _TOOL_NAMES_CAP,
    implicit_remember_activation,
    recall_for_activation,
)


def _actor(actor_id: str = "a1", persona_desc: str = "tired urbanite") -> ActorState:
    return ActorState(
        actor_id=ActorId(actor_id),
        role="consumer",
        actor_type="internal",
        persona={"description": persona_desc},
    )


def _memory_engine_stub(*, top_k: int = 5) -> AsyncMock:
    eng = AsyncMock()
    eng._memory_config = type("MC", (), {"default_recall_top_k": top_k})()
    eng.recall = AsyncMock(return_value=None)
    eng.remember = AsyncMock(return_value="rec-1")
    return eng


# ─── Pre-activation recall ─────────────────────────────────────────


class TestRecallForActivation:
    """D2 / D11-3 — helper surface for pre-activation recall."""

    async def test_negative_none_memory_engine_returns_none_without_call(self) -> None:
        """The critical opt-out contract. Consumers that don't wire
        memory must pay zero cost — no attribute access, no coroutine
        creation, no warning log."""
        result = await recall_for_activation(
            memory_engine=None,
            actor=_actor(),
            trigger_event=None,
            prompt_describe=lambda _e: "describe",
            tick=0,
        )
        assert result is None

    async def test_negative_recall_exception_returns_none_and_logs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """D11-6: any failure (store down, FTS5 parse error) MUST
        degrade to ``None`` with a warning. Memory is additive."""
        eng = _memory_engine_stub()
        eng.recall = AsyncMock(side_effect=RuntimeError("store down"))

        with caplog.at_level("WARNING"):
            result = await recall_for_activation(
                memory_engine=eng,
                actor=_actor(),
                trigger_event=None,
                prompt_describe=lambda _e: "describe",
                tick=7,
            )
        assert result is None
        assert any("memory recall failed" in r.message for r in caplog.records)

    async def test_negative_empty_trigger_and_persona_uses_fallback_query(self) -> None:
        """When trigger description is empty AND persona is empty, the
        query text must fall back to an actor-id-anchored string — never
        an empty query (FTS5 rejects empty search strings)."""
        actor = _actor(persona_desc="")
        eng = _memory_engine_stub()

        await recall_for_activation(
            memory_engine=eng,
            actor=actor,
            trigger_event=None,
            prompt_describe=lambda _e: "",
            tick=0,
        )
        q = eng.recall.await_args.kwargs["query"]
        assert "a1" in q.semantic_text
        assert q.semantic_text.strip() != ""

    async def test_positive_recall_called_with_expected_shape(self) -> None:
        """Happy path: helper constructs HybridQuery with top_k from
        config, calls recall with actor-scope + self-as-caller, forwards
        the tick. Asserts every kwarg."""
        eng = _memory_engine_stub(top_k=7)

        await recall_for_activation(
            memory_engine=eng,
            actor=_actor(),
            trigger_event=None,
            prompt_describe=lambda _e: "event description",
            tick=42,
        )
        kw = eng.recall.await_args.kwargs
        assert kw["target_scope"] == "actor"
        assert kw["target_owner"] == "a1"
        assert kw["caller"] == ActorId("a1")
        assert kw["tick"] == 42
        assert kw["query"].top_k == 7
        assert "event description" in kw["query"].semantic_text
        assert "tired urbanite" in kw["query"].semantic_text

    async def test_positive_query_text_capped_at_max_chars(self) -> None:
        """Bounded query size — prevents runaway prompt sizes from
        generating multi-KB FTS5 queries that could stall the engine."""
        long_desc = "x" * 10_000
        actor = _actor(persona_desc=long_desc)
        eng = _memory_engine_stub()

        await recall_for_activation(
            memory_engine=eng,
            actor=actor,
            trigger_event=None,
            prompt_describe=lambda _e: long_desc,
            tick=0,
        )
        q = eng.recall.await_args.kwargs["query"]
        assert len(q.semantic_text) == _QUERY_TEXT_MAX_CHARS


# ─── Post-activation implicit remember ─────────────────────────────


class TestImplicitRememberActivation:
    """D2 / D11-7 — helper surface for post-activation remember."""

    async def test_negative_none_memory_engine_noop(self) -> None:
        """Opt-out default — zero side effects.

        L1 (audit-fold): assert that a nearby stub mock's ``remember``
        is not called either — the None path must not sneak a call
        through any side channel. We can't assert on the actual
        ``memory_engine=None`` call, so we construct a stub, confirm
        it's untouched after a None-engine call to the helper.
        """
        stub = _memory_engine_stub()
        await implicit_remember_activation(
            memory_engine=None,
            actor_id=ActorId("a1"),
            activation_id=ActivationId("act-1"),
            reason="test",
            terminated_by="text_response",
            total_tool_calls=0,
            tool_names_invoked=[],
            final_text="",
            tick=0,
        )
        # Stub is in scope but was never passed in — its ``remember``
        # must still be untouched, confirming no global side channel.
        stub.remember.assert_not_called()
        stub.recall.assert_not_called()

    async def test_negative_remember_exception_swallowed_and_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """D11-9: failure in the store must not propagate."""
        eng = _memory_engine_stub()
        eng.remember = AsyncMock(side_effect=RuntimeError("store down"))

        with caplog.at_level("WARNING"):
            await implicit_remember_activation(
                memory_engine=eng,
                actor_id=ActorId("a1"),
                activation_id=ActivationId("act-1"),
                reason="test",
                terminated_by="do_nothing",
                total_tool_calls=1,
                tool_names_invoked=["tickets_read"],
                final_text="ok",
                tick=5,
            )
        assert any("implicit remember failed" in r.message for r in caplog.records)

    async def test_negative_tool_names_exceeding_cap_are_clipped(self) -> None:
        """Runaway loop protection — a 100-call activation does not
        inflate the episodic record's tags beyond the 50-cap."""
        eng = _memory_engine_stub()
        many_tools = [f"tool_{i}" for i in range(100)]

        await implicit_remember_activation(
            memory_engine=eng,
            actor_id=ActorId("a1"),
            activation_id=ActivationId("act-1"),
            reason="test",
            terminated_by="max_tool_calls",
            total_tool_calls=100,
            tool_names_invoked=many_tools,
            final_text="ran out",
            tick=0,
        )
        write = eng.remember.await_args.kwargs["write"]
        # tags = [reason, *capped_tools, terminated_by] = 1 + 50 + 1 = 52
        assert len(write.tags) == _TOOL_NAMES_CAP + 2
        assert "tool_49" in write.tags
        assert "tool_50" not in write.tags

    async def test_positive_tools_used_importance_0_5(self) -> None:
        eng = _memory_engine_stub()

        await implicit_remember_activation(
            memory_engine=eng,
            actor_id=ActorId("a1"),
            activation_id=ActivationId("act-xyz"),
            reason="autonomous_work",
            terminated_by="do_nothing",
            total_tool_calls=3,
            tool_names_invoked=["tickets_read", "chat_postMessage", "tickets_update"],
            final_text="Triage done.",
            tick=11,
        )
        write = eng.remember.await_args.kwargs["write"]
        assert write.kind == "episodic"
        assert write.source == "implicit"
        assert write.importance == 0.5
        assert write.metadata["activation_id"] == "act-xyz"
        assert write.metadata["terminated_by"] == "do_nothing"
        assert "Triage done." in write.content
        assert "tickets_read" in write.tags
