"""Session-scope tests for the agency memory-hook helpers.

Locks the ``session_id`` forwarding contract for
``recall_for_activation`` and ``implicit_remember_activation``
(``tnl/session-scoped-memory.tnl``).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from volnix.actors.state import ActorState
from volnix.core.types import ActivationId, ActorId, SessionId
from volnix.engines.agency._memory_hooks import (
    implicit_remember_activation,
    recall_for_activation,
)


def _actor() -> ActorState:
    return ActorState(
        actor_id=ActorId("a1"),
        role="consumer",
        actor_type="internal",
        persona={"description": "tired urbanite"},
    )


def _memory_engine_stub() -> AsyncMock:
    eng = AsyncMock()
    eng._memory_config = type("MC", (), {"default_recall_top_k": 5})()
    eng.recall = AsyncMock(return_value=None)
    eng.remember = AsyncMock(return_value="rec-1")
    return eng


class TestRecallForwardsSessionId:
    async def test_positive_recall_forwards_session_id_to_engine(self) -> None:
        eng = _memory_engine_stub()
        await recall_for_activation(
            memory_engine=eng,
            actor=_actor(),
            trigger_event=None,
            prompt_describe=lambda _e: "describe",
            tick=3,
            session_id=SessionId("sess-xyz"),
        )
        assert eng.recall.await_count == 1
        assert eng.recall.await_args.kwargs["session_id"] == SessionId("sess-xyz")

    async def test_positive_recall_omitted_session_id_forwards_none(self) -> None:
        # Default kwarg path — still forwards a session_id kwarg, set
        # to None. The store reads this as "session-less".
        eng = _memory_engine_stub()
        await recall_for_activation(
            memory_engine=eng,
            actor=_actor(),
            trigger_event=None,
            prompt_describe=lambda _e: "describe",
            tick=0,
        )
        assert eng.recall.await_args.kwargs["session_id"] is None


class TestImplicitRememberForwardsSessionId:
    async def test_positive_implicit_remember_forwards_session_id_to_engine(
        self,
    ) -> None:
        eng = _memory_engine_stub()
        await implicit_remember_activation(
            memory_engine=eng,
            actor_id=ActorId("a1"),
            activation_id=ActivationId("act-1"),
            reason="event_affected",
            terminated_by="text_response",
            total_tool_calls=0,
            tool_names_invoked=[],
            final_text="",
            tick=3,
            session_id=SessionId("sess-xyz"),
        )
        assert eng.remember.await_count == 1
        assert eng.remember.await_args.kwargs["session_id"] == SessionId("sess-xyz")

    async def test_positive_implicit_remember_omitted_session_id_forwards_none(
        self,
    ) -> None:
        eng = _memory_engine_stub()
        await implicit_remember_activation(
            memory_engine=eng,
            actor_id=ActorId("a1"),
            activation_id=ActivationId("act-1"),
            reason="event_affected",
            terminated_by="text_response",
            total_tool_calls=0,
            tool_names_invoked=[],
            final_text="",
            tick=0,
        )
        assert eng.remember.await_args.kwargs["session_id"] is None
