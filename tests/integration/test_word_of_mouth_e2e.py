"""End-to-end: ``npc_chat.send_message(feature_mention=...)`` wakes the peer NPC.

This is the Phase 3 E2E gate, symmetric to the Phase 2 exposure-event
test: proves that the full wire — handler emits ``WordOfMouthEvent``
in ``proposed_events``, pipeline publishes it, recipient's
subscription matches it, ``AgencyEngine.notify`` activates them — is
live and correct. Unit tests alone can't catch a break in any of those
handoffs.

The test does NOT boot the full ``VolnixApp`` pipeline (that would
pull in real LLM calls, real state backends, 20+ engine dependencies).
Instead it wires the minimum in-process:

* The handler is invoked directly via the pack.
* The ``proposed_events`` are fed into ``AgencyEngine.notify`` by
  hand — matching what the pipeline's ``CommitStep`` does at
  ``volnix/engines/state/engine.py:324-328`` (verified by grep).
* The recipient is an Active NPC pre-wired with the subscription
  ``app.configure_agency`` synthesizes from
  ``profile.activation_triggers``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from volnix.actors.activation_profile import (
    ActivationProfile,
    ActivationTrigger,
    BudgetDefaults,
    ToolScope,
)
from volnix.actors.state import ActorState, Subscription
from volnix.core.events import WordOfMouthEvent
from volnix.core.types import ActorId, ToolName
from volnix.engines.agency.engine import AgencyEngine
from volnix.engines.agency.npc_activator import NPCActivator
from volnix.engines.agency.npc_prompt_builder import NPCPromptBuilder
from volnix.llm.types import LLMResponse, ToolCall
from volnix.packs.verified.npc_chat.pack import NPCChatPack
from volnix.simulation.world_context import WorldContextBundle

# -- fixtures ----------------------------------------------------------------


def _profile() -> ActivationProfile:
    return ActivationProfile(
        name="consumer_user",
        description="consumer",
        state_schema={"type": "object", "properties": {}},
        activation_triggers=[
            ActivationTrigger(event="npc.exposure"),
            ActivationTrigger(event="npc.word_of_mouth"),
        ],
        prompt_template="consumer_user_decision.j2",
        tool_scope=ToolScope(read=["vibemesh"], write=["vibemesh"]),
        budget_defaults=BudgetDefaults(api_calls=2, llm_spend=0.0),
    )


class _ProfileLoaderStub:
    def load(self, name: str) -> ActivationProfile:
        if name == "consumer_user":
            return _profile()
        raise FileNotFoundError(name)

    def list_available(self) -> list[str]:
        return ["consumer_user"]


def _ctx() -> WorldContextBundle:
    return WorldContextBundle(
        world_description="WoM world",
        reality_summary="Messy.",
        mission="Test word of mouth.",
        available_services=[
            {
                "name": "drop_flare",
                "service": "vibemesh",
                "http_method": "POST",
                "description": "Start a hangout",
                "required_params": ["duration_min"],
            },
        ],
    )


def _active_npc(actor_id: str) -> ActorState:
    """An Active NPC subscribed to ``npc.word_of_mouth`` (as app.py synthesizes)."""
    return ActorState(
        actor_id=ActorId(actor_id),
        role="consumer",
        actor_type="internal",
        persona={"description": "Gen-Z consumer"},
        activation_profile_name="consumer_user",
        npc_state={"awareness": 0, "interest": 0, "satisfaction": 0.5, "usage_count": 0},
        subscriptions=[
            Subscription(service_id="", filter={"event_type": "npc.word_of_mouth"}),
        ],
    )


async def _build_engine(actors: list[ActorState]) -> tuple[AgencyEngine, AsyncMock, AsyncMock, Any]:
    engine = AgencyEngine()
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    await engine.initialize({}, bus)
    await engine.configure(actors, _ctx(), _ctx().available_services)

    llm_router = AsyncMock()
    llm_router.route = AsyncMock(
        return_value=LLMResponse(
            content="",
            tool_calls=[ToolCall(name="drop_flare", arguments={"duration_min": 90}, id="c1")],
            model="mock",
            provider="mock",
        )
    )
    engine._llm_router = llm_router

    committed = AsyncMock()
    committed.response_body = {"status": "ok"}
    committed.event_id = "evt-committed-npc-action"
    tool_executor = AsyncMock(return_value=committed)
    engine.set_tool_executor(tool_executor)

    class _Ledger:
        def __init__(self) -> None:
            self.entries: list[Any] = []

        async def append(self, entry: Any) -> int:
            self.entries.append(entry)
            return len(self.entries)

    ledger = _Ledger()
    engine._ledger = ledger

    engine.set_npc_activator(
        NPCActivator(
            prompt_builder=NPCPromptBuilder(),
            activation_profile_loader=_ProfileLoaderStub(),
        )
    )
    return engine, llm_router, tool_executor, ledger


# -- Tests -------------------------------------------------------------------


class TestWordOfMouthEndToEnd:
    @pytest.mark.asyncio
    async def test_feature_mention_wakes_recipient_and_runs_pipeline(self) -> None:
        """The one contract: send_message with feature_mention -> recipient activates.

        Flow:
        1. npc-1 calls ``npc_chat.send_message(recipient="npc-2", feature_mention="drop_flare")``.
        2. The handler returns a ``WordOfMouthEvent`` in ``proposed_events``.
        3. We hand that event to ``engine.notify`` — the same thing the
           pipeline's ``CommitStep`` does in production.
        4. npc-2's subscription (``event_type == npc.word_of_mouth``) matches.
        5. ``intended_for == [npc-2]`` triggers activation.
        6. NPCActivator runs: LLM is called once, tool_executor invoked,
           ActivationCompleteEntry lands in the ledger.
        """
        recipient = _active_npc("npc-2")
        engine, router, executor, ledger = await _build_engine([recipient])

        pack = NPCChatPack()
        proposal = await pack.handle_action(
            ToolName("npc_chat.send_message"),
            {
                "sender_id": "npc-1",
                "recipient_id": "npc-2",
                "content": "you have to try this",
                "feature_mention": "drop_flare",
                "sentiment": "positive",
            },
            {"entities": {}, "tick": 3},
        )

        assert len(proposal.proposed_events) == 1
        wom = proposal.proposed_events[0]
        assert isinstance(wom, WordOfMouthEvent)

        envelopes = await engine.notify(wom)

        # Recipient activated and went through the NPC tool-loop end-to-end.
        assert router.route.await_count == 1, "LLM must be called exactly once"
        assert executor.await_count == 1, "pipeline tool executor must see the action"
        assert len(envelopes) == 1
        assert envelopes[0].actor_id == recipient.actor_id
        # Ledger confirms the activation completed through the NPC path.
        entry_types = [getattr(e, "entry_type", "?") for e in ledger.entries]
        assert "activation_complete" in entry_types
        assert "tool_loop_step" in entry_types

    @pytest.mark.asyncio
    async def test_plain_message_does_not_wake_recipient(self) -> None:
        """Inverse proof: without ``feature_mention``, no WordOfMouthEvent,
        so no activation. Confirms the handler's gating matches the
        recipient's subscription.
        """
        recipient = _active_npc("npc-2")
        engine, router, _, _ = await _build_engine([recipient])

        pack = NPCChatPack()
        proposal = await pack.handle_action(
            ToolName("npc_chat.send_message"),
            {
                "sender_id": "npc-1",
                "recipient_id": "npc-2",
                "content": "random chit-chat",
            },
            {"entities": {}, "tick": 3},
        )
        assert proposal.proposed_events == []

        # Even if we try to notify with an unrelated WorldEvent, no
        # npc.word_of_mouth event exists, so no subscription match.
        assert router.route.await_count == 0

    @pytest.mark.asyncio
    async def test_word_of_mouth_targeted_only_wakes_recipient(self) -> None:
        """A WordOfMouthEvent for npc-2 must not wake npc-3."""
        npc2 = _active_npc("npc-2")
        npc3 = _active_npc("npc-3")
        engine, router, _, _ = await _build_engine([npc2, npc3])

        pack = NPCChatPack()
        proposal = await pack.handle_action(
            ToolName("npc_chat.send_message"),
            {
                "sender_id": "npc-1",
                "recipient_id": "npc-2",
                "content": "this app is great",
                "feature_mention": "drop_flare",
                "sentiment": "positive",
            },
            {"entities": {}, "tick": 3},
        )
        wom = proposal.proposed_events[0]
        await engine.notify(wom)

        # Exactly one activation. If npc-3 woke too, router would be
        # called twice.
        assert router.route.await_count == 1
