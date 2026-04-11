"""Tests for ``volnix.engines.game.orchestrator_runner.OrchestratorRunner``.

The runner is the CLI-compatibility shim that bridges the
``SimulationRunner.run()`` interface with
:meth:`GameOrchestrator.await_result`. Tested in isolation here;
end-to-end CLI flow is covered by tests/cli/test_run_*.py.
"""

from __future__ import annotations

import asyncio

import pytest

from volnix.core.types import ActorId
from volnix.engines.game.definition import GameResult
from volnix.engines.game.orchestrator_runner import OrchestratorRunner


class _FakeOrchestrator:
    """Minimal orchestrator stub exposing ``await_result``.

    The future is lazily created inside ``await_result`` so tests that
    construct the stub outside a running event loop (e.g. sync tests
    for ``_is_game_runner``) don't hit ``DeprecationWarning``.
    """

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
    async def test_run_returns_orchestrator_result(self):
        expected = GameResult(
            reason="deal_closed",
            winner=ActorId("buyer-001"),
            total_events=7,
        )
        orch = _FakeOrchestrator(result=expected)
        runner = OrchestratorRunner(orchestrator=orch, agency=None)
        result = await runner.run()
        assert result is expected
        assert result.reason == "deal_closed"
        assert result.winner == ActorId("buyer-001")

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


# ---------------------------------------------------------------------------
# CLI compatibility surface
# ---------------------------------------------------------------------------


class TestCliCompat:
    @pytest.mark.asyncio
    async def test_set_mission_is_noop(self):
        orch = _FakeOrchestrator(result=GameResult(reason="ok"))
        runner = OrchestratorRunner(orchestrator=orch, agency=None)
        runner.set_mission("negotiate Q3 steel")
        assert runner._mission == "negotiate Q3 steel"
        # Doesn't affect the result
        result = await runner.run()
        assert result.reason == "ok"

    def test_class_name_is_detected_as_game_runner(self):
        """CLI ``_is_game_runner`` matches on class name — must be stable."""
        from volnix.cli import _is_game_runner

        orch = _FakeOrchestrator(result=GameResult(reason="x"))
        runner = OrchestratorRunner(orchestrator=orch, agency=None)
        assert _is_game_runner(runner) is True


# ---------------------------------------------------------------------------
# Format compatibility with CLI's result formatter
# ---------------------------------------------------------------------------


class TestFormatRunResult:
    """CLI's ``_format_run_result`` must handle OrchestratorRunner output."""

    def test_winner_reason_formatted(self):
        from volnix.cli import _format_run_result

        result = GameResult(reason="deal_closed", winner=ActorId("buyer-001"))
        formatted = _format_run_result(result, is_game=True)
        assert "deal_closed" in formatted
        assert "buyer-001" in formatted

    def test_reason_only_formatted(self):
        from volnix.cli import _format_run_result

        result = GameResult(reason="stalemate")
        formatted = _format_run_result(result, is_game=True)
        assert formatted == "stalemate"
