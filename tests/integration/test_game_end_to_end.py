"""End-to-end scripted game integration test (Cycle B.12).

Exercises the full stack in a single test: real ``VolnixApp``, real
bus, real state engine, real pipeline, real ``GameOrchestrator``,
real ``AgencyEngine`` — the ONLY mock is a scripted LLM router that
returns pre-programmed ``negotiate_*`` tool calls.

The test scripts a three-event deal-closed scenario:

    1. Buyer activation → negotiate_propose
    2. Supplier activation → negotiate_counter
    3. Buyer activation → negotiate_accept
    -> orchestrator publishes GameTerminatedEvent(reason="deal_closed")

This is the capstone proving that every B.5-B.11 piece wires together
for a live run. Before this test, the orchestrator + agency + pipeline
were each exercised in isolation. Here they run together under the real
app.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from volnix.actors.definition import ActorDefinition
from volnix.actors.internal_profile import InternalAgentProfile
from volnix.actors.state import ActorState
from volnix.core.types import ActorId, ActorType
from volnix.engines.game.definition import (
    DealDecl,
    FlowConfig,
    GameDefinition,
    GameEntitiesConfig,
    NegotiationField,
    PlayerBriefDecl,
    WinCondition,
)
from volnix.engines.game.events import GameTerminatedEvent
from volnix.engines.world_compiler.plan import WorldPlan
from volnix.llm.types import LLMResponse, ToolCall

# ---------------------------------------------------------------------------
# Scripted LLM router
# ---------------------------------------------------------------------------


class ScriptedLLMRouter:
    """Fake LLM router that returns pre-programmed responses keyed by actor.

    Inspects the ``LLMRequest.messages`` to identify which actor is
    being asked (by matching ``## You are: {role}`` in the system or
    user prompt) and returns the next scripted response for that actor.

    Each scripted response is a tuple of (tool_call_dict, text). If
    text is provided it populates ``LLMResponse.content``; if
    tool_call_dict is provided it produces exactly one ``ToolCall``.
    """

    def __init__(self, scripts: dict[str, list[tuple[dict[str, Any] | None, str]]]) -> None:
        """Build with a per-role script list.

        Args:
            scripts: Maps actor role (e.g. ``"buyer"``) to a list of
                (tool_call_dict, text) tuples. The router walks the list
                in order per role; each call consumes one entry.
        """
        self._scripts = {role: list(moves) for role, moves in scripts.items()}
        self._cursors: dict[str, int] = dict.fromkeys(scripts, 0)
        self._calls: list[tuple[str, int]] = []  # (role, iteration) tuples
        self._unmatched_count: int = 0  # calls for actors outside the script

    async def route(self, request, engine_name: str = "", use_case: str = "") -> LLMResponse:
        """Return the next scripted response for whichever actor is calling."""
        role = self._detect_role(request)
        if role is None or role not in self._scripts:
            self._unmatched_count += 1
            # Unknown / no-script actor → empty response ends the loop
            return LLMResponse(content="", tool_calls=None, model="scripted", provider="scripted")

        cursor = self._cursors[role]
        script = self._scripts[role]
        if cursor >= len(script):
            # Out of script → terminate the tool loop with empty text
            return LLMResponse(content="", tool_calls=None, model="scripted", provider="scripted")

        tool_args, text = script[cursor]
        self._cursors[role] = cursor + 1
        self._calls.append((role, cursor))

        tool_calls = None
        if tool_args is not None:
            tool_calls = [
                ToolCall(
                    name=tool_args["name"],
                    arguments=tool_args.get("arguments", {}),
                    id=f"call_{role}_{cursor}",
                )
            ]
        return LLMResponse(
            content=text or "",
            tool_calls=tool_calls,
            model="scripted",
            provider="scripted",
        )

    def _detect_role(self, request) -> str | None:
        """Find the actor's role by scanning the request messages."""
        messages = getattr(request, "messages", None) or []
        for msg in messages:
            content = msg.get("content", "") if isinstance(msg, dict) else ""
            if not isinstance(content, str):
                continue
            for role in self._scripts:
                if f"## You are: {role}" in content:
                    return role
        # Fallback: scan system_prompt + user_content
        for content in (
            getattr(request, "system_prompt", ""),
            getattr(request, "user_content", ""),
        ):
            if isinstance(content, str):
                for role in self._scripts:
                    if f"## You are: {role}" in content:
                        return role
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plan() -> WorldPlan:
    """Build an event-driven Q3 Steel-like plan with two players."""
    return WorldPlan(
        name="q3-steel-scripted",
        description="Scripted Q3 Steel deal for the B.12 end-to-end test",
        game=GameDefinition(
            enabled=True,
            mode="negotiation",
            scoring_mode="behavioral",
            negotiation_fields=[
                NegotiationField(name="price", type="number"),
                NegotiationField(name="delivery_weeks", type="integer"),
                NegotiationField(name="payment_days", type="integer"),
                NegotiationField(name="warranty_months", type="integer"),
            ],
            flow=FlowConfig(
                type="event_driven",
                # Short timers so the test fails fast when wiring breaks.
                # A working scripted run terminates in well under a second.
                max_wall_clock_seconds=3,
                max_events=10,
                stalemate_timeout_seconds=3,
                activation_mode="serial",
                first_mover="buyer",
                reactivity_window_events=5,
                state_summary_entity_types=["negotiation_deal"],
            ),
            entities=GameEntitiesConfig(
                deals=[
                    DealDecl(
                        id="deal-q3-steel",
                        title="Q3 Steel Supply",
                        parties=["buyer", "supplier"],
                        status="open",
                        terms={},
                    )
                ],
                player_briefs=[
                    PlayerBriefDecl(
                        actor_role="buyer",
                        deal_id="deal-q3-steel",
                        brief_content="Max $95/ton, need delivery in 4 weeks.",
                        mission="Close the best deal for Atlas.",
                    ),
                    PlayerBriefDecl(
                        actor_role="supplier",
                        deal_id="deal-q3-steel",
                        brief_content="Cost floor $75/ton, target $110+.",
                        mission="Maximize revenue for Vulcan.",
                    ),
                ],
            ),
            win_conditions=[WinCondition(type="deal_closed")],
        ),
    )


