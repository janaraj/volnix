"""Smoke tests for VolnixApp.create_runner() — the composition-root factory.

Verifies that create_runner dispatches correctly for game vs. simulation
blueprints and returns the proper runner type + metadata, without importing
concrete runner classes in the test itself (mirrors the CLI contract).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from volnix.app import VolnixApp
from volnix.config.schema import VolnixConfig
from volnix.core.protocols import RunnerProtocol


def _make_app() -> VolnixApp:
    """Build a minimal VolnixApp with mocked internals for factory testing."""
    app = VolnixApp(config=VolnixConfig())
    registry = MagicMock()
    app._registry = registry
    app._ledger = MagicMock()
    return app


def _game_plan(*, mode: str = "negotiation", scoring: str = "behavioral") -> SimpleNamespace:
    """Fake compiled plan with game.enabled = True."""
    return SimpleNamespace(
        game=SimpleNamespace(
            enabled=True,
            mode=mode,
            scoring_mode=scoring,
            flow=SimpleNamespace(max_events=50),
        ),
        actor_specs=[],
    )


def _sim_plan() -> SimpleNamespace:
    """Fake compiled plan with no game section."""
    return SimpleNamespace(
        game=None,
        actor_specs=[
            {"id": "agent1", "type": "agent", "role": "buyer"},
        ],
    )


async def test_game_plan_returns_orchestrator_runner() -> None:
    """Game blueprint → OrchestratorRunner + game metadata."""
    app = _make_app()

    mock_orchestrator = MagicMock()
    mock_orchestrator._on_start = AsyncMock()
    mock_agency = MagicMock()
    app._registry.get.side_effect = lambda name: {
        "game": mock_orchestrator,
        "agency": mock_agency,
    }[name]

    result = await app.create_runner(
        compiled_plan=_game_plan(),
        event_queue=MagicMock(),
        pipeline_executor=AsyncMock(),
    )

    assert result is not None
    runner, metadata = result
    assert metadata["runner_kind"] == "game"
    assert metadata["game_mode"] == "negotiation"
    assert metadata["scoring_mode"] == "behavioral"
    assert metadata["max_events"] == 50
    # Runner satisfies protocol structurally
    assert isinstance(runner, RunnerProtocol)
    mock_orchestrator._on_start.assert_awaited_once()


async def test_sim_plan_returns_simulation_runner() -> None:
    """Non-game blueprint → SimulationRunner + simulation metadata."""
    app = _make_app()

    mock_agency = MagicMock()
    mock_animator = MagicMock()
    app._registry.get.side_effect = lambda name: {
        "agency": mock_agency,
        "animator": mock_animator,
    }[name]

    result = await app.create_runner(
        compiled_plan=_sim_plan(),
        event_queue=MagicMock(),
        pipeline_executor=AsyncMock(),
    )

    assert result is not None
    runner, metadata = result
    assert metadata["runner_kind"] == "simulation"
    assert isinstance(runner, RunnerProtocol)


async def test_game_plan_no_engine_registered_returns_none() -> None:
    """Game blueprint with no game engine registered → returns None."""
    app = _make_app()
    app._registry.get.side_effect = KeyError("game")

    result = await app.create_runner(
        compiled_plan=_game_plan(),
        event_queue=MagicMock(),
        pipeline_executor=AsyncMock(),
    )

    assert result is None


async def test_plan_with_game_disabled_falls_through_to_simulation() -> None:
    """compiled_plan.game.enabled = False → simulation path, not game."""
    app = _make_app()

    mock_agency = MagicMock()
    mock_animator = MagicMock()
    app._registry.get.side_effect = lambda name: {
        "agency": mock_agency,
        "animator": mock_animator,
    }[name]

    plan = SimpleNamespace(
        game=SimpleNamespace(enabled=False, mode="negotiation"),
        actor_specs=[{"id": "a1", "type": "agent", "role": "tester"}],
    )

    result = await app.create_runner(
        compiled_plan=plan,
        event_queue=MagicMock(),
        pipeline_executor=AsyncMock(),
    )

    assert result is not None
    _, metadata = result
    assert metadata["runner_kind"] == "simulation"
