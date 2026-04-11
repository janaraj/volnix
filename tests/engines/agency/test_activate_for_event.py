"""Tests for ``AgencyEngine.activate_for_event`` — the Cycle B unified entry.

Covers the new ``activate_for_event`` method that
:class:`GameOrchestrator` calls directly (Option D, MF2):

- Unknown actor returns [] without raising
- ``state_summary`` is injected as a user message at the top of
  ``activation_messages``
- Injection is bounded by a rolling window to cap prompt size
- ``Event`` triggers that aren't ``WorldEvent`` are passed through as None
  (the tool loop only forwards world events)
- The activation reason is forwarded to ``_activate_with_tool_loop`` and
  the prompt builder picks it up on the first activation
- Legacy ``activate_for_game_turn`` still works (deleted in B.10)
- Agency's bus ``subscriptions`` ClassVar is empty (Fact B — never fired)

Prompt builder tests verify the Cycle B additions:
- ``game_kickstart`` / ``game_event`` / ``game_turn`` all render the
  game-player instruction block
- ``_build_action_history`` runs for non-autonomous actors now that the
  guard is dropped
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
        """The override is respected by the inner tool loop cap."""
        # 5 tool responses, but cap at 2
        router = _make_router(
            _make_tool_response("negotiate_propose", {"deal_id": "deal-q3", "price": 80}),
            _make_tool_response("negotiate_propose", {"deal_id": "deal-q3", "price": 82}),
            _make_tool_response("negotiate_propose", {"deal_id": "deal-q3", "price": 84}),
            _make_tool_response("negotiate_propose", {"deal_id": "deal-q3", "price": 86}),
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
        # Exactly 2 executed, not 4
        assert len(envelopes) == 2


# ---------------------------------------------------------------------------
# state_summary injection
# ---------------------------------------------------------------------------


class TestStateSummaryInjection:
    @pytest.mark.asyncio
    async def test_state_summary_appended_as_user_message(self):
        """state_summary is appended to activation_messages as a user entry."""
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
        # The last user message before activation should be our state summary
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
        """Pre-activation trim caps activation_messages to the rolling window.

        Monkey-patches ``_activate_with_tool_loop`` so we can observe
        ``activation_messages`` immediately after state_summary injection,
        before the tool loop grows it further.
        """
        engine = await _create_engine()

        actor = engine._actor_states[ActorId("buyer-001")]
        # Stuff 30 entries in — the cap is 20; we expect it to be trimmed.
        actor.activation_messages = [{"role": "user", "content": f"old-{i}"} for i in range(30)]

        captured_len: list[int] = []
        captured_contents: list[list[str]] = []

        async def fake_loop(_actor, _reason, _trigger_event, max_calls_override=None):
            captured_len.append(len(_actor.activation_messages))
            captured_contents.append([m["content"] for m in _actor.activation_messages])
            return []

        engine._activate_with_tool_loop = fake_loop  # type: ignore[assignment]

        await engine.activate_for_event(
            ActorId("buyer-001"),
            reason="game_event",
            trigger_event=None,
            state_summary="new ground truth",
        )
        assert captured_len == [20]  # Exactly the cap
        contents = captured_contents[0]
        # With 30 original + 1 summary = 31, trimmed to last 20.
        # So first kept entry is old-11, last 19 originals are old-11..old-29,
        # and the 20th entry is the state_summary.
        assert contents[0] == "old-11"
        assert contents[-2] == "old-29"
        assert "[game state update]" in contents[-1]
        assert "new ground truth" in contents[-1]


# ---------------------------------------------------------------------------
# Trigger event filtering
# ---------------------------------------------------------------------------


class TestTriggerEventFiltering:
    @pytest.mark.asyncio
    async def test_world_event_forwarded_to_tool_loop(self):
        """A WorldEvent trigger flows through to the tool loop."""
        engine = await _create_engine()

        captured_triggers: list = []

        async def fake_loop(actor, reason, trigger_event, max_calls_override=None):
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

        async def fake_loop(actor, reason, trigger_event, max_calls_override=None):
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

        async def fake_loop(actor, reason, trigger_event, max_calls_override=None):
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

        async def fake_loop(actor, reason, trigger_event, max_calls_override=None):
            captured_reasons.append(reason)
            return []

        engine._activate_with_tool_loop = fake_loop  # type: ignore[assignment]
        for reason in ("game_kickstart", "game_event", "autonomous_tick"):
            await engine.activate_for_event(
                ActorId("buyer-001"),
                reason=reason,
                trigger_event=None,
            )
        assert captured_reasons == ["game_kickstart", "game_event", "autonomous_tick"]


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
        assert "current state" in prompt

    def test_game_turn_renders_game_instructions_legacy(self):
        """Legacy ``game_turn`` reason still maps to game instructions."""
        builder = self._make_builder()
        actor = _make_actor(autonomous=False)
        prompt = builder.build_individual_prompt(
            actor=actor,
            trigger_event=None,
            activation_reason="game_turn",
            available_actions=[],
        )
        assert "game player" in prompt

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
