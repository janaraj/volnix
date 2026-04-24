"""Session-scope tests for ``NPCActivator`` memory forwarders.

Pins the contract that ``NPCActivator._recall_for_activation`` and
``_implicit_remember`` forward ``host._session_id`` into the shared
``_memory_hooks`` helpers, which in turn forward to the memory
engine (``tnl/session-scoped-memory.tnl``).

Mock depth: we stub the memory ENGINE (one layer below the helper)
rather than the helper itself. This keeps the test order-independent
— module-level monkeypatching of the helper can leak across the full
test suite in hard-to-diagnose ways, whereas engine mocks are
isolated to the SimpleNamespace host instance.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from volnix.actors.state import ActorState
from volnix.core.types import ActorId, SessionId
from volnix.engines.agency.npc_activator import NPCActivator


def _actor() -> ActorState:
    return ActorState(
        actor_id=ActorId("npc-1"),
        role="consumer",
        actor_type="internal",
        persona={"description": "curious shopper"},
    )


def _activator() -> NPCActivator:
    pb = MagicMock()
    pb._describe = lambda _e: "describe-stub"
    return NPCActivator(prompt_builder=pb, activation_profile_loader=MagicMock())


def _memory_engine_stub() -> AsyncMock:
    """Minimal MemoryEngineProtocol-shaped stub — enough for the
    shared helpers to drive end-to-end without a real DB."""
    eng = AsyncMock()
    eng._memory_config = type("MC", (), {"default_recall_top_k": 5})()
    eng.recall = AsyncMock(return_value=None)
    eng.remember = AsyncMock(return_value="rec-1")
    return eng


class TestNpcRecallForwarderThreadsSessionId:
    async def test_positive_npc_forwarder_threads_host_session_id_into_recall(
        self,
    ) -> None:
        eng = _memory_engine_stub()
        host = SimpleNamespace(
            _memory_engine=eng,
            _session_id=SessionId("sess-npc"),
            _simulation_progress=[5],
        )
        await _activator()._recall_for_activation(
            actor=_actor(), trigger_event=None, host=host
        )
        # The real helper ran and forwarded session_id to engine.recall.
        assert eng.recall.await_count == 1
        assert eng.recall.await_args.kwargs["session_id"] == SessionId("sess-npc")

    async def test_positive_npc_forwarder_defaults_to_none_when_host_has_no_session_id(
        self,
    ) -> None:
        eng = _memory_engine_stub()
        host = SimpleNamespace(_memory_engine=eng, _simulation_progress=[0])
        await _activator()._recall_for_activation(
            actor=_actor(), trigger_event=None, host=host
        )
        assert eng.recall.await_args.kwargs["session_id"] is None


class TestNpcImplicitRememberForwarderThreadsSessionId:
    async def test_positive_npc_forwarder_threads_host_session_id_into_remember(
        self,
    ) -> None:
        eng = _memory_engine_stub()
        host = SimpleNamespace(
            _memory_engine=eng,
            _session_id=SessionId("sess-npc-remember"),
            _simulation_progress=[7],
        )
        await _activator()._implicit_remember(
            actor=_actor(),
            reason="npc_exposure",
            terminated_by="text_response",
            total_tool_calls=0,
            tool_names_invoked=[],
            final_text="",
            activation_id="act-1",
            host=host,
        )
        assert eng.remember.await_count == 1
        assert eng.remember.await_args.kwargs["session_id"] == SessionId(
            "sess-npc-remember"
        )
