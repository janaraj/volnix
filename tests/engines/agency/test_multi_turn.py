"""Tests for multi-turn agent activation loop.

Verifies that _activate_with_tool_loop correctly:
- Maintains a messages array across tool calls
- Terminates on text response, do_nothing, or max_tool_calls
- Executes each tool call through the pipeline executor
- Auto-posts text findings to team channel
- Records ledger entries per step
- Uses tool_choice from config
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from volnix.actors.state import ActorState
from volnix.core.events import WorldEvent
from volnix.core.types import ActorId, EntityId, ServiceId, Timestamp
from volnix.engines.agency.engine import AgencyEngine
from volnix.llm.types import LLMResponse, ToolCall
from volnix.simulation.world_context import WorldContextBundle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_world_context() -> WorldContextBundle:
    return WorldContextBundle(
        world_description="A corporate helpdesk simulation.",
        reality_summary="Messy reality.",
        mission="Evaluate support quality.",
        available_services=[
            {
                "name": "tickets_search",
                "service": "zendesk",
                "http_method": "GET",
                "description": "Search tickets",
                "required_params": ["query"],
            },
            {
                "name": "tickets_read",
                "service": "zendesk",
                "http_method": "GET",
                "description": "Read ticket",
                "required_params": ["ticket_id"],
            },
            {
                "name": "get_charge",
                "service": "stripe",
                "http_method": "GET",
                "description": "Get charge",
                "required_params": ["charge_id"],
            },
            {
                "name": "chat.postMessage",
                "service": "slack",
                "http_method": "POST",
                "description": "Post message",
                "required_params": ["text"],
            },
        ],
    )


def _make_actor(**kwargs) -> ActorState:
    defaults = {
        "actor_id": ActorId("test-agent"),
        "role": "support_agent",
        "actor_type": "internal",
        "current_goal": "Investigate tickets",
        "goal_context": "Investigate and share findings",
        "persona": {"description": "Thorough support agent"},
        "autonomous": True,
        "team_channel": "#team",
    }
    defaults.update(kwargs)
    return ActorState(**defaults)


def _make_timestamp(tick: float = 1.0) -> Timestamp:
    now = datetime.now(UTC)
    return Timestamp(world_time=now, wall_time=now, tick=tick)


def _make_world_event(
    actor_id: str = "external-agent",
    action: str = "update_ticket",
    tick: float = 1.0,
    target_entity: str = "ticket-1",
) -> WorldEvent:
    return WorldEvent(
        event_type=f"world.{action}",
        timestamp=_make_timestamp(tick),
        actor_id=ActorId(actor_id),
        service_id=ServiceId("zendesk"),
        action=action,
        target_entity=EntityId(target_entity),
        input_data={"status": "updated"},
    )


def _make_tool_response(name: str, args: dict, tool_id: str = "") -> LLMResponse:
    """LLM response with a single tool call."""
    return LLMResponse(
        content="",
        tool_calls=[ToolCall(name=name, arguments=args, id=tool_id or f"call_{name}")],
        model="test",
        provider="test",
    )


def _make_text_response(text: str) -> LLMResponse:
    """LLM response with text (agent's findings)."""
    return LLMResponse(
        content=text,
        tool_calls=None,
        model="test",
        provider="test",
    )


def _make_sequential_router(*responses: LLMResponse) -> AsyncMock:
    """Mock router that returns responses in sequence."""
    router = AsyncMock()
    router.route = AsyncMock(side_effect=list(responses))
    return router


def _make_committed_event_mock() -> AsyncMock:
    """Mock that looks like a committed WorldEvent (frozen model)."""
    event = AsyncMock()
    event.response_body = {"tickets": [{"id": "T1", "subject": "Refund request"}]}
    event.event_id = "evt-committed-1"
    return event


def _make_tool_executor() -> AsyncMock:
    """Mock pipeline executor returning a committed event."""
    executor = AsyncMock()
    executor.return_value = _make_committed_event_mock()
    return executor


async def _create_engine(
    actors: list[ActorState] | None = None,
    config_overrides: dict | None = None,
) -> AgencyEngine:
    """Create and configure an AgencyEngine for testing."""
    ctx = _make_world_context()
    if actors is None:
        actors = [_make_actor()]

    raw_config: dict = {}
    if config_overrides:
        raw_config.update(config_overrides)

    bus = AsyncMock()
    bus.subscribe = AsyncMock()

    engine = AgencyEngine()
    await engine.initialize(raw_config, bus)
    await engine.configure(actors, ctx, ctx.available_services)
    return engine


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_single_tool_then_text():
    """Agent makes 1 tool call, then responds with text findings."""
    router = _make_sequential_router(
        _make_tool_response("tickets_search", {"query": "refund", "reasoning": "search"}),
        _make_text_response("Customer needs refund for order #123"),
    )
    executor = _make_tool_executor()
    engine = await _create_engine()
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    envelopes = await engine._activate_with_tool_loop(
        actor,
        "subscription_immediate",
        trigger_event=None,
    )

    # 1 tool call envelope + 1 channel post envelope
    assert len(envelopes) == 2
    assert envelopes[0].action_type == "tickets_search"
    assert envelopes[1].action_type == "chat.postMessage"
    assert executor.call_count == 2  # tool execution + channel post
    assert router.route.call_count == 2


async def test_multiple_tools_then_text():
    """Agent makes 3 tool calls before sharing findings."""
    router = _make_sequential_router(
        _make_tool_response("tickets_search", {"query": "refund", "reasoning": "s1"}),
        _make_tool_response("tickets_read", {"ticket_id": "T1", "reasoning": "s2"}),
        _make_tool_response("get_charge", {"charge_id": "ch_1", "reasoning": "s3"}),
        _make_text_response("Refund is valid, charge was $50"),
    )
    executor = _make_tool_executor()
    engine = await _create_engine()
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    envelopes = await engine._activate_with_tool_loop(
        actor,
        "subscription_immediate",
        trigger_event=None,
    )

    # 3 tool calls + 1 channel post
    assert len(envelopes) == 4
    assert router.route.call_count == 4


async def test_max_tool_calls_limit():
    """Loop stops at max_tool_calls_per_activation."""
    responses = [
        _make_tool_response("tickets_search", {"query": f"q{i}", "reasoning": f"r{i}"})
        for i in range(20)
    ]
    router = _make_sequential_router(*responses)
    executor = _make_tool_executor()
    engine = await _create_engine(config_overrides={"max_tool_calls_per_activation": 5})
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    envelopes = await engine._activate_with_tool_loop(
        actor,
        "autonomous_continue",
        trigger_event=None,
    )

    assert len(envelopes) == 5
    assert router.route.call_count == 5


async def test_text_on_first_call():
    """Agent responds with text immediately — no tool calls needed."""
    router = _make_sequential_router(
        _make_text_response("Everything looks fine, no action needed"),
    )
    executor = _make_tool_executor()
    engine = await _create_engine()
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    envelopes = await engine._activate_with_tool_loop(
        actor,
        "subscription_immediate",
        trigger_event=None,
    )

    # Text response → auto-post to channel (1 envelope)
    assert len(envelopes) == 1
    assert envelopes[0].action_type == "chat.postMessage"


async def test_do_nothing_terminates():
    """do_nothing tool call terminates the loop with 0 envelopes."""
    router = _make_sequential_router(
        _make_tool_response("do_nothing", {"reasoning": "Nothing to do"}),
    )
    executor = _make_tool_executor()
    engine = await _create_engine()
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    envelopes = await engine._activate_with_tool_loop(
        actor,
        "autonomous_continue",
        trigger_event=None,
    )

    assert len(envelopes) == 0
    assert executor.call_count == 0


async def test_messages_array_structure():
    """Verify messages passed to LLM on second call contain tool call + result."""
    router = _make_sequential_router(
        _make_tool_response(
            "tickets_search", {"query": "test", "reasoning": "look"}, tool_id="call_123"
        ),
        _make_text_response("Done"),
    )
    executor = _make_tool_executor()
    engine = await _create_engine()
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    await engine._activate_with_tool_loop(
        actor,
        "subscription_immediate",
        trigger_event=None,
    )

    # Check the second LLM call's request
    second_call_request = router.route.call_args_list[1][0][0]
    messages = second_call_request.messages
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[2]["role"] == "assistant"
    assert "tool_calls" in messages[2]
    assert messages[3]["role"] == "tool"
    assert messages[3]["tool_call_id"] == "call_123"
    # Tool result should contain the response body
    assert "T1" in messages[3]["content"]


async def test_parallel_activations():
    """Multiple agents run concurrently via asyncio.gather."""
    import time

    async def slow_route(request, engine_name, use_case):
        await asyncio.sleep(0.05)
        return _make_text_response("findings")

    router = AsyncMock()
    router.route = AsyncMock(side_effect=slow_route)
    executor = _make_tool_executor()
    agents = [_make_actor(actor_id=ActorId(f"agent-{i}"), role=f"role-{i}") for i in range(3)]
    engine = await _create_engine(actors=agents)
    engine._llm_router = router
    engine.set_tool_executor(executor)

    start = time.monotonic()
    tasks = [
        engine._activate_with_tool_loop(a, "subscription_immediate", None)
        for a in engine._actor_states.values()
    ]
    results = await asyncio.gather(*tasks)
    elapsed = time.monotonic() - start

    # Parallel: should be faster than 3 * 0.05 = 0.15s
    assert elapsed < 0.12
    assert all(isinstance(r, list) for r in results)


async def test_pipeline_rejection_continues():
    """When pipeline rejects (returns None), agent gets BLOCKED message and continues."""
    committed = _make_committed_event_mock()
    executor = AsyncMock(side_effect=[None, committed, committed])

    router = _make_sequential_router(
        _make_tool_response("risky_action", {"reasoning": "try"}, tool_id="call_1"),
        _make_tool_response(
            "tickets_search", {"query": "safe", "reasoning": "retry"}, tool_id="call_2"
        ),
        _make_text_response("Adjusted approach after block"),
    )
    engine = await _create_engine()
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    envelopes = await engine._activate_with_tool_loop(
        actor,
        "subscription_immediate",
        trigger_event=None,
    )

    # First blocked (0), second succeeded (1), text posted (1)
    assert len(envelopes) == 2
    # Verify BLOCKED message was in the messages for second call
    second_request = router.route.call_args_list[1][0][0]
    tool_msgs = [m for m in second_request.messages if m.get("role") == "tool"]
    assert any("BLOCKED" in m["content"] for m in tool_msgs)


async def test_self_continuation_removed():
    """Autonomous non-lead agent's own committed event does NOT trigger re-activation."""
    actor = _make_actor(autonomous=True)
    actor.is_lead = False
    engine = await _create_engine(actors=[actor])
    executor = _make_tool_executor()
    engine.set_tool_executor(executor)
    engine._llm_router = AsyncMock()

    # Create event from this actor's own action
    own_event = _make_world_event(
        actor_id=str(actor.actor_id),
        action="tickets_search",
        tick=5,
    )

    envelopes = await engine.notify(own_event)

    # No self-continuation — old behavior removed
    assert len(envelopes) == 0


async def test_tool_choice_from_config():
    """LLMRequest uses tool_choice from AgencyConfig, not hardcoded."""
    router = _make_sequential_router(_make_text_response("done"))
    executor = _make_tool_executor()
    engine = await _create_engine(config_overrides={"tool_choice_mode": "auto"})
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    await engine._activate_with_tool_loop(actor, "test", trigger_event=None)

    request = router.route.call_args_list[0][0][0]
    assert request.tool_choice == "auto"
    # Should NOT have system_prompt/user_content — uses messages instead
    assert request.messages is not None
    assert len(request.messages) >= 2


async def test_goal_context_updated_on_text():
    """Agent's goal_context is updated with its text findings."""
    router = _make_sequential_router(
        _make_tool_response("tickets_search", {"query": "q", "reasoning": "r"}),
        _make_text_response("The customer's refund is overdue by 3 days"),
    )
    executor = _make_tool_executor()
    engine = await _create_engine()
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    await engine._activate_with_tool_loop(actor, "test", trigger_event=None)

    assert "refund is overdue" in actor.goal_context


async def test_no_executor_returns_empty():
    """If tool_executor is not set, activation returns empty list."""
    router = _make_sequential_router(_make_text_response("done"))
    engine = await _create_engine()
    engine._llm_router = router
    # Deliberately NOT setting tool_executor
    actor = list(engine._actor_states.values())[0]

    envelopes = await engine._activate_with_tool_loop(actor, "test", None)

    assert len(envelopes) == 0
    assert router.route.call_count == 0


async def test_no_team_channel_skips_post():
    """Agent without team_channel doesn't auto-post findings."""
    router = _make_sequential_router(
        _make_text_response("My findings"),
    )
    executor = _make_tool_executor()
    engine = await _create_engine(
        actors=[_make_actor(team_channel=None)],
    )
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    envelopes = await engine._activate_with_tool_loop(actor, "test", None)

    # No channel post, but goal_context still updated
    assert len(envelopes) == 0
    assert "findings" in actor.goal_context.lower()


# ---------------------------------------------------------------------------
# Message persistence + re-activation tests
# ---------------------------------------------------------------------------


async def test_messages_persisted_on_actor():
    """After activation, actor.activation_messages contains the conversation."""
    router = _make_sequential_router(
        _make_tool_response("tickets_search", {"query": "q", "reasoning": "r"}),
        _make_text_response("Done investigating"),
    )
    executor = _make_tool_executor()
    engine = await _create_engine()
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    assert actor.activation_messages == []

    await engine._activate_with_tool_loop(actor, "continue_work", None)

    # Messages persisted: system + user + assistant+tool_call + tool_result + ...
    assert len(actor.activation_messages) >= 4
    assert actor.activation_messages[0]["role"] == "system"
    assert actor.activation_messages[1]["role"] == "user"


async def test_reactivation_continues_conversation():
    """Re-activation appends to persisted messages, not fresh start."""
    # First activation
    router1 = _make_sequential_router(
        _make_tool_response("tickets_search", {"query": "q", "reasoning": "r"}),
        _make_text_response("Initial findings"),
    )
    executor = _make_tool_executor()
    engine = await _create_engine()
    engine._llm_router = router1
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    await engine._activate_with_tool_loop(actor, "continue_work", None)
    msg_count_after_first = len(actor.activation_messages)
    assert msg_count_after_first >= 4

    # Re-activation
    router2 = _make_sequential_router(_make_text_response("Updated synthesis"))
    engine._llm_router = router2

    await engine._activate_with_tool_loop(actor, "subscription_match", None)

    # Messages grew (reactivation context appended + new LLM exchange)
    assert len(actor.activation_messages) > msg_count_after_first
    # Second LLM call should have received the full prior conversation + reactivation context
    second_request = router2.route.call_args_list[0][0][0]
    assert len(second_request.messages) > msg_count_after_first
    # Should contain a re-activation context message
    reactivation_msgs = [
        m for m in second_request.messages if "Re-activation" in (m.get("content") or "")
    ]
    assert len(reactivation_msgs) >= 1


async def test_reactivation_includes_lead_instructions() -> None:
    """Lead re-activation messages must include 'do NOT re-delegate' instructions."""
    # Create a lead actor with prior activation_messages (simulating re-activation)
    lead = _make_actor(
        actor_id=ActorId("lead-agent"),
        role="supervisor",
        is_lead=True,
        autonomous=True,
        activation_messages=[
            {"role": "system", "content": "You are the lead."},
            {"role": "user", "content": "Start investigation."},
            {"role": "assistant", "content": "I'll delegate to the team."},
            {"role": "user", "content": "[Activation complete.]"},
        ],
    )
    # Need a teammate so team_size > 1 (prompt builder guard for lead note)
    teammate = _make_actor(
        actor_id=ActorId("senior-agent"),
        role="senior_agent",
        is_lead=False,
        autonomous=True,
    )
    engine = await _create_engine(actors=[lead, teammate])

    # Router returns text response (agent shares findings, terminates loop)
    router = _make_sequential_router(
        _make_text_response("Team findings look complete."),
    )
    engine._llm_router = router
    engine._tool_executor = _make_tool_executor()

    trigger = _make_world_event()
    await engine._activate_with_tool_loop(lead, "continue_work", trigger)

    # Verify the re-activation message includes lead-specific instructions.
    # The last user message appended before the LLM call contains both
    # autonomous instructions and re-activation context.
    call_args = router.route.call_args_list[0][0][0]
    # Find the message with re-activation content (last appended user message)
    reactivation_msg = next(
        (
            m
            for m in reversed(call_args.messages)
            if m.get("role") == "user" and "Re-activation" in (m.get("content") or "")
        ),
        None,
    )
    assert reactivation_msg is not None, "Re-activation context should be present in messages"
    content = reactivation_msg["content"]
    assert "Active Monitoring" in content, (
        f"Re-activation message should include Phase 2 'Active Monitoring' for lead. Got: {content[:300]}"
    )
    assert "Do NOT investigate on your own" in content, (
        "Lead should be told not to investigate on their own"
    )


# ---------------------------------------------------------------------------
# Multi-call response handling + actions_per_turn budget plumbing
# ---------------------------------------------------------------------------


def _make_multi_tool_response(*calls: tuple[str, dict]) -> LLMResponse:
    """LLM response containing multiple tool calls in a single message.

    Mirrors the real behavior of OpenAI, Anthropic, and Google Gemini when
    the model composes a turn as several coordinated actions.
    """
    return LLMResponse(
        content="",
        tool_calls=[
            ToolCall(name=name, arguments=args, id=f"call_{i}_{name}")
            for i, (name, args) in enumerate(calls)
        ],
        model="test",
        provider="test",
    )


async def test_multi_call_response_all_executed():
    """All tool calls in a single LLM response are executed, not just the first.

    This is the real fix for the duplicate-call bug: before the fix, only
    ``response.tool_calls[0]`` was processed and the rest were silently
    dropped — causing the LLM to re-emit them on subsequent iterations
    and producing runtime duplicates.
    """
    router = _make_sequential_router(
        _make_multi_tool_response(
            ("tickets_search", {"query": "refund", "reasoning": "search"}),
            ("tickets_read", {"ticket_id": "T1", "reasoning": "read"}),
            ("get_charge", {"charge_id": "ch_1", "reasoning": "check"}),
        ),
        _make_text_response("All three done"),
    )
    executor = _make_tool_executor()
    engine = await _create_engine()
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    envelopes = await engine._activate_with_tool_loop(
        actor,
        "subscription_immediate",
        trigger_event=None,
    )

    # 3 tool envelopes from iteration 1 (one LLM response with 3 calls),
    # plus 1 auto-posted chat from iteration 2's text response = 4 envelopes.
    # Only 2 LLM round-trips total.
    assert len(envelopes) == 4
    action_types = [e.action_type for e in envelopes]
    assert "tickets_search" in action_types
    assert "tickets_read" in action_types
    assert "get_charge" in action_types
    assert "chat.postMessage" in action_types
    # Exactly 2 LLM calls — the three tools shared one round-trip
    assert router.route.call_count == 2


async def test_multi_call_response_respects_budget():
    """A multi-call response that exceeds the budget executes only up to the cap.

    When ``max_calls_override`` is 3 and the LLM returns 5 tool calls in one
    response, only the first 3 execute and the loop terminates with
    ``terminated_by = "max_tool_calls"``.
    """
    router = _make_sequential_router(
        _make_multi_tool_response(
            ("tickets_search", {"query": "a", "reasoning": "r1"}),
            ("tickets_read", {"ticket_id": "T1", "reasoning": "r2"}),
            ("get_charge", {"charge_id": "ch1", "reasoning": "r3"}),
            ("tickets_search", {"query": "b", "reasoning": "r4"}),
            ("tickets_read", {"ticket_id": "T2", "reasoning": "r5"}),
        ),
    )
    executor = _make_tool_executor()
    engine = await _create_engine()
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    envelopes = await engine._activate_with_tool_loop(
        actor,
        "game_turn",
        trigger_event=None,
        max_calls_override=3,
    )

    # Only 3 of 5 tool calls executed — budget cap enforced mid-response
    assert len(envelopes) == 3
    # Only 1 LLM call — we didn't need a second round-trip
    assert router.route.call_count == 1


async def test_blocked_tool_in_multi_call_preserves_siblings():
    """A blocked tool in a multi-call response does not stop sibling calls.

    When the pipeline rejects one of several tool calls in a single response,
    the BLOCKED message is fed back to the LLM (in history) and the remaining
    calls in the same response continue to execute.
    """
    committed = _make_committed_event_mock()
    # First call succeeds, second blocked, third succeeds, fourth is the
    # auto-post of the text response (also succeeds).
    executor = AsyncMock(side_effect=[committed, None, committed, committed])

    router = _make_sequential_router(
        _make_multi_tool_response(
            ("tickets_search", {"query": "a", "reasoning": "r1"}),
            ("tickets_read", {"ticket_id": "T1", "reasoning": "r2"}),
            ("get_charge", {"charge_id": "ch1", "reasoning": "r3"}),
        ),
        _make_text_response("Two succeeded, one blocked"),
    )
    engine = await _create_engine()
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    envelopes = await engine._activate_with_tool_loop(
        actor,
        "subscription_immediate",
        trigger_event=None,
    )

    # 2 successful tool envelopes (blocked one isn't in envelopes) + 1 auto-posted chat
    assert len(envelopes) == 3
    action_types = [e.action_type for e in envelopes]
    assert action_types.count("tickets_search") == 1
    assert action_types.count("get_charge") == 1
    # Blocked tool NOT in envelopes
    assert "tickets_read" not in action_types

    # BLOCKED message must have been fed back into the next LLM iteration
    second_request = router.route.call_args_list[1][0][0]
    tool_msgs = [m for m in second_request.messages if m.get("role") == "tool"]
    assert any("BLOCKED" in m["content"] for m in tool_msgs)


async def test_game_turn_budget_plumbing():
    """``activate_for_game_turn(max_actions=N)`` caps the loop at N tool calls.

    Queues five single-call responses; with ``max_actions=3`` only three
    should execute and the loop should exit at the cap.
    """
    responses = [
        _make_tool_response("tickets_search", {"query": f"q{i}", "reasoning": f"r{i}"})
        for i in range(5)
    ]
    router = _make_sequential_router(*responses)
    executor = _make_tool_executor()
    engine = await _create_engine(
        actors=[_make_actor(actor_id=ActorId("player-1"), role="buyer")],
    )
    engine._llm_router = router
    engine.set_tool_executor(executor)

    envelopes = await engine.activate_for_game_turn(
        ActorId("player-1"),
        round_number=1,
        total_rounds=5,
        standings_summary="tied",
        max_actions=3,
    )

    # Exactly 3 tool calls executed despite 5 responses queued
    assert len(envelopes) == 3
    assert router.route.call_count == 3


async def test_autonomous_uses_config_default_when_no_override():
    """Non-game activation with no override uses ``max_tool_calls_per_activation``.

    Ensures autonomous lead-agent workflows are unaffected by the game-turn
    override plumbing — they keep using the global config value.
    """
    responses = [
        _make_tool_response("tickets_search", {"query": f"q{i}", "reasoning": f"r{i}"})
        for i in range(15)
    ]
    router = _make_sequential_router(*responses)
    executor = _make_tool_executor()
    engine = await _create_engine(config_overrides={"max_tool_calls_per_activation": 7})
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    envelopes = await engine._activate_with_tool_loop(
        actor,
        "autonomous_work",
        trigger_event=None,
        max_calls_override=None,
    )

    # Uses the config default of 7, not the global 10 or any override
    assert len(envelopes) == 7
    assert router.route.call_count == 7


async def test_autopost_skipped_when_agent_already_chat_posted():
    """Framework does not double-post when the agent already called chat.postMessage.

    The pre-fix bug: if the agent explicitly called chat.postMessage in one
    iteration and then returned plain text in the next, the auto-post branch
    would post the text to the same channel — producing the visible
    "1 second apart" duplicate chat messages in the run.
    """
    router = _make_sequential_router(
        _make_tool_response(
            "chat.postMessage",
            {"channel": "#team", "text": "Explicit post", "reasoning": "announce"},
            tool_id="call_chat",
        ),
        _make_text_response("Explicit post"),
    )
    executor = _make_tool_executor()
    engine = await _create_engine()
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    envelopes = await engine._activate_with_tool_loop(
        actor,
        "subscription_immediate",
        trigger_event=None,
    )

    # Exactly one chat.postMessage — the explicit call. Auto-post must not fire.
    chat_envelopes = [e for e in envelopes if e.action_type == "chat.postMessage"]
    assert len(chat_envelopes) == 1


async def test_game_turn_preserves_conversation_across_rounds():
    """Consecutive game turns share the same conversation history.

    This is the generic cross-round memory invariant required by ANY
    turn-based game (negotiation, trading, auction, debate, …). Without
    it, the LLM starts each round as a blank slate and defaults to
    re-emitting its opening move. Verified against run_d5165eb40ad8,
    where every round re-proposed opening terms because the reset wiped
    the conversation each round.

    This test does NOT reference any game-type-specific tool names — it
    uses a generic tool ("tickets_search") to prove the mechanism itself
    is game-type-agnostic.
    """
    router = _make_sequential_router(
        # Round 1
        _make_tool_response("tickets_search", {"query": "round1", "reasoning": "r1"}),
        _make_text_response("Round 1 done"),
        # Round 2
        _make_tool_response("tickets_search", {"query": "round2", "reasoning": "r2"}),
        _make_text_response("Round 2 done"),
        # Round 3
        _make_tool_response("tickets_search", {"query": "round3", "reasoning": "r3"}),
        _make_text_response("Round 3 done"),
    )
    executor = _make_tool_executor()
    engine = await _create_engine(
        actors=[_make_actor(actor_id=ActorId("player-1"), role="player")],
    )
    engine._llm_router = router
    engine.set_tool_executor(executor)

    # Round 1
    await engine.activate_for_game_turn(
        ActorId("player-1"),
        round_number=1,
        total_rounds=3,
        standings_summary="tied",
        max_actions=2,
    )
    actor = engine._actor_states[ActorId("player-1")]
    round1_msg_count = len(actor.activation_messages)
    assert round1_msg_count >= 4, "Round 1 must leave messages in history"

    # Round 2 — conversation MUST carry over (not reset)
    await engine.activate_for_game_turn(
        ActorId("player-1"),
        round_number=2,
        total_rounds=3,
        standings_summary="tied",
        max_actions=2,
    )
    round2_msg_count = len(actor.activation_messages)
    assert round2_msg_count > round1_msg_count, "Round 2 must APPEND to prior history, not reset it"

    # Round 3 — still accumulating
    await engine.activate_for_game_turn(
        ActorId("player-1"),
        round_number=3,
        total_rounds=3,
        standings_summary="tied",
        max_actions=2,
    )
    round3_msg_count = len(actor.activation_messages)
    assert round3_msg_count > round2_msg_count

    # On round 3's LLM call, the messages sent should include the
    # round-1 AND round-2 tool calls + results (proof of memory).
    # The last LLM route call is for round 3; its messages argument
    # must contain references to all prior rounds.
    last_call = router.route.call_args_list[-1]
    last_request = last_call[0][0]
    last_messages = last_request.messages

    # Count assistant tool_call entries — should be at least 2 (one per
    # prior round's completed move)
    assistant_with_calls = [
        m for m in last_messages if m.get("role") == "assistant" and m.get("tool_calls")
    ]
    assert len(assistant_with_calls) >= 2, (
        f"Round 3 should see at least 2 prior assistant tool_calls in history, "
        f"got {len(assistant_with_calls)}. Full message roles: "
        f"{[m.get('role') for m in last_messages]}"
    )

    # And the ROUND marker text should have been injected somewhere in
    # the conversation so the LLM knows it's on round 3
    user_contents = [m.get("content", "") for m in last_messages if m.get("role") == "user"]
    assert any("ROUND 3" in c for c in user_contents), (
        "Round 3 marker must be present in the user messages"
    )


async def test_game_turn_round_context_is_generic():
    """The round_ctx text injected by activate_for_game_turn is game-type-agnostic.

    Contains no negotiation-specific, trading-specific, or any other
    game-type-specific terminology. Game-type guidance lives in the
    agent persona, not in this runtime context. This invariant keeps
    the generic turn machinery usable by any future game type without
    modification.
    """
    router = _make_sequential_router(_make_text_response("done"))
    executor = _make_tool_executor()
    engine = await _create_engine(
        actors=[_make_actor(actor_id=ActorId("p1"), role="player")],
    )
    engine._llm_router = router
    engine.set_tool_executor(executor)

    await engine.activate_for_game_turn(
        ActorId("p1"),
        round_number=1,
        total_rounds=5,
        standings_summary="initial",
        max_actions=3,
    )

    # Inspect the actual LLM request that went out on round 1 — the
    # round_ctx is rendered into either goal_context (fresh start) or
    # an appended user message. Either way it must appear in messages
    # sent to the LLM.
    first_request = router.route.call_args_list[0][0][0]
    messages = first_request.messages
    full_text = "\n".join(str(m.get("content", "") or "") for m in messages)

    # Must contain the ROUND marker and budget
    assert "ROUND 1/5" in full_text, (
        f"Round marker missing from LLM request. Got: {full_text[:500]}"
    )
    assert "3 tool calls" in full_text, f"Budget missing from LLM request. Got: {full_text[:500]}"

    # The round_ctx block itself must NOT contain game-type-specific
    # terminology. Extract just the ROUND marker context by finding
    # the "ROUND 1/5" line and reading forward up to the double newline
    # or end.
    round_idx = full_text.find("ROUND 1/5")
    round_block = full_text[round_idx : round_idx + 1000]

    # Must NOT contain negotiation terminology in the generic round_ctx
    # (word-boundary match to avoid false positives like "proceed")
    import re

    negotiation_terms = [
        "negotiate",
        "BATNA",
        "propose",
    ]
    # "counter", "accept", "reject", "deal" could legitimately appear
    # in generic game guidance. "propose", "negotiate", and "BATNA" are
    # unmistakably negotiation-specific.
    for word in negotiation_terms:
        pattern = rf"\b{re.escape(word)}\b"
        assert not re.search(pattern, round_block, re.IGNORECASE), (
            f"Generic round context contains negotiation-specific word "
            f"'{word}' in the ROUND block: {round_block[:500]}"
        )
    # Must NOT contain trading-specific terminology in round_ctx
    trading_terms = ["portfolio", "create_order", "ticker"]
    for word in trading_terms:
        pattern = rf"\b{re.escape(word)}\b"
        assert not re.search(pattern, round_block, re.IGNORECASE), (
            f"Generic round context contains trading-specific word "
            f"'{word}' in the ROUND block: {round_block[:500]}"
        )


async def test_do_nothing_short_circuits_multi_call_response():
    """``do_nothing`` in a multi-call response stops the loop immediately.

    The LLM may return ``[A, do_nothing, C]`` in one response (unusual but
    possible). The first call executes, the do_nothing terminates the loop,
    and the third call is NOT executed.
    """
    router = _make_sequential_router(
        _make_multi_tool_response(
            ("tickets_search", {"query": "a", "reasoning": "first"}),
            ("do_nothing", {"reasoning": "nothing else to do"}),
            ("get_charge", {"charge_id": "ch1", "reasoning": "should not run"}),
        ),
    )
    executor = _make_tool_executor()
    engine = await _create_engine()
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    envelopes = await engine._activate_with_tool_loop(
        actor,
        "autonomous_continue",
        trigger_event=None,
    )

    # Only the first call executed; do_nothing halted the loop before get_charge
    assert len(envelopes) == 1
    assert envelopes[0].action_type == "tickets_search"
    # Only one LLM call — do_nothing terminated the outer loop too
    assert router.route.call_count == 1
