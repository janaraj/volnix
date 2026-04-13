"""Tests for ``volnix.engines.game.orchestrator_runner.OrchestratorRunner``.

The runner is the CLI-compatibility shim that bridges the
``RunnerProtocol.run()`` interface with
:meth:`GameOrchestrator.await_result`. Tested in isolation here;
end-to-end CLI flow is covered by tests/cli/test_run_*.py.
"""

from __future__ import annotations

import asyncio

import pytest

from volnix.core.types import ActorId, RunResult
from volnix.engines.game.definition import GameResult
from volnix.engines.game.orchestrator_runner import OrchestratorRunner


class _FakeOrchestrator:
    """Minimal orchestrator stub exposing ``await_result``."""

    def __init__(self, result: GameResult | None = None) -> None:
        self._result = result
        self._future: asyncio.Future[GameResult] | None = None

    def _ensure_future(self) -> asyncio.Future[GameResult]:
        if self._future is None:
            self._future = asyncio.get_running_loop().create_future()
            if self._result is not None:
                self._future.set_result(self._result)
        return self._future

    def set_result(self, result: GameResult) -> None:
        fut = self._ensure_future()
        if not fut.done():
            fut.set_result(result)

    async def await_result(self) -> GameResult:
        return await self._ensure_future()


# ---------------------------------------------------------------------------
# Basic delegation
# ---------------------------------------------------------------------------


class TestOrchestratorRunnerRun:
    @pytest.mark.asyncio
    async def test_run_returns_run_result(self):
        game_result = GameResult(
            reason="deal_closed",
            winner=ActorId("buyer-001"),
            total_events=7,
            wall_clock_seconds=12.5,
        )
        orch = _FakeOrchestrator(result=game_result)
        runner = OrchestratorRunner(orchestrator=orch, agency=None)
        result = await runner.run()
        assert isinstance(result, RunResult)
        assert result.runner_kind == "game"
        assert result.reason == "deal_closed"
        assert result.winner == "buyer-001"
        assert result.total_events == 7
        assert result.wall_clock_seconds == 12.5

    @pytest.mark.asyncio
    async def test_run_blocks_until_result_resolved(self):
        orch = _FakeOrchestrator()  # pending future
        runner = OrchestratorRunner(orchestrator=orch, agency=None)
        task = asyncio.create_task(runner.run())
        await asyncio.sleep(0)
        assert not task.done()  # runner blocks on the future
        orch.set_result(GameResult(reason="stalemate"))
        result = await task
        assert result.reason == "stalemate"
        assert result.runner_kind == "game"


# ---------------------------------------------------------------------------
# RunnerProtocol compliance
# ---------------------------------------------------------------------------


class TestRunnerProtocol:
    @pytest.mark.asyncio
    async def test_set_mission_is_noop(self):
        orch = _FakeOrchestrator(result=GameResult(reason="ok"))
        runner = OrchestratorRunner(orchestrator=orch, agency=None)
        runner.set_mission("negotiate Q3 steel")
        assert runner._mission == "negotiate Q3 steel"
        result = await runner.run()
        assert result.reason == "ok"

    def test_satisfies_runner_protocol(self):
        """OrchestratorRunner must satisfy RunnerProtocol."""
        from volnix.core.protocols import RunnerProtocol

        assert issubclass(OrchestratorRunner, RunnerProtocol)


# ---------------------------------------------------------------------------
# Format compatibility with CLI's result formatter
# ---------------------------------------------------------------------------


class TestFormatRunResult:
    """CLI's ``_format_run_result`` must handle RunResult from game runner."""

    def test_winner_reason_formatted(self):
        from volnix.cli import _format_run_result

        result = RunResult(
            reason="deal_closed",
            runner_kind="game",
            winner="buyer-001",
        )
        formatted = _format_run_result(result)
        assert "deal_closed" in formatted
        assert "buyer-001" in formatted

    def test_reason_only_formatted(self):
        from volnix.cli import _format_run_result

        result = RunResult(reason="stalemate", runner_kind="game")
        formatted = _format_run_result(result)
        assert formatted == "stalemate"
