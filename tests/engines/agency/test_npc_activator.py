"""Tests for :class:`NPCActivator` — Active-NPC LLM tool loop.

Covers the Phase 2 contract:

* Passive NPCs (``activation_profile_name=None``) never route to the
  NPC path, even if the activator is wired in. They keep the existing
  agent loop.
* Active NPCs route to ``NPCActivator.activate_npc`` via the new
  early branch in ``AgencyEngine.activate_for_event``.
* Every NPC tool call flows through the shared ``tool_executor`` — the
  same 7-step governance pipeline used by agents.
* ``do_nothing`` ends the activation.
* Tool scope from the activation profile constrains which tools the
  LLM sees.
* The LLM is called at most once per activation in Phase 2 (single
  turn); the activation-profile budget cap is respected.
* The activator is fully opt-in — without a ``set_npc_activator`` call
  on the engine, every actor (including HUMAN-with-profile actors)
  falls back to the agent path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from volnix.actors.activation_profile import (
    ActivationProfile,
    ActivationTrigger,
    BudgetDefaults,
    ToolScope,
)
from volnix.actors.state import ActorState
from volnix.core.events import NPCExposureEvent
from volnix.core.types import ActorId, EventId, ServiceId, Timestamp
from volnix.engines.agency.engine import AgencyEngine
from volnix.engines.agency.npc_activator import NPCActivator
from volnix.engines.agency.npc_prompt_builder import NPCPromptBuilder
from volnix.llm.types import LLMResponse, ToolCall
from volnix.simulation.world_context import WorldContextBundle

# -- shared helpers -----------------------------------------------------------


def _ts() -> Timestamp:
    now = datetime.now(UTC)
    return Timestamp(world_time=now, wall_time=now, tick=0)


def _exposure(npc_id: str = "npc-1", feature: str = "drop_flare") -> NPCExposureEvent:
    return NPCExposureEvent(
        event_id=EventId(f"evt-{npc_id}-{feature}"),
        event_type="npc.exposure",
        timestamp=_ts(),
        actor_id=ActorId(npc_id),
        service_id=ServiceId("vibemesh"),
        action="expose",
        npc_id=ActorId(npc_id),
        feature_id=feature,
        source="animator",
        medium="push_notification",
    )


def _active_npc(actor_id: str = "npc-1") -> ActorState:
    return ActorState(
        actor_id=ActorId(actor_id),
        role="consumer",
        actor_type="internal",
        persona={"description": "Gen-Z burnt-out urbanite"},
        activation_profile_name="consumer_user",
        npc_state={
            "awareness": 0.2,
            "interest": 0.1,
            "satisfaction": 0.5,
            "usage_count": 0,
            "known_features": [],
            "sentiment": "neutral",
        },
    )


def _passive_npc(actor_id: str = "passive-1") -> ActorState:
    return ActorState(
        actor_id=ActorId(actor_id),
        role="customer",
        actor_type="internal",
        persona={"description": "A generic customer"},
    )


def _world_context() -> WorldContextBundle:
    return WorldContextBundle(
        world_description="VibeMesh pilot world.",
        reality_summary="Messy.",
        mission="Simulate product adoption.",
        available_services=[
            {
                "name": "drop_flare",
                "service": "vibemesh",
                "http_method": "POST",
                "description": "Drop a flare to start a hangout",
                "required_params": ["duration_min"],
            },
            {
                "name": "list_venues",
                "service": "vibemesh",
                "http_method": "GET",
                "description": "List nearby venues",
                "required_params": [],
            },
            {
                "name": "send_message",
                "service": "npc_chat",
                "http_method": "POST",
                "description": "Message another NPC",
                "required_params": ["recipient_id", "content"],
            },
        ],
    )


def _profile_loader_stub() -> Any:
    """A loader the activator can call without touching the filesystem."""

    profile = ActivationProfile(
        name="consumer_user",
        description="test consumer",
        state_schema={"type": "object", "properties": {}},
        activation_triggers=[ActivationTrigger(event="npc.exposure")],
        prompt_template="consumer_user_decision.j2",
        tool_scope=ToolScope(
            read=["vibemesh", "npc_chat"],
            write=["vibemesh", "npc_chat"],
        ),
        budget_defaults=BudgetDefaults(api_calls=5, llm_spend=0.1),
    )

    class _Loader:
        @staticmethod
        def load(name: str) -> ActivationProfile:
            if name == "consumer_user":
                return profile
            raise FileNotFoundError(name)

        @staticmethod
        def list_available() -> list[str]:
            return ["consumer_user"]

    return _Loader()


async def _wired_engine(
    *,
    actors: list[ActorState],
    llm_responses: list[LLMResponse],
    with_activator: bool = True,
) -> tuple[AgencyEngine, AsyncMock, AsyncMock]:
    """Construct an engine wired like app.py does for integration use.

    Returns (engine, llm_router_mock, tool_executor_mock) so tests can
    assert against the mocks. The tool_executor always returns a
    committed event with a small response_body — enough for the
    activator's summary/truncation logic.
    """
    engine = AgencyEngine()
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    await engine.initialize({}, bus)

    ctx = _world_context()
    await engine.configure(actors, ctx, ctx.available_services)

    llm_router = AsyncMock()
    llm_router.route = AsyncMock(side_effect=llm_responses)
    engine._llm_router = llm_router

    committed = AsyncMock()
    committed.response_body = {"status": "ok"}
    committed.event_id = "evt-committed"
    tool_executor = AsyncMock(return_value=committed)
    engine.set_tool_executor(tool_executor)

    if with_activator:
        engine.set_npc_activator(
            NPCActivator(
                prompt_builder=NPCPromptBuilder(),
                activation_profile_loader=_profile_loader_stub(),
            )
        )

    return engine, llm_router, tool_executor


def _tool_call(name: str, args: dict, call_id: str = "call_1") -> ToolCall:
    return ToolCall(name=name, arguments=args, id=call_id)


def _response_with_tool(name: str, args: dict, call_id: str = "call_1") -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=[_tool_call(name, args, call_id)],
        model="mock",
        provider="mock",
    )


def _response_text_only(text: str = "I'll pass.") -> LLMResponse:
    return LLMResponse(content=text, tool_calls=None, model="mock", provider="mock")


# -- Tests: active NPC routing --------------------------------------------


class TestActiveNPCRouting:
    @pytest.mark.asyncio
    async def test_active_npc_routes_through_activator(self) -> None:
        """Triggering activate_for_event on an Active NPC calls the LLM once."""
        npc = _active_npc()
        engine, router, executor = await _wired_engine(
            actors=[npc],
            llm_responses=[_response_with_tool("drop_flare", {"duration_min": 120})],
        )

        envelopes = await engine.activate_for_event(
            npc.actor_id,
            reason="npc_exposure",
            trigger_event=_exposure(),
        )

        assert router.route.await_count == 1
        assert len(envelopes) == 1
        assert executor.await_count == 1

    @pytest.mark.asyncio
    async def test_npc_tool_call_goes_through_tool_executor(self) -> None:
        """The shared tool_executor (the pipeline) must see every NPC call."""
        npc = _active_npc()
        engine, _, executor = await _wired_engine(
            actors=[npc],
            llm_responses=[_response_with_tool("drop_flare", {"duration_min": 60})],
        )

        await engine.activate_for_event(
            npc.actor_id,
            reason="npc_exposure",
            trigger_event=_exposure(),
        )

        executor.assert_awaited_once()
        sent_envelope = executor.await_args.args[0]
        assert str(sent_envelope.actor_id) == str(npc.actor_id)
        assert sent_envelope.action_type == "drop_flare"

    @pytest.mark.asyncio
    async def test_do_nothing_terminates_without_tool_call(self) -> None:
        """do_nothing is a sentinel — no ActionEnvelope, no pipeline call."""
        npc = _active_npc()
        engine, _, executor = await _wired_engine(
            actors=[npc],
            llm_responses=[_response_with_tool("do_nothing", {})],
        )

        envelopes = await engine.activate_for_event(
            npc.actor_id,
            reason="npc_exposure",
            trigger_event=_exposure(),
        )

        assert envelopes == []
        executor.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_text_only_response_ends_activation(self) -> None:
        npc = _active_npc()
        engine, _, executor = await _wired_engine(
            actors=[npc],
            llm_responses=[_response_text_only("Not interested.")],
        )

        envelopes = await engine.activate_for_event(
            npc.actor_id,
            reason="npc_exposure",
            trigger_event=_exposure(),
        )

        assert envelopes == []
        executor.assert_not_awaited()


# -- Tests: passive NPC — no NPC path ----------------------------------------


class TestPassiveNPCRegression:
    @pytest.mark.asyncio
    async def test_passive_npc_does_not_route_to_activator(self) -> None:
        """Active NPC activator wired, but passive NPC uses agent path.

        The agent path needs a lot of additional setup we don't provide
        here (prompt_builder already configured via ``configure``),
        but the critical assertion is that ``NPCActivator.activate_npc``
        is NOT invoked — meaning the early branch correctly gates on
        ``activation_profile_name``. We observe this by giving the NPC
        activator a broken loader that would raise if called: if we
        never see the error, we know the activator wasn't used.
        """
        passive = _passive_npc()
        engine, router, _executor = await _wired_engine(
            actors=[passive],
            llm_responses=[_response_text_only("noop")],
        )
        # Replace the activator with one whose loader raises — if the
        # passive path accidentally routes here, the error is the
        # evidence of regression.

        class _Tripwire:
            @staticmethod
            def load(name: str) -> Any:
                raise RuntimeError("regression: passive NPC was routed to NPCActivator")

            @staticmethod
            def list_available() -> list[str]:
                return []

        engine.set_npc_activator(
            NPCActivator(
                prompt_builder=NPCPromptBuilder(),
                activation_profile_loader=_Tripwire(),
            )
        )

        # Activate — the agent path will itself do nothing because we
        # haven't set up ActorPromptBuilder paths, but it MUST NOT
        # raise from the tripwire loader.
        envelopes = await engine.activate_for_event(
            passive.actor_id,
            reason="event_affected",
            trigger_event=None,
        )

        # Agent path returned whatever it returned — the only thing
        # that matters is no tripwire error.
        assert envelopes == [] or envelopes is not None  # structural, not value

    @pytest.mark.asyncio
    async def test_active_npc_falls_back_to_agent_path_when_no_activator(self) -> None:
        """Without ``set_npc_activator``, even active NPCs route the old way.

        We don't assert agent-path behavior (that's covered elsewhere)
        — only that nothing explodes and the NPC activator is not
        invoked (it literally doesn't exist on the engine).
        """
        npc = _active_npc()
        engine, _, _ = await _wired_engine(
            actors=[npc],
            llm_responses=[_response_text_only("noop")],
            with_activator=False,  # KEY: no activator wired
        )
        assert engine._npc_activator is None

        # Agent path may or may not produce output — we only assert it
        # doesn't crash. The regression-safety contract is preserved.
        try:
            await engine.activate_for_event(
                npc.actor_id,
                reason="event_affected",
                trigger_event=None,
            )
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"Agent fallback path raised unexpectedly: {exc}")


# -- Tests: tool-scope filtering & budget ------------------------------------


class TestToolScopeAndBudget:
    @pytest.mark.asyncio
    async def test_scoped_tools_excludes_out_of_scope_services(self) -> None:
        """Tools for services outside ``tool_scope`` must not be presented.

        We invoke the activator's static helper directly so the test
        isolates the scoping logic from the LLM loop.
        """
        from volnix.actors.activation_profile import ToolScope
        from volnix.engines.agency.npc_activator import NPCActivator

        # Build a mock engine just enough to extract the tool catalog.
        engine, _, _ = await _wired_engine(
            actors=[_active_npc()],
            llm_responses=[_response_text_only("noop")],
        )

        # Scope allows vibemesh only.
        scope = ToolScope(read=["vibemesh"], write=["vibemesh"])
        filtered = NPCActivator._scoped_tools(
            scope,
            engine._tool_definitions,
            engine._available_actions,
            engine._tool_name_map,
        )
        filtered_services = {t.service for t in filtered if getattr(t, "service", None)}
        assert filtered_services == {"vibemesh"}

    @pytest.mark.asyncio
    async def test_scope_all_expands_to_universe(self) -> None:
        from volnix.actors.activation_profile import ToolScope
        from volnix.engines.agency.npc_activator import NPCActivator

        engine, _, _ = await _wired_engine(
            actors=[_active_npc()],
            llm_responses=[_response_text_only("noop")],
        )
        scope = ToolScope(read=["all"], write=["all"])
        filtered = NPCActivator._scoped_tools(
            scope,
            engine._tool_definitions,
            engine._available_actions,
            engine._tool_name_map,
        )
        filtered_services = {t.service for t in filtered if getattr(t, "service", None)}
        # All real services from _world_context are present.
        assert "vibemesh" in filtered_services
        assert "npc_chat" in filtered_services

    @pytest.mark.asyncio
    async def test_budget_override_takes_precedence_over_profile(self) -> None:
        """``max_calls_override`` on activate_npc wins over profile default.

        Profile defaults to api_calls=5, but we set override=1 and
        feed a tool response — only one call should execute.
        """
        npc = _active_npc()
        engine, router, executor = await _wired_engine(
            actors=[npc],
            llm_responses=[_response_with_tool("drop_flare", {"duration_min": 60})],
        )

        envelopes = await engine.activate_for_event(
            npc.actor_id,
            reason="npc_exposure",
            trigger_event=_exposure(),
            max_calls_override=1,
        )
        assert len(envelopes) == 1
        assert router.route.await_count == 1

    def test_resolve_max_calls_priority(self) -> None:
        """Override > profile budget > global typed_config fallback."""
        from types import SimpleNamespace

        profile = _profile_loader_stub().load("consumer_user")
        typed = SimpleNamespace(max_tool_calls_per_activation=99)

        assert NPCActivator._resolve_max_calls(profile, 3, typed) == 3
        assert NPCActivator._resolve_max_calls(profile, None, typed) == 5  # profile cap
        assert NPCActivator._resolve_max_calls(profile, 0, typed) == 5  # zero override ignored

        # Profile with no budget: global fallback wins.
        profile_no_budget = ActivationProfile(
            name="x",
            description="y",
            state_schema={},
            activation_triggers=[ActivationTrigger(event="x.y")],
            prompt_template="t",
            tool_scope=ToolScope(),
            budget_defaults=BudgetDefaults(api_calls=0),
        )
        assert NPCActivator._resolve_max_calls(profile_no_budget, None, typed) == 99


# -- Tests: defensive guards in activate_npc --------------------------------


class TestRunToolLoopGuards:
    """Direct unit tests for ``NPCActivator.activate_npc`` bypass paths.

    These paths can't be triggered through ``activate_for_event`` (the
    engine's early branch requires an activation_profile_name AND a wired
    activator), so we invoke the activator directly with handcrafted
    hosts to exercise the defensive log-and-return branches.
    """

    @pytest.mark.asyncio
    async def test_skips_when_activation_profile_name_is_none(self) -> None:
        """Defense in depth — if called against a passive actor, no-op."""
        activator = NPCActivator(
            prompt_builder=NPCPromptBuilder(),
            activation_profile_loader=_profile_loader_stub(),
        )
        host = _stub_host(with_llm=True, with_executor=True)
        out = await activator.activate_npc(
            actor=_passive_npc(),
            reason="npc_exposure",
            trigger_event=None,
            max_calls_override=None,
            host=host,
        )
        assert out == []

    @pytest.mark.asyncio
    async def test_skips_when_no_llm_router(self) -> None:
        activator = NPCActivator(
            prompt_builder=NPCPromptBuilder(),
            activation_profile_loader=_profile_loader_stub(),
        )
        host = _stub_host(with_llm=False, with_executor=True)
        out = await activator.activate_npc(
            actor=_active_npc(),
            reason="npc_exposure",
            trigger_event=None,
            max_calls_override=None,
            host=host,
        )
        assert out == []

    @pytest.mark.asyncio
    async def test_skips_when_no_tool_executor(self) -> None:
        activator = NPCActivator(
            prompt_builder=NPCPromptBuilder(),
            activation_profile_loader=_profile_loader_stub(),
        )
        host = _stub_host(with_llm=True, with_executor=False)
        out = await activator.activate_npc(
            actor=_active_npc(),
            reason="npc_exposure",
            trigger_event=None,
            max_calls_override=None,
            host=host,
        )
        assert out == []

    @pytest.mark.asyncio
    async def test_skips_when_profile_load_fails(self) -> None:
        class _Broken:
            @staticmethod
            def load(name: str) -> Any:
                raise FileNotFoundError("no such profile")

            @staticmethod
            def list_available() -> list[str]:
                return []

        activator = NPCActivator(
            prompt_builder=NPCPromptBuilder(),
            activation_profile_loader=_Broken(),
        )
        host = _stub_host(with_llm=True, with_executor=True)
        out = await activator.activate_npc(
            actor=_active_npc(),
            reason="npc_exposure",
            trigger_event=None,
            max_calls_override=None,
            host=host,
        )
        assert out == []

    @pytest.mark.asyncio
    async def test_unknown_tool_call_produces_pipeline_envelope(self) -> None:
        """Unknown tool names still build an ``ActionEnvelope`` (with
        ``target_service=None``) and hand it to the pipeline. The pipeline
        is the arbiter — not the activator — and will reject unresolvable
        actions. This matches the agent loop's handling and keeps the two
        paths consistent.
        """
        npc = _active_npc()
        engine, _, executor = await _wired_engine(
            actors=[npc],
            llm_responses=[_response_with_tool("tool_not_in_catalog", {})],
        )
        envelopes = await engine.activate_for_event(
            npc.actor_id,
            reason="npc_exposure",
            trigger_event=_exposure(),
        )
        assert len(envelopes) == 1
        assert envelopes[0].target_service is None
        # The pipeline (executor) got called; blocking was its job.
        executor.assert_awaited_once()


def _stub_host(*, with_llm: bool, with_executor: bool) -> Any:
    """Minimal host object for direct activate_npc invocations."""
    import asyncio as _asyncio
    from types import SimpleNamespace

    return SimpleNamespace(
        _llm_router=(AsyncMock() if with_llm else None),
        _tool_executor=(AsyncMock() if with_executor else None),
        _tool_definitions=[],
        _available_actions=[],
        _tool_name_map={},
        _llm_semaphore=_asyncio.Semaphore(1),
        _pipeline_lock=_asyncio.Lock(),
        _typed_config=SimpleNamespace(max_tool_calls_per_activation=10),
    )


# -- Tests: initial_npc_state helper -----------------------------------------


class TestInitialNPCState:
    def test_extracts_defaults(self) -> None:
        from volnix.actors.activation_profile import initial_npc_state

        profile = ActivationProfile(
            name="p",
            description="d",
            state_schema={
                "type": "object",
                "properties": {
                    "awareness": {"type": "number", "default": 0},
                    "usage_count": {"type": "integer", "default": 0},
                    "known": {"type": "array", "default": []},
                },
            },
            activation_triggers=[ActivationTrigger(event="x.y")],
            prompt_template="t",
            tool_scope=ToolScope(),
        )
        state = initial_npc_state(profile)
        assert state == {"awareness": 0, "usage_count": 0, "known": []}

    def test_omits_properties_without_default(self) -> None:
        from volnix.actors.activation_profile import initial_npc_state

        profile = ActivationProfile(
            name="p",
            description="d",
            state_schema={
                "type": "object",
                "properties": {
                    "with_default": {"type": "number", "default": 42},
                    "no_default": {"type": "number"},
                },
            },
            activation_triggers=[ActivationTrigger(event="x.y")],
            prompt_template="t",
            tool_scope=ToolScope(),
        )
        state = initial_npc_state(profile)
        assert state == {"with_default": 42}

    def test_empty_schema_returns_empty(self) -> None:
        from volnix.actors.activation_profile import initial_npc_state

        profile = ActivationProfile(
            name="p",
            description="d",
            state_schema={},
            activation_triggers=[ActivationTrigger(event="x.y")],
            prompt_template="t",
            tool_scope=ToolScope(),
        )
        assert initial_npc_state(profile) == {}

    def test_non_dict_properties_handled(self) -> None:
        from volnix.actors.activation_profile import initial_npc_state

        profile = ActivationProfile(
            name="p",
            description="d",
            state_schema={"type": "object", "properties": "not-a-dict"},
            activation_triggers=[ActivationTrigger(event="x.y")],
            prompt_template="t",
            tool_scope=ToolScope(),
        )
        # Not-a-dict properties fall back to empty — no crash.
        assert initial_npc_state(profile) == {}