def _make_profile() -> InternalAgentProfile:
    """Build a two-agent internal profile (buyer + supplier)."""
    return InternalAgentProfile(
        mission="Negotiate the Q3 Steel contract.",
        deliverable=None,
        agents=[
            ActorDefinition(
                id=ActorId("buyer-001"),
                type=ActorType.AGENT,
                role="buyer",
                permissions={"read": ["slack", "game"], "write": ["slack", "game"]},
            ),
            ActorDefinition(
                id=ActorId("supplier-001"),
                type=ActorType.AGENT,
                role="supplier",
                permissions={"read": ["slack", "game"], "write": ["slack", "game"]},
            ),
        ],
        lead_id=ActorId("buyer-001"),
    )


async def _seed_game_entities_directly(app) -> None:
    """Materialize the game entities directly into state engine.

    Normally the world compiler's ``_materialize_game_entities`` hook
    handles this, but the B.12 test bypasses the compiler pipeline
    (no LLM seed expansion) and seeds the two required entity types
    by hand: the ``negotiation_deal`` and two ``game_player_brief``
    records. The orchestrator's behavioral scorer + state_summary
    helpers read from ``negotiation_deal``.
    """
    state = app.registry.get("state")
    await state.populate_entities(
        {
            "negotiation_deal": [
                {
                    "id": "deal-q3-steel",
                    "title": "Q3 Steel Supply",
                    "parties": ["buyer", "supplier"],
                    "status": "open",
                    "terms": {},
                    "terms_template": {},
                    "consent_rule": "unanimous",
                    "consent_by": [],
                }
            ],
            "game_player_brief": [
                {
                    "id": "gpb-buyer-deal-q3-steel",
                    "actor_role": "buyer",
                    "deal_id": "deal-q3-steel",
                    "owner_role": "buyer",
                    "brief_content": "Max $95/ton",
                    "mission": "Close the best deal",
                },
                {
                    "id": "gpb-supplier-deal-q3-steel",
                    "actor_role": "supplier",
                    "deal_id": "deal-q3-steel",
                    "owner_role": "supplier",
                    "brief_content": "Cost floor $75/ton",
                    "mission": "Maximize revenue",
                },
            ],
        }
    )


