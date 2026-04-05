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
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from volnix.actors.state import ActorState
from volnix.core.events import WorldEvent
from volnix.core.types import ActorId, EntityId, ServiceId, Timestamp
from volnix.engines.agency.engine import AgencyEngine
from volnix.engines.agency.prompt_builder import ActorPromptBuilder
from volnix.llm.types import LLMResponse, ToolCall, ToolDefinition
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
            {"name": "tickets_search", "service": "zendesk", "http_method": "GET",
             "description": "Search tickets", "required_params": ["query"]},
            {"name": "tickets_read", "service": "zendesk", "http_method": "GET",
             "description": "Read ticket", "required_params": ["ticket_id"]},
            {"name": "get_charge", "service": "stripe", "http_method": "GET",
             "description": "Get charge", "required_params": ["charge_id"]},
            {"name": "chat.postMessage", "service": "slack", "http_method": "POST",
             "description": "Post message", "required_params": ["text"]},
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
        actor, "subscription_immediate", trigger_event=None,
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
        actor, "subscription_immediate", trigger_event=None,
    )

    # 3 tool calls + 1 channel post
    assert len(envelopes) == 4
    assert router.route.call_count == 4


async def test_max_tool_calls_limit():
    """Loop stops at max_tool_calls_per_activation."""
    responses = [
        _make_tool_response(f"tickets_search", {"query": f"q{i}", "reasoning": f"r{i}"})
        for i in range(20)
    ]
    router = _make_sequential_router(*responses)
    executor = _make_tool_executor()
    engine = await _create_engine(config_overrides={"max_tool_calls_per_activation": 5})
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    envelopes = await engine._activate_with_tool_loop(
        actor, "autonomous_continue", trigger_event=None,
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
        actor, "subscription_immediate", trigger_event=None,
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
        actor, "autonomous_continue", trigger_event=None,
    )

    assert len(envelopes) == 0
    assert executor.call_count == 0


async def test_messages_array_structure():
    """Verify messages passed to LLM on second call contain tool call + result."""
    router = _make_sequential_router(
        _make_tool_response("tickets_search", {"query": "test", "reasoning": "look"}, tool_id="call_123"),
        _make_text_response("Done"),
    )
    executor = _make_tool_executor()
    engine = await _create_engine()
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    await engine._activate_with_tool_loop(
        actor, "subscription_immediate", trigger_event=None,
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
    agents = [
        _make_actor(actor_id=ActorId(f"agent-{i}"), role=f"role-{i}")
        for i in range(3)
    ]
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
        _make_tool_response("tickets_search", {"query": "safe", "reasoning": "retry"}, tool_id="call_2"),
        _make_text_response("Adjusted approach after block"),
    )
    engine = await _create_engine()
    engine._llm_router = router
    engine.set_tool_executor(executor)
    actor = list(engine._actor_states.values())[0]

    envelopes = await engine._activate_with_tool_loop(
        actor, "subscription_immediate", trigger_event=None,
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
        actor_id=str(actor.actor_id), action="tickets_search", tick=5,
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
        m for m in second_request.messages
        if "Re-activation" in (m.get("content") or "")
    ]
    assert len(reactivation_msgs) >= 1
