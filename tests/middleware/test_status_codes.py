"""Tests for StatusCodeMiddleware — error body → HTTP status mapping."""
from __future__ import annotations

import httpx

from volnix.middleware.config import MiddlewareConfig
from volnix.middleware.status_codes import StatusCodeMiddleware


def _make_app(config: MiddlewareConfig, response_body: dict):
    """Create a minimal app that returns a fixed response body."""
    import fastapi

    app = fastapi.FastAPI()
    app.add_middleware(StatusCodeMiddleware, config=config)

    @app.get("/test")
    async def endpoint():
        return response_body

    return app


async def test_not_found_maps_to_404():
    """Response with 'not found' error gets 404 status."""
    config = MiddlewareConfig(status_codes_enabled=True)
    app = _make_app(config, {"error": "Entity not found"})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/test")
    assert resp.status_code == 404


async def test_permission_denied_maps_to_403():
    """Response with 'permission denied' error gets 403 status."""
    config = MiddlewareConfig(status_codes_enabled=True)
    app = _make_app(config, {"error": "Permission denied for this resource"})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/test")
    assert resp.status_code == 403


async def test_validation_step_maps_to_422():
    """Pipeline validation short-circuit gets 422 status."""
    config = MiddlewareConfig(status_codes_enabled=True)
    app = _make_app(config, {
        "error": "Pipeline short-circuited",
        "step": "validation",
    })
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/test")
    assert resp.status_code == 422


async def test_budget_step_maps_to_429():
    """Pipeline budget short-circuit gets 429 status."""
    config = MiddlewareConfig(status_codes_enabled=True)
    app = _make_app(config, {
        "error": "Budget exhausted",
        "step": "budget",
    })
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/test")
    assert resp.status_code == 429


async def test_success_passes_through():
    """Non-error responses keep 200 status."""
    config = MiddlewareConfig(status_codes_enabled=True)
    app = _make_app(config, {"id": "ch_123", "status": "succeeded"})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/test")
    assert resp.status_code == 200
    assert resp.json()["id"] == "ch_123"


async def test_disabled_passes_all():
    """When disabled, error responses keep 200."""
    config = MiddlewareConfig(status_codes_enabled=False)
    app = _make_app(config, {"error": "Entity not found"})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/test")
    assert resp.status_code == 200


# -- Error/edge case tests ---


async def test_error_null_passes_through():
    """H4: Response with error: null keeps 200."""
    config = MiddlewareConfig(status_codes_enabled=True)
    app = _make_app(config, {"data": [], "error": None})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/test")
    assert resp.status_code == 200


async def test_nested_error_object():
    """Nested Stripe-style error object classified correctly."""
    config = MiddlewareConfig(status_codes_enabled=True)
    app = _make_app(config, {
        "error": {
            "message": "No such charge: ch_123",
            "type": "invalid_request_error",
        }
    })
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/test")
    # "No such" matches "no such" pattern → 404
    assert resp.status_code == 404


async def test_default_400_for_unmatched_error():
    """Unrecognized error message defaults to 400."""
    config = MiddlewareConfig(status_codes_enabled=True)
    app = _make_app(config, {
        "error": "Something completely unexpected happened"
    })
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/test")
    assert resp.status_code == 400


async def test_non_200_passes_through():
    """Non-200 responses pass through unchanged."""
    import fastapi

    config = MiddlewareConfig(status_codes_enabled=True)
    app = fastapi.FastAPI()

    from volnix.middleware.status_codes import StatusCodeMiddleware

    app.add_middleware(StatusCodeMiddleware, config=config)

    @app.get("/test")
    async def endpoint():
        from starlette.responses import JSONResponse

        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error"},
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/test")
    # 500 passes through unchanged (middleware only reclassifies 200)
    assert resp.status_code == 500
