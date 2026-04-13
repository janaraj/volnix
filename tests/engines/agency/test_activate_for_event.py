"""Tests for ``AgencyEngine.activate_for_event`` — the unified entry.

Covers the ``activate_for_event`` method that :class:`GameOrchestrator`
calls directly (MF2):

- Unknown actor returns [] without raising
- ``state_summary`` is injected as a user message at the top of
  ``activation_messages``
- Injection is bounded by a rolling window to cap prompt size
- ``Event`` triggers that aren't ``WorldEvent`` are passed through as None
  (the tool loop only forwards world events)
- The activation reason is forwarded to ``_activate_with_tool_loop`` and
  the prompt builder picks it up on the first activation
- Agency's bus ``subscriptions`` ClassVar is empty (Fact B — never fired)

Prompt builder tests verify:
- ``game_kickstart`` / ``game_event`` both render the game-player
  instruction block
- ``_build_action_history`` runs for non-autonomous actors (no autonomous
  guard)
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from volnix.actors.state import ActorState
from volnix.core.events import Event, WorldEvent
from volnix.core.types import ActorId, EventId, ServiceId, Timestamp
from volnix.engines.agency.engine import AgencyEngine
from volnix.engines.agency.prompt_builder import ActorPromptBuilder
from volnix.llm.types import LLMResponse, ToolCall
from volnix.simulation.world_context import WorldContextBundle

# ---------------------------------------------------------------------------
# Shared fixtures (minimal versions of the helpers in test_multi_turn.py)
# ---------------------------------------------------------------------------


def _make_world_context() -> WorldContextBundle:
    return WorldContextBundle(
        world_description="Q3 steel supply negotiation.",
        reality_summary="Messy reality.",
        mission="Close the best deal.",
        available_services=[
            {
                "name": "negotiate_propose",
                "service": "game",
                "http_method": "POST",
                "description": "Propose deal terms",
                "required_params": ["deal_id"],
            },
            {
                "name": "chat.postMessage",
                "service": "slack",
                "http_method": "POST",
                "description": "Post a message",
                "required_params": ["text"],
            },
        ],
    )


def _make_actor(
    actor_id: str = "buyer-001",
    role: str = "buyer",
    autonomous: bool = False,
    persona: dict | None = None,
    goal_context: str | None = "Close the best deal.",
) -> ActorState:
    return ActorState(
        actor_id=ActorId(actor_id),
        role=role,
        actor_type="internal",
        autonomous=autonomous,
        persona=persona or {"description": "Q3 procurement lead"},
        current_goal="Maximize deal value.",
        goal_context=goal_context,
        team_channel="#team",
    )


def _make_timestamp() -> Timestamp:
    now = datetime.now(UTC)
    return Timestamp(world_time=now, wall_time=now, tick=0)


def _make_world_event(
    actor_id: str = "supplier-001",
    action: str = "negotiate_propose",
) -> WorldEvent:
    return WorldEvent(
        event_id=EventId(f"evt-{actor_id}-{action}"),
        event_type=f"world.{action}",
        timestamp=_make_timestamp(),
        actor_id=ActorId(actor_id),
        service_id=ServiceId("game"),
        action=action,
        input_data={"deal_id": "deal-q3", "price": 90},
    )


def _make_non_world_event(event_type: str = "game.kickstart") -> Event:
    return Event(event_type=event_type, timestamp=_make_timestamp())


def _make_router(*responses: LLMResponse) -> AsyncMock:
    router = AsyncMock()
    router.route = AsyncMock(side_effect=list(responses))
    return router


def _make_text_response(text: str) -> LLMResponse:
    return LLMResponse(content=text, tool_calls=None, model="test", provider="test")


def _make_tool_response(name: str, args: dict, tool_id: str = "") -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=[ToolCall(name=name, arguments=args, id=tool_id or f"call_{name}")],
        model="test",
        provider="test",
    )


def _make_tool_executor() -> AsyncMock:
    executor = AsyncMock()
    committed = AsyncMock()
    committed.response_body = {"object": "negotiation_proposal", "status": "proposed"}
    committed.event_id = "evt-committed"
    executor.return_value = committed
    return executor


async def _create_engine(actors: list[ActorState] | None = None) -> AgencyEngine:
    ctx = _make_world_context()
    engine = AgencyEngine()
    bus = AsyncMock()
    bus.subscribe = AsyncMock()
    await engine.initialize({}, bus)
    await engine.configure(
        actors or [_make_actor()],
        ctx,
        ctx.available_services,
    )
    return engine


# ---------------------------------------------------------------------------
# activate_for_event — basic routing
# ---------------------------------------------------------------------------


class TestActivateForEventBasics:
    @pytest.mark.asyncio
    async def test_unknown_actor_returns_empty(self):
        engine = await _create_engine()
        envelopes = await engine.activate_for_event(
            ActorId("stranger-999"),
            reason="game_kickstart",
            trigger_event=None,
        )
        assert envelopes == []

    @pytest.mark.asyncio
    async def test_known_actor_routes_to_tool_loop(self):
        """activate_for_event delegates to _activate_with_tool_loop and returns its envelopes."""
        router = _make_router(_make_text_response("ready"))
        executor = _make_tool_executor()
        engine = await _create_engine()
        engine._llm_router = router
        engine.set_tool_executor(executor)

        envelopes = await engine.activate_for_event(
            ActorId("buyer-001"),
            reason="game_kickstart",
            trigger_event=None,
        )
        # Text response → one chat post from the auto-post branch
        assert len(envelopes) == 1
        assert envelopes[0].action_type == "chat.postMessage"

    @pytest.mark.asyncio
    async def test_max_calls_override_forwarded(self):
        """For game activations, the turn-ending model stops after the
        first game move commits (service_id='game'). The max_calls_override
        is a safety ceiling, not the turn structure.
        """
        router = _make_router(
            _make_tool_response("negotiate_propose", {"deal_id": "deal-q3", "price": 80}),
            _make_tool_response("negotiate_propose", {"deal_id": "deal-q3", "price": 82}),
        )
        engine = await _create_engine()
        engine._llm_router = router
        engine.set_tool_executor(_make_tool_executor())

        envelopes = await engine.activate_for_event(
            ActorId("buyer-001"),
            reason="game_event",
            trigger_event=_make_world_event(),
            max_calls_override=2,
        )
        # Turn-ending: first negotiate_propose commits → turn ends.
        # Only 1 envelope, not 2, because the game move terminates the turn.
        assert len(envelopes) == 1


# ---------------------------------------------------------------------------
# state_summary injection
# ---------------------------------------------------------------------------


class TestStateSummaryInjection:
    @pytest.mark.asyncio
    async def test_state_summary_appended_as_user_message(self):
        """state_summary is injected into conversation messages by the tool loop.

        State summary is now passed as a parameter to _activate_with_tool_loop
        and injected INSIDE the loop (works on both first and re-activation).
        After the loop, it persists in activation_messages.
        """
        engine = await _create_engine()
        engine._llm_router = _make_router(_make_text_response("ok"))
        engine.set_tool_executor(_make_tool_executor())

        actor = engine._actor_states[ActorId("buyer-001")]
        # Pre-seed some activation history so the state_summary is appended to it
        actor.activation_messages = [
            {"role": "user", "content": "previous turn"},
            {"role": "assistant", "content": "previous response"},
        ]

        await engine.activate_for_event(
            ActorId("buyer-001"),
            reason="game_event",
            trigger_event=_make_world_event(),
            state_summary="deal-q3 status=proposed, price=90",
        )
        # State summary is injected into messages by the tool loop and
        # persisted to activation_messages after the loop completes.
        user_msgs = [m for m in actor.activation_messages if m.get("role") == "user"]
        contents = [m["content"] for m in user_msgs]
        assert any("deal-q3 status=proposed" in c for c in contents)
        assert any("[game state update]" in c for c in contents)

    @pytest.mark.asyncio
    async def test_no_state_summary_when_argument_empty(self):
        """An empty state_summary is treated as absent."""
        engine = await _create_engine()
        engine._llm_router = _make_router(_make_text_response("ok"))
        engine.set_tool_executor(_make_tool_executor())

        actor = engine._actor_states[ActorId("buyer-001")]
        await engine.activate_for_event(
            ActorId("buyer-001"),
            reason="game_kickstart",
            trigger_event=None,
            state_summary="",
        )
        # No injected "[game state update]" marker
        for msg in actor.activation_messages:
            assert "[game state update]" not in msg.get("content", "")

    @pytest.mark.asyncio
    async def test_state_summary_trimmed_to_bounded_window(self):
        """Pre-activation trim caps activation_messages with pinned system/user prompt.

        Step 1 (P6.3-fix.6) pins the first 2 messages (system + user
        prompt) so the agent never loses its identity. The rolling
        window truncation only drops entries from position 2 onwards.

        State summary is now injected INSIDE the tool loop (not before
        trim), so trim math doesn't include it. The tool loop receives
        it as a parameter and appends to the messages array after building.
        """
        engine = await _create_engine()

        actor = engine._actor_states[ActorId("buyer-001")]
        # Stuff 30 entries in — the cap is 20; we expect it to be trimmed
        # with the first 2 pinned.
        actor.activation_messages = [{"role": "user", "content": f"old-{i}"} for i in range(30)]

        captured_len: list[int] = []
        captured_summaries: list[str | None] = []

        async def fake_loop(
            _actor,
            _reason,
            _trigger_event,
            max_calls_override=None,
            append_closure=True,
            state_summary=None,
        ):
            captured_len.append(len(_actor.activation_messages))
            captured_summaries.append(state_summary)
            return []

        engine._activate_with_tool_loop = fake_loop  # type: ignore[assignment]

        await engine.activate_for_event(
            ActorId("buyer-001"),
            reason="game_event",
            trigger_event=None,
            state_summary="new ground truth",
        )
        assert captured_len == [20]  # Exactly the cap (trim before tool loop)
        # State summary passed as parameter, not in activation_messages
        assert captured_summaries[0] == "new ground truth"
        # Pinned first 2 survive: old-0, old-1. Rolling: 28 entries
        # trimmed to 18 (cap - 2). Oldest surviving: old-12.
        assert actor.activation_messages[0]["content"] == "old-0"
        assert actor.activation_messages[1]["content"] == "old-1"
        assert actor.activation_messages[2]["content"] == "old-12"


# ---------------------------------------------------------------------------
# Trigger event filtering
# ---------------------------------------------------------------------------


class TestTriggerEventFiltering:
    @pytest.mark.asyncio
    async def test_world_event_forwarded_to_tool_loop(self):
        """A WorldEvent trigger flows through to the tool loop."""
        engine = await _create_engine()

        captured_triggers: list = []

        async def fake_loop(
            actor,
            reason,
            trigger_event,
            max_calls_override=None,
            append_closure=True,
            state_summary=None,
        ):
            captured_triggers.append(trigger_event)
            return []

        engine._activate_with_tool_loop = fake_loop  # type: ignore[assignment]
        world_event = _make_world_event()
        await engine.activate_for_event(
            ActorId("buyer-001"),
            reason="game_event",
            trigger_event=world_event,
        )
        assert captured_triggers == [world_event]

    @pytest.mark.asyncio
    async def test_non_world_event_passed_as_none(self):
        """Non-WorldEvent triggers become ``None`` at the tool loop boundary."""
        engine = await _create_engine()
        captured_triggers: list = []

        async def fake_loop(
            actor,
            reason,
            trigger_event,
            max_calls_override=None,
            append_closure=True,
            state_summary=None,
        ):
            captured_triggers.append(trigger_event)
            return []

        engine._activate_with_tool_loop = fake_loop  # type: ignore[assignment]
        non_world = _make_non_world_event("game.active_state_changed")
        await engine.activate_for_event(
            ActorId("buyer-001"),
            reason="game_event",
            trigger_event=non_world,
        )
        assert captured_triggers == [None]

    @pytest.mark.asyncio
    async def test_none_trigger_stays_none(self):
        engine = await _create_engine()
        captured_triggers: list = []

        async def fake_loop(
            actor,
            reason,
            trigger_event,
            max_calls_override=None,
            append_closure=True,
            state_summary=None,
        ):
            captured_triggers.append(trigger_event)
            return []

        engine._activate_with_tool_loop = fake_loop  # type: ignore[assignment]
        await engine.activate_for_event(
            ActorId("buyer-001"),
            reason="game_kickstart",
            trigger_event=None,
        )
        assert captured_triggers == [None]


# ---------------------------------------------------------------------------
# Reason forwarding
# ---------------------------------------------------------------------------


class TestReasonForwarding:
    @pytest.mark.asyncio
    async def test_reason_forwarded_to_tool_loop(self):
        engine = await _create_engine()
        captured_reasons: list[str] = []

        async def fake_loop(
            actor,
            reason,
            trigger_event,
            max_calls_override=None,
            append_closure=True,
            state_summary=None,
        ):
            captured_reasons.append(reason)
            return []

        engine._activate_with_tool_loop = fake_loop  # type: ignore[assignment]
        for reason in ("game_kickstart", "game_event", "autonomous_tick"):
            await engine.activate_for_event(
                ActorId("buyer-001"),
                reason=reason,
                trigger_event=None,
            )
        # Two-phase: with max_read_calls=None (default), research_budget=0
        # → Phase 1 skipped, only game_move fires.
        # autonomous_tick → single call (unchanged)
        assert captured_reasons == [
            "game_move",  # from game_kickstart (research skipped, budget=0)
            "game_move",  # from game_event (same)
            "autonomous_tick",  # non-game, single-phase
        ]


# ---------------------------------------------------------------------------
# Subscriptions ClassVar (Fact B)
# ---------------------------------------------------------------------------


class TestSubscriptionsClassVar:
    def test_subscriptions_is_empty(self):
        """AgencyEngine.subscriptions is [] after Cycle B (Fact B cleanup)."""
        assert AgencyEngine.subscriptions == []

    @pytest.mark.asyncio
    async def test_start_does_not_subscribe_to_legacy_topics(self):
        """engine.start() makes no legacy ``world`` / ``simulation`` subscriptions."""
        engine = await _create_engine()
        bus = engine._bus
        await engine.start()
        topics = [call.args[0] for call in bus.subscribe.call_args_list]
        assert "world" not in topics
        assert "simulation" not in topics


# ---------------------------------------------------------------------------
# Prompt builder — game-reason dispatch
# ---------------------------------------------------------------------------


class TestPromptBuilderGameReasons:
    """Prompt builder renders game instructions for all game-* reasons."""

    def _make_builder(self) -> ActorPromptBuilder:
        return ActorPromptBuilder(world_context=_make_world_context())

    def test_game_kickstart_renders_game_instructions(self):
        builder = self._make_builder()
        actor = _make_actor(autonomous=False)
        prompt = builder.build_individual_prompt(
            actor=actor,
            trigger_event=None,
            activation_reason="game_kickstart",
            available_actions=[],
        )
        assert "game player" in prompt
        assert "moves commit immediately" in prompt
        # Must not mention the autonomous delegation flow
        assert "INVESTIGATE" not in prompt

    def test_game_event_renders_game_instructions(self):
        builder = self._make_builder()
        actor = _make_actor(autonomous=False)
        prompt = builder.build_individual_prompt(
            actor=actor,
            trigger_event=_make_world_event(),
            activation_reason="game_event",
            available_actions=[],
        )
        assert "game player" in prompt
        assert "MOVE" in prompt  # research-then-move model
        assert "negotiate_propose" in prompt

    def test_game_turn_reason_does_not_render_game_instructions(self):
        """Legacy ``game_turn`` reason is no longer recognized (deleted in B.10).

        The prompt's "You are a game player" instruction block is only
        emitted for ``game_kickstart`` / ``game_event`` reasons. The word
        "game player" may appear elsewhere (persona, team roster) so the
        assertion checks the specific instruction phrase instead.
        """
        builder = self._make_builder()
        actor = _make_actor(autonomous=False)
        prompt = builder.build_individual_prompt(
            actor=actor,
            trigger_event=None,
            activation_reason="game_turn",
            available_actions=[],
        )
        assert "moves commit immediately" not in prompt

    def test_non_game_reason_does_not_render_game_instructions(self):
        builder = self._make_builder()
        actor = _make_actor(autonomous=False)
        prompt = builder.build_individual_prompt(
            actor=actor,
            trigger_event=None,
            activation_reason="subscription_match",
            available_actions=[],
        )
        assert "game player" not in prompt


# ---------------------------------------------------------------------------
# Prompt builder — action history for non-autonomous actors
# ---------------------------------------------------------------------------


class TestPromptBuilderActionHistory:
    """_build_action_history runs for all actors now (dropped autonomous guard)."""

    def test_non_autonomous_actor_gets_action_history_section(self):
        """A game player (non-autonomous) sees the action history block."""
        builder = ActorPromptBuilder(world_context=_make_world_context())
        actor = _make_actor(autonomous=False)
        prompt = builder.build_individual_prompt(
            actor=actor,
            trigger_event=None,
            activation_reason="game_kickstart",
            available_actions=[
                {
                    "name": "negotiate_propose",
                    "http_method": "POST",
                    "service": "game",
                    "description": "",
                },
            ],
        )
        assert "### Your Action History" in prompt

    def test_action_history_placeholder_on_fresh_actor(self):
        """A fresh actor (no interactions) sees the 'No actions taken yet' line."""
        builder = ActorPromptBuilder(world_context=_make_world_context())
        actor = _make_actor(autonomous=False)
        prompt = builder.build_individual_prompt(
            actor=actor,
            trigger_event=None,
            activation_reason="game_event",
            available_actions=[],
        )
        assert "No actions taken yet" in prompt


# ---------------------------------------------------------------------------
# B3 — max_activation_messages comes from AgencyConfig
# ---------------------------------------------------------------------------


class TestMaxActivationMessagesConfig:
    """The rolling window cap is read from AgencyConfig, not hardcoded."""

    @pytest.mark.asyncio
    async def test_custom_cap_respected(self):
        """Injecting ``max_activation_messages=5`` trims to 5."""
        import asyncio as _asyncio

        from volnix.core.types import ActorId
        from volnix.engines.agency.engine import AgencyEngine

        engine = AgencyEngine()
        bus = AsyncMock()
        bus.subscribe = AsyncMock()
        await engine.initialize({"max_activation_messages": 5}, bus)
        ctx = _make_world_context()
        await engine.configure([_make_actor()], ctx, ctx.available_services)

        actor = engine._actor_states[ActorId("buyer-001")]
        actor.activation_messages = [{"role": "user", "content": f"m-{i}"} for i in range(10)]

        captured_len: list[int] = []

        async def fake_loop(
            _actor,
            _reason,
            _trigger_event,
            max_calls_override=None,
            append_closure=True,
            state_summary=None,
        ):
            captured_len.append(len(_actor.activation_messages))
            return []

        engine._activate_with_tool_loop = fake_loop  # type: ignore[assignment]
        await engine.activate_for_event(
            ActorId("buyer-001"),
            reason="game_event",
            trigger_event=None,
            state_summary="truth",
        )
        assert captured_len == [5]
        _ = _asyncio  # silence unused-import warning

    @pytest.mark.asyncio
    async def test_default_cap_is_20(self):
        """Default AgencyConfig.max_activation_messages is 20."""
        from volnix.engines.agency.config import AgencyConfig

        assert AgencyConfig().max_activation_messages == 20


# ---------------------------------------------------------------------------
# B1 — Per-actor lock prevents concurrent same-actor activations
# ---------------------------------------------------------------------------


class TestPerActorActivationLock:
    """Two concurrent activate_for_event calls on the same actor serialize.

    This protects against the GameOrchestrator feedback-loop race where
    Player A's activation is still in _activate_with_tool_loop when the
    orchestrator fires another activation for Player A.
    """

    @pytest.mark.asyncio
    async def test_concurrent_same_actor_activations_serialize(self):
        import asyncio as _asyncio

        engine = await _create_engine()
        order: list[str] = []
        release_first = _asyncio.Event()

        async def slow_loop(
            _actor,
            _reason,
            _trigger_event,
            max_calls_override=None,
            append_closure=True,
            state_summary=None,
        ):
            order.append("enter")
            await release_first.wait()
            order.append("exit")
            return []

        engine._activate_with_tool_loop = slow_loop  # type: ignore[assignment]

        task1 = _asyncio.create_task(
            engine.activate_for_event(
                ActorId("buyer-001"),
                reason="game_event",
                trigger_event=None,
            )
        )
        task2 = _asyncio.create_task(
            engine.activate_for_event(
                ActorId("buyer-001"),
                reason="game_event",
                trigger_event=None,
            )
        )
        # Let task1 reach the slow section
        await _asyncio.sleep(0.01)
        # Both tasks are scheduled but only one should be inside the loop
        assert order == ["enter"]
        # Release the first task
        release_first.set()
        await _asyncio.gather(task1, task2)
        # Second task ran AFTER the first exited — strict ordering
        assert order == ["enter", "exit", "enter", "exit"]

    @pytest.mark.asyncio
    async def test_different_actors_run_concurrently(self):
        """Per-actor locks must not serialize across actors."""
        import asyncio as _asyncio

        engine = await _create_engine(
            actors=[
                _make_actor(actor_id="buyer-001", role="buyer"),
                _make_actor(actor_id="supplier-001", role="supplier"),
            ]
        )

        inside: set[str] = set()
        max_concurrent = {"v": 0}
        release = _asyncio.Event()

        async def slow_loop(
            _actor,
            _reason,
            _trigger_event,
            max_calls_override=None,
            append_closure=True,
            state_summary=None,
        ):
            inside.add(str(_actor.actor_id))
            max_concurrent["v"] = max(max_concurrent["v"], len(inside))
            await release.wait()
            inside.discard(str(_actor.actor_id))
            return []

        engine._activate_with_tool_loop = slow_loop  # type: ignore[assignment]

        t1 = _asyncio.create_task(
            engine.activate_for_event(ActorId("buyer-001"), reason="game_event", trigger_event=None)
        )
        t2 = _asyncio.create_task(
            engine.activate_for_event(
                ActorId("supplier-001"), reason="game_event", trigger_event=None
            )
        )
        await _asyncio.sleep(0.01)
        assert max_concurrent["v"] == 2  # both actors inside simultaneously
        release.set()
        await _asyncio.gather(t1, t2)

    @pytest.mark.asyncio
    async def test_lock_released_on_exception(self):
        """If the tool loop raises, the per-actor lock is released."""
        import asyncio as _asyncio

        engine = await _create_engine()

        async def raising_loop(
            _actor,
            _reason,
            _trigger_event,
            max_calls_override=None,
            append_closure=True,
            state_summary=None,
        ):
            raise RuntimeError("boom")

        engine._activate_with_tool_loop = raising_loop  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="boom"):
            await engine.activate_for_event(
                ActorId("buyer-001"),
                reason="game_event",
                trigger_event=None,
            )

        # Second call should succeed — lock is released
        calls = {"n": 0}

        async def ok_loop(
            _actor,
            _reason,
            _trigger_event,
            max_calls_override=None,
            append_closure=True,
            state_summary=None,
        ):
            calls["n"] += 1
            return []

        engine._activate_with_tool_loop = ok_loop  # type: ignore[assignment]
        await engine.activate_for_event(
            ActorId("buyer-001"),
            reason="game_event",
            trigger_event=None,
        )
        assert calls["n"] == 1
        _ = _asyncio  # silence unused-import warning

    @pytest.mark.asyncio
    async def test_lock_is_lazy_created(self):
        """The first activation creates the lock; subsequent reuse the same one."""
        engine = await _create_engine()
        assert engine._actor_activation_locks == {}
        engine._activate_with_tool_loop = AsyncMock(return_value=[])  # type: ignore[assignment]
        await engine.activate_for_event(
            ActorId("buyer-001"), reason="game_event", trigger_event=None
        )
        first_lock = engine._actor_activation_locks[ActorId("buyer-001")]
        await engine.activate_for_event(
            ActorId("buyer-001"), reason="game_event", trigger_event=None
        )
        assert engine._actor_activation_locks[ActorId("buyer-001")] is first_lock

    def test_autonomous_actor_still_gets_action_history(self):
        """Autonomous actor continues to render the block (no regression)."""
        builder = ActorPromptBuilder(world_context=_make_world_context())
        actor = _make_actor(autonomous=True)
        prompt = builder.build_individual_prompt(
            actor=actor,
            trigger_event=None,
            activation_reason="autonomous_work",
            available_actions=[],
        )
        assert "### Your Action History" in prompt


# ---------------------------------------------------------------------------
# _sanitize_history_for_game_move — Phase 1 history cleanup
# ---------------------------------------------------------------------------


from volnix.engines.agency.engine import _sanitize_history_for_game_move


def _tc(name: str, tc_id: str) -> dict:
    """Helper: build a minimal tool_call dict."""
    return {
        "id": tc_id,
        "type": "function",
        "function": {"name": name, "arguments": "{}"},
    }


GAME_TOOLS = frozenset({"negotiate_propose", "negotiate_counter", "negotiate_accept"})


class TestSanitizeHistoryForGameMove:
    """Unit tests for the Phase-1 history sanitization function."""

    def test_non_game_tools_replaced_with_summary(self):
        """Non-game tool_call + results → single assistant text with data."""
        msgs = [
            {"role": "system", "content": "You are a buyer."},
            {"role": "user", "content": "Your mission."},
            {"role": "assistant", "tool_calls": [_tc("databases.retrieve", "c1")]},
            {"role": "tool", "tool_call_id": "c1", "content": '{"price": 95}'},
            {"role": "assistant", "tool_calls": [_tc("pages.retrieve", "c2")]},
            {"role": "tool", "tool_call_id": "c2", "content": '{"stock": 200}'},
        ]
        result = _sanitize_history_for_game_move(msgs, GAME_TOOLS)

        # System + user preserved, two assistant+tool blocks → 1 summary
        assert result[0] == msgs[0]
        assert result[1] == msgs[1]
        assert len(result) == 3
        summary = result[2]
        assert summary["role"] == "assistant"
        assert "research" in summary["content"].lower()
        assert '{"price": 95}' in summary["content"]
        assert '{"stock": 200}' in summary["content"]

    def test_game_tools_preserved(self):
        """Messages with game tool_calls are kept as-is."""
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "usr"},
            {
                "role": "assistant",
                "tool_calls": [_tc("negotiate_propose", "g1")],
                "_provider_metadata": {"thinking_blocks": []},
            },
            {"role": "tool", "tool_call_id": "g1", "content": '{"ok": true}'},
        ]
        result = _sanitize_history_for_game_move(msgs, GAME_TOOLS)
        assert result == msgs

    def test_system_and_user_preserved(self):
        """System and user messages are never removed."""
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "mission"},
            {"role": "user", "content": "[game state update] deal status"},
            {"role": "assistant", "tool_calls": [_tc("conversations.list", "c1")]},
            {"role": "tool", "tool_call_id": "c1", "content": "channels"},
        ]
        result = _sanitize_history_for_game_move(msgs, GAME_TOOLS)
        roles = [m["role"] for m in result]
        assert roles.count("system") == 1
        assert roles.count("user") >= 2
        assert result[0]["content"] == "sys"
        assert result[1]["content"] == "mission"
        # State summary user msg also preserved
        user_contents = [m["content"] for m in result if m["role"] == "user"]
        assert any("game state update" in c for c in user_contents)

    def test_text_assistant_preserved(self):
        """Text-only assistant messages (no tool_calls) are kept."""
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "usr"},
            {"role": "assistant", "content": "My analysis shows low supply."},
        ]
        result = _sanitize_history_for_game_move(msgs, GAME_TOOLS)
        assert result == msgs

    def test_no_tool_calls_unchanged(self):
        """When no tool_calls exist, output equals input."""
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "usr"},
        ]
        result = _sanitize_history_for_game_move(msgs, GAME_TOOLS)
        assert result == msgs

    def test_empty_messages(self):
        """Empty list → empty list."""
        assert _sanitize_history_for_game_move([], GAME_TOOLS) == []

    def test_no_mutation_of_input(self):
        """The original message list is not modified."""
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "usr"},
            {"role": "assistant", "tool_calls": [_tc("databases.retrieve", "c1")]},
            {"role": "tool", "tool_call_id": "c1", "content": "data"},
        ]
        import copy

        original = copy.deepcopy(msgs)
        _sanitize_history_for_game_move(msgs, GAME_TOOLS)
        assert msgs == original

    def test_truncation_over_limit(self):
        """Research findings exceeding the char limit are truncated."""
        from volnix.engines.agency.config import AgencyConfig

        char_limit = AgencyConfig().history_sanitize_char_limit

        big_content = "x" * 5000
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "usr"},
            {"role": "assistant", "tool_calls": [_tc("db.query", "c1")]},
            {"role": "tool", "tool_call_id": "c1", "content": big_content},
            {"role": "assistant", "tool_calls": [_tc("db.query", "c2")]},
            {"role": "tool", "tool_call_id": "c2", "content": big_content},
        ]
        result = _sanitize_history_for_game_move(msgs, GAME_TOOLS)
        summary = result[2]
        assert "[...truncated]" in summary["content"]
        # Total content (excluding header) should be capped
        assert len(summary["content"]) < char_limit + 200

    def test_research_summary_position(self):
        """Summary is inserted where the first removed assistant msg was."""
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "usr"},
            {"role": "user", "content": "[game state update] deal info"},
            {"role": "assistant", "tool_calls": [_tc("databases.retrieve", "c1")]},
            {"role": "tool", "tool_call_id": "c1", "content": "data"},
        ]
        result = _sanitize_history_for_game_move(msgs, GAME_TOOLS)
        # Position 0: system, 1: user, 2: user (state), 3: assistant (summary)
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert result[2]["role"] == "user"
        assert result[2]["content"] == "[game state update] deal info"
        assert result[3]["role"] == "assistant"
        assert "research" in result[3]["content"].lower()

    def test_state_summary_ordering(self):
        """State summary user message stays before the research summary."""
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "mission"},
            {"role": "user", "content": "[game state update] deal-q3 proposed"},
            {"role": "assistant", "tool_calls": [_tc("pages.retrieve", "c1")]},
            {"role": "tool", "tool_call_id": "c1", "content": '{"inventory": 50}'},
        ]
        result = _sanitize_history_for_game_move(msgs, GAME_TOOLS)
        # State summary (user) at index 2, research summary (assistant) at 3
        assert result[2]["role"] == "user"
        assert "game state update" in result[2]["content"]
        assert result[3]["role"] == "assistant"
        assert '{"inventory": 50}' in result[3]["content"]
