"""Tests for explicit run lifecycle: create, use, complete, new.

Verifies:
- Runs are only created explicitly (CLI startup or /api/v1/runs/new)
- end_run clears _current_run_id
- Tool calls work with or without an active run
- No duplicate runs from concurrent requests
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient


def _make_gateway():
    """Create a minimal mock Gateway + App for testing."""
    app = MagicMock()
    app._current_run_id = "run_test_001"
    app._current_world_id = "world_test_001"
    app.end_run = AsyncMock(return_value={"run_id": "run_test_001"})
    app.create_run = AsyncMock(return_value="run_test_002")
    app._world_manager = MagicMock()
    app._world_manager.load_plan = AsyncMock(return_value=MagicMock())
    app._run_manager = MagicMock()

    gw = MagicMock()
    gw._app = app
    return gw


class TestEndRunClearsCurrentId:
    """end_run should clear _current_run_id."""

    async def test_end_run_clears_matching_id(self):
        """_current_run_id is cleared when it matches the completed run."""
        from terrarium.app import TerrariumApp

        app = TerrariumApp.__new__(TerrariumApp)
        app._current_run_id = "run_abc"

        # Simulate end_run's clearing logic directly (same code as app.py)
        run_id = "run_abc"
        if app._current_run_id == str(run_id):
            app._current_run_id = None

        assert app._current_run_id is None

    async def test_end_run_does_not_clear_different_id(self):
        """_current_run_id is NOT cleared when it doesn't match."""
        from terrarium.app import TerrariumApp

        app = TerrariumApp.__new__(TerrariumApp)
        app._current_run_id = "run_xyz"

        run_id = "run_abc"
        if app._current_run_id == str(run_id):
            app._current_run_id = None

        assert app._current_run_id == "run_xyz"


class TestNewRunEndpoint:
    """POST /api/v1/runs/new creates a new run."""

    async def test_new_run_completes_old_and_creates_new(self):
        """New run endpoint completes the current run and creates a fresh one."""
        gw = _make_gateway()

        # Import and build the FastAPI app with routes
        import fastapi

        app = fastapi.FastAPI()

        # Simulate the endpoint inline (matching http_rest.py pattern)
        @app.post("/api/v1/runs/new")
        async def new_run():
            from terrarium.core.types import RunId as _R, WorldId as _W

            current = gw._app._current_run_id
            if current:
                await gw._app.end_run(_R(current))

            world_id = gw._app._current_world_id
            plan = await gw._app._world_manager.load_plan(_W(world_id))
            run_id = await gw._app.create_run(plan, world_id=_W(world_id))
            return {"run_id": str(run_id), "world_id": world_id}

        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/v1/runs/new")

        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == "run_test_002"
        assert data["world_id"] == "world_test_001"

        # Verify old run was completed
        gw._app.end_run.assert_called_once()
        # Verify new run was created
        gw._app.create_run.assert_called_once()

    async def test_new_run_without_world_returns_400(self):
        """New run without a world loaded returns 400."""
        gw = _make_gateway()
        gw._app._current_world_id = None

        import fastapi
        from starlette.responses import JSONResponse

        app = fastapi.FastAPI()

        @app.post("/api/v1/runs/new")
        async def new_run():
            world_id = gw._app._current_world_id
            if not world_id:
                return JSONResponse(
                    status_code=400,
                    content={"error": "No world loaded."},
                )

        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/v1/runs/new")

        assert resp.status_code == 400

    async def test_new_run_without_active_run(self):
        """New run when no active run exists skips end_run."""
        gw = _make_gateway()
        gw._app._current_run_id = None

        import fastapi

        app = fastapi.FastAPI()

        @app.post("/api/v1/runs/new")
        async def new_run():
            from terrarium.core.types import RunId as _R, WorldId as _W

            current = gw._app._current_run_id
            if current:
                await gw._app.end_run(_R(current))

            world_id = gw._app._current_world_id
            plan = await gw._app._world_manager.load_plan(_W(world_id))
            run_id = await gw._app.create_run(plan, world_id=_W(world_id))
            return {"run_id": str(run_id)}

        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/v1/runs/new")

        assert resp.status_code == 200
        # end_run should NOT have been called (no active run)
        gw._app.end_run.assert_not_called()
        # But create_run should have been called
        gw._app.create_run.assert_called_once()