async def _configure_agency_for_test(app) -> None:
    """Configure the real AgencyEngine with two game-player actors.

    Wires:

    - Two :class:`ActorState` instances (buyer + supplier)
    - A minimal :class:`WorldContextBundle`
    - ``available_actions`` built from the game pack's tool list so the
      tool loop can dispatch ``negotiate_*`` calls
    """
    from volnix.simulation.world_context import WorldContextBundle

    agency = app.registry.get("agency")
    responder = app.registry.get("responder")
    pack_registry = getattr(responder, "_pack_registry", None)
    assert pack_registry is not None, "responder pack registry must be wired"

    # Build available_actions from the game pack (the 4 negotiate_* tools).
    # Include slack chat.postMessage too so agents can optionally reply.
    available_actions: list[dict[str, Any]] = []
    for tool_info in pack_registry.list_tools():
        if tool_info.get("pack_name") not in {"game", "slack"}:
            continue
        params = tool_info.get("parameters", {})
        available_actions.append(
            {
                "name": tool_info.get("name", ""),
                "description": tool_info.get("description", ""),
                "service": tool_info.get("pack_name", ""),
                "required_params": params.get("required", []),
                "http_method": tool_info.get("http_method", "POST"),
                "parameters": params,
            }
        )

    actor_states = [
        ActorState(
            actor_id=ActorId("buyer-001"),
            role="buyer",
            actor_type="internal",
            autonomous=False,
            persona={"description": "Buyer agent for the Q3 Steel test"},
            current_goal="Close the Q3 Steel deal.",
            goal_context="Negotiate terms through the game tools.",
            team_channel="#negotiations",
        ),
        ActorState(
            actor_id=ActorId("supplier-001"),
            role="supplier",
            actor_type="internal",
            autonomous=False,
            persona={"description": "Supplier agent for the Q3 Steel test"},
            current_goal="Close the Q3 Steel deal.",
            goal_context="Negotiate terms through the game tools.",
            team_channel="#negotiations",
        ),
    ]
    world_context = WorldContextBundle(
        world_description="Q3 Steel Supply — scripted end-to-end test",
        mission="Negotiate a Q3 Steel contract.",
        available_services=available_actions,
    )
    await agency.configure(actor_states, world_context, available_actions)


def _wire_scripted_router(app, router: ScriptedLLMRouter) -> None:
    """Replace the agency engine's LLM router with the scripted version."""
    agency = app.registry.get("agency")
    mock_router = AsyncMock()
    mock_router.route = AsyncMock(side_effect=router.route)
    agency._llm_router = mock_router


def _wire_pipeline_executor(app) -> None:
    """Wire app.handle_action as the agency's tool executor."""
    agency = app.registry.get("agency")

    async def pipeline_executor(envelope):
        try:
            result = await app.handle_action(
                actor_id=str(envelope.actor_id),
                service_id=str(envelope.target_service),
                action=envelope.action_type,
                input_data=envelope.payload,
                tick=0,
            )
        except Exception:
            return None
        if isinstance(result, dict):
            return result.pop("_event", None)
        return None

    agency.set_tool_executor(pipeline_executor)


# ---------------------------------------------------------------------------
# The end-to-end test
# ---------------------------------------------------------------------------


