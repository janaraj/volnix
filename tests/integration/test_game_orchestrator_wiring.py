"""Integration tests for Cycle B.9 wiring: composition → app → CLI.

Verifies:

- ``create_default_registry`` registers ``game_orchestrator``
- ``wire_engines`` starts the orchestrator cleanly (dependencies resolved)
- ``app._inject_cross_engine_deps`` wires agency and ledger into the
  orchestrator and creates + subscribes the GameActivePolicy gate
- ``app.configure_game`` dispatches event-driven plans to
  ``_configure_event_driven_game``
- The GameActivePolicy gate flips to active when the orchestrator
  publishes ``GameActiveStateChangedEvent`` via the bus

These tests start a real :class:`VolnixApp` (with mock LLM) so the full
wiring path is exercised, not stubs.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from volnix.engines.game.definition import (
    DealDecl,
    FlowConfig,
    GameDefinition,
    GameEntitiesConfig,
    PlayerBriefDecl,
    WinCondition,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event_driven_plan():
    """Build a WorldPlan with an event-driven game definition."""
    from volnix.engines.world_compiler.plan import WorldPlan

    return WorldPlan(
        name="test-event-driven-game",
        description="Event-driven game for wiring tests",
        game=GameDefinition(
            enabled=True,
            mode="negotiation",
            scoring_mode="behavioral",
            flow=FlowConfig(
                type="event_driven",
                max_events=10,
                activation_mode="serial",
                first_mover="buyer",
                state_summary_entity_types=["negotiation_deal"],
            ),
            entities=GameEntitiesConfig(
                deals=[
                    DealDecl(
                        id="deal-test",
                        title="Test Deal",
                        parties=["buyer", "supplier"],
                    )
                ],
                player_briefs=[
                    PlayerBriefDecl(
                        actor_role="buyer",
                        deal_id="deal-test",
                        brief_content="buy low",
                    ),
                    PlayerBriefDecl(
                        actor_role="supplier",
                        deal_id="deal-test",
                        brief_content="sell high",
                    ),
                ],
            ),
            win_conditions=[WinCondition(type="deal_closed")],
        ),
    )


# ---------------------------------------------------------------------------
# Composition root wiring
# ---------------------------------------------------------------------------


class TestCompositionRoot:
    def test_game_orchestrator_registered(self):
        from volnix.registry.composition import create_default_registry

        reg = create_default_registry()
        # GameOrchestrator is registered under ``"game"`` after B.10
        # (the legacy GameEngine was deleted).
        assert "game" in reg.list_engines()
        from volnix.engines.game.orchestrator import GameOrchestrator

        assert isinstance(reg.get("game"), GameOrchestrator)

    def test_game_orchestrator_depends_on_state_and_budget(self):
        from volnix.registry.composition import create_default_registry

        reg = create_default_registry()
        order = reg.resolve_initialization_order()
        orch_idx = order.index("game")
        assert order.index("state") < orch_idx
        assert order.index("budget") < orch_idx


# ---------------------------------------------------------------------------
# VolnixApp wiring via the mock-LLM fixture
# ---------------------------------------------------------------------------


class TestAppWiring:
    """Full app.start() exercises wire_engines + _inject_cross_engine_deps."""

    @pytest.mark.asyncio
    async def test_orchestrator_starts_cleanly(self, app_with_mock_llm):
        """Orchestrator initializes and starts without a definition (noop path)."""
        from volnix.engines.game.orchestrator import GameOrchestrator

        orchestrator = app_with_mock_llm.registry.get("game")
        assert isinstance(orchestrator, GameOrchestrator)
        # _on_start noops when no definition — the engine is still "started"
        assert orchestrator._started is True
        # State dependency resolved during startup path
        assert orchestrator._state is not None

    @pytest.mark.asyncio
    async def test_orchestrator_ledger_is_wired(self, app_with_mock_llm):
        orchestrator = app_with_mock_llm.registry.get("game")
        assert orchestrator._config.get("_ledger") is not None

    @pytest.mark.asyncio
    async def test_orchestrator_agency_dependency_is_wired(self, app_with_mock_llm):
        orchestrator = app_with_mock_llm.registry.get("game")
        assert orchestrator._dependencies.get("agency") is not None

    @pytest.mark.asyncio
    async def test_game_active_gate_registered_on_policy_engine(self, app_with_mock_llm):
        policy = app_with_mock_llm.registry.get("policy")
        gates = getattr(policy, "_builtin_gates", [])
        from volnix.engines.policy.builtin.game_active import GameActivePolicy

        assert any(isinstance(g, GameActivePolicy) for g in gates)

    @pytest.mark.asyncio
    async def test_game_active_gate_stored_on_app(self, app_with_mock_llm):
        from volnix.engines.policy.builtin.game_active import GameActivePolicy

        gate = getattr(app_with_mock_llm, "_game_active_gate", None)
        assert isinstance(gate, GameActivePolicy)
        # Gate starts inactive (no game running yet)
        assert gate.is_active is False


# ---------------------------------------------------------------------------
# configure_game dispatch
# ---------------------------------------------------------------------------


class TestConfigureGameDispatch:
    @pytest.mark.asyncio
    async def test_event_driven_plan_configures_orchestrator(self, app_with_mock_llm):
        """An event-driven plan routes to ``_configure_event_driven_game``."""
        plan = _make_event_driven_plan()

        # Register two players in the actor registry so configure_game
        # can collect them
        from volnix.actors.definition import ActorDefinition
        from volnix.core.types import ActorId, ActorType

        app_with_mock_llm._actor_registry.register(
            ActorDefinition(
                id=ActorId("buyer-001"),
                type=ActorType.AGENT,
                role="buyer",
                permissions={"read": ["game"], "write": ["game"]},
            )
        )
        app_with_mock_llm._actor_registry.register(
            ActorDefinition(
                id=ActorId("supplier-001"),
                type=ActorType.AGENT,
                role="supplier",
                permissions={"read": ["game"], "write": ["game"]},
            )
        )
        app_with_mock_llm._current_run_id = "run-wire-001"

        orchestrator = app_with_mock_llm.registry.get("game")
        # Stub out the fire-and-forget kickstart so the test doesn't
        # actually call the mock LLM. ``_launch_activation`` is a sync
        # method that wraps asyncio.create_task — use MagicMock not AsyncMock.
        orchestrator._launch_activation = MagicMock(return_value=None)  # type: ignore[method-assign]

        await app_with_mock_llm.configure_game(plan)

        # Orchestrator now has the definition and player scores
        assert orchestrator._definition is plan.game
        assert len(orchestrator._player_scores) == 2


# ---------------------------------------------------------------------------
# Bus-driven gate state transitions
# ---------------------------------------------------------------------------


class TestGameActiveStateViaBus:
    @pytest.mark.asyncio
    async def test_gate_flips_active_on_bus_event(self, app_with_mock_llm):
        """Publishing ``game.active_state_changed`` flips the gate's flag.

        Exercises the actual bus subscription wired by
        ``_inject_cross_engine_deps``.
        """
        from datetime import UTC, datetime

        from volnix.core.types import EventId, Timestamp
        from volnix.engines.game.events import GameActiveStateChangedEvent

        gate = app_with_mock_llm._game_active_gate
        assert gate.is_active is False

        now = datetime.now(UTC)
        evt = GameActiveStateChangedEvent(
            event_id=EventId("evt-wire-test"),
            event_type="game.active_state_changed",
            timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
            active=True,
            run_id="run-wire-001",
        )
        await app_with_mock_llm._bus.publish(evt)
        # Give the bus dispatch loop a chance to run
        import asyncio

        for _ in range(10):
            await asyncio.sleep(0.01)
            if gate.is_active:
                break
        assert gate.is_active is True