class TestScriptedGameEndToEnd:
    @pytest.mark.asyncio
    async def test_scripted_deal_closed_terminates_orchestrator(self, app_with_mock_llm):
        """3 scripted moves (propose → counter → accept) → deal_closed termination.

        The full event-driven stack exercises:

        - AgencyEngine runs its multi-turn tool loop for each scripted move
        - The governance pipeline executes each ``negotiate_*`` call
        - GamePack handlers write state deltas (deal status transitions)
        - StateEngine commits + publishes ``world.negotiate_*`` events
        - Bus fanout delivers each committed event to GameOrchestrator
        - Orchestrator scores the event, checks DealClosedHandler, and
          on the accept commit publishes GameTerminatedEvent
        - OrchestratorRunner's ``await_result`` resolves with a
          GameResult carrying ``reason="deal_closed"``
        """
        app = app_with_mock_llm

        # ---- Script the LLM for both roles ----
        # Buyer moves first (propose), supplier counters, buyer accepts.
        # Each tool call also sets a short text reply so the agency loop
        # knows when to terminate the per-activation inner loop — we
        # return the tool call on iteration N and an empty response on
        # iteration N+1, which terminates the loop naturally.
        scripted = ScriptedLLMRouter(
            scripts={
                "buyer": [
                    (
                        {
                            "name": "negotiate_propose",
                            "arguments": {
                                "deal_id": "deal-q3-steel",
                                "price": 85,
                                "delivery_weeks": 3,
                                "payment_days": 45,
                                "warranty_months": 18,
                            },
                        },
                        "",
                    ),
                    (None, "Opening terms on the table."),
                    (
                        {
                            "name": "negotiate_accept",
                            "arguments": {"deal_id": "deal-q3-steel"},
                        },
                        "",
                    ),
                    (None, "Deal accepted."),
                ],
                "supplier": [
                    (
                        {
                            "name": "negotiate_counter",
                            "arguments": {
                                "deal_id": "deal-q3-steel",
                                "price": 95,
                                "delivery_weeks": 5,
                                "payment_days": 30,
                                "warranty_months": 12,
                            },
                        },
                        "",
                    ),
                    (None, "Counteroffer posted."),
                ],
            }
        )

        # ---- Wire everything into the live app ----
        await _configure_agency_for_test(app)
        await _seed_game_entities_directly(app)
        _wire_scripted_router(app, scripted)
        _wire_pipeline_executor(app)

        # Track GameTerminatedEvent via a bus subscription
        terminated_events: list[GameTerminatedEvent] = []
        game_world_events: list[Any] = []

        async def capture_terminated(event):
            if isinstance(event, GameTerminatedEvent):
                terminated_events.append(event)

        async def capture_game_events(event):
            game_world_events.append(event)

        await app._bus.subscribe("game.terminated", capture_terminated)
        for topic in (
            "world.negotiate_propose",
            "world.negotiate_counter",
            "world.negotiate_accept",
            "world.negotiate_reject",
        ):
            await app._bus.subscribe(topic, capture_game_events)

        # ---- Configure + start the game ----
        plan = _make_plan()
        app._current_run_id = "run-b12-scripted"

        profile = _make_profile()
        # Register the profile's actors in the actor registry (so
        # configure_game finds them when it collects player IDs).
        for agent_def in profile.agents:
            if not app._actor_registry.has_actor(agent_def.id):
                app._actor_registry.register(agent_def)

        await app.configure_game(plan, internal_profile=profile)

        # Start the orchestrator AFTER configure_game + tool_executor
        # wiring. configure_game no longer calls _on_start() because
        # the CLI's set_tool_executor runs after configure_game returns
        # (startup ordering fix). In tests, we wire the executor above
        # via _wire_pipeline_executor, so _on_start is safe to call now.
        orchestrator = app.registry.get("game")
        await orchestrator._on_start()

        # ---- Await orchestrator termination via its result future ----
        result = await orchestrator.await_result()

        # ---- Assertions ----
        assert result.reason == "deal_closed", f"Expected deal_closed, got {result.reason}"
        assert result.total_events >= 3, (
            f"Expected >= 3 committed game events (propose/counter/accept), "
            f"got {result.total_events}"
        )
        assert result.scoring_mode == "behavioral"

        # Give bus fanout a moment to deliver the GameTerminatedEvent
        import asyncio

        for _ in range(10):
            if terminated_events:
                break
            await asyncio.sleep(0.02)
        assert len(terminated_events) == 1, (
            f"Expected 1 GameTerminatedEvent, got {len(terminated_events)}"
        )
        assert terminated_events[0].reason == "deal_closed"

        # Both actors were activated via the scripted router. At minimum
        # we expect buyer activated twice (propose + accept) and supplier
        # once (counter).
        call_roles = [role for role, _ in scripted._calls]
        assert call_roles.count("buyer") >= 2, (
            f"Buyer should have been activated at least twice; got {call_roles}"
        )
        assert call_roles.count("supplier") >= 1, (
            f"Supplier should have been activated at least once; got {call_roles}"
        )

        # The deal entity should now be in state with status=accepted
        state = app.registry.get("state")
        deals = await state.query_entities("negotiation_deal", {"id": "deal-q3-steel"})
        assert len(deals) == 1
        assert str(deals[0].get("status", "")).lower() == "accepted"

        # NF1: verify the dynamic tool schema landed on the agency
        # correctly. ``configure_game`` should have called
        # ``build_negotiation_tools`` + ``register_game_tools`` with the
        # plan's 4 typed negotiation fields, and the agency's
        # ``_tool_definitions`` should now carry ``negotiate_propose``
        # with typed ``price`` / ``delivery_weeks`` / ``payment_days`` /
        # ``warranty_months`` parameters plus meta_params
        # (``reasoning`` required).
        agency = app.registry.get("agency")
        propose_tool = next(
            (t for t in agency._tool_definitions if t.name == "negotiate_propose"),
            None,
        )
        assert propose_tool is not None, "negotiate_propose not registered on agency"
        props = propose_tool.parameters["properties"]
        assert props["price"]["type"] == "number"
        assert props["delivery_weeks"]["type"] == "integer"
        assert props["payment_days"]["type"] == "integer"
        assert props["warranty_months"]["type"] == "integer"
        # Meta_params layered on
        assert "reasoning" in props
        assert "intended_for" in props
        required = set(propose_tool.parameters["required"])
        assert {
            "deal_id",
            "price",
            "delivery_weeks",
            "payment_days",
            "warranty_months",
            "reasoning",
        }.issubset(required)

        # Accept/reject are terminal — no term field parameters
        accept_tool = next(
            (t for t in agency._tool_definitions if t.name == "negotiate_accept"),
            None,
        )
        assert accept_tool is not None
        accept_props = accept_tool.parameters["properties"]
        assert "price" not in accept_props
        assert "delivery_weeks" not in accept_props
        # But accept DOES carry deal_id + message + meta_params
        assert "deal_id" in accept_props
        assert "message" in accept_props
        assert "reasoning" in accept_props

    @pytest.mark.asyncio
    async def test_stalemate_timeout_terminates_when_no_moves_committed(self, app_with_mock_llm):
        """If both agents return empty responses, the stalemate timer fires.

        This covers the Path B timeout termination path through the full
        stack: scripted router returns no tool calls → agency tool loop
        exits with empty results → no game events committed → stalemate
        deadline elapses → orchestrator publishes GameTimeoutEvent(stalemate)
        → _handle_timeout runs settle + publishes GameTerminatedEvent.
        """
        app = app_with_mock_llm

        # Scripted router that returns ONLY empty responses → no tool calls
        scripted = ScriptedLLMRouter(
            scripts={
                "buyer": [(None, "")],
                "supplier": [(None, "")],
            }
        )

        await _configure_agency_for_test(app)
        await _seed_game_entities_directly(app)
        _wire_scripted_router(app, scripted)
        _wire_pipeline_executor(app)

        plan = _make_plan()
        app._current_run_id = "run-b12-stalemate"
        profile = _make_profile()
        for agent_def in profile.agents:
            if not app._actor_registry.has_actor(agent_def.id):
                app._actor_registry.register(agent_def)

        await app.configure_game(plan, internal_profile=profile)

        # Start orchestrator after tool_executor is wired (same pattern
        # as the deal_closed test above — see startup ordering fix).
        orchestrator = app.registry.get("game")
        await orchestrator._on_start()

        result = await orchestrator.await_result()

        # Stalemate (or wall_clock if stalemate = wall_clock, but we
        # set stalemate=3s which is equal to wall_clock=3s; whichever
        # fires first wins; both are timeout Path B results).
        assert result.reason in {"stalemate", "wall_clock"}, (
            f"Expected stalemate or wall_clock timeout, got {result.reason}"
        )
        assert result.winner is None
        assert result.total_events == 0  # no moves committed
