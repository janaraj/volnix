"""Tests for AuthMiddleware — token shape validation."""
from __future__ import annotations

import httpx

from volnix.middleware.auth import AuthMiddleware
from volnix.middleware.config import MiddlewareConfig


def _make_app(config: MiddlewareConfig):
    """Create a minimal FastAPI app with AuthMiddleware."""
    import fastapi

    app = fastapi.FastAPI()
    app.add_middleware(AuthMiddleware, config=config)

    @app.get("/v1/charges")
    async def stripe_endpoint():
        return {"data": []}

    @app.get("/api/v1/tools")
    async def internal_endpoint():
        return {"tools": []}

    @app.get("/gmail/v1/messages")
    async def gmail_endpoint():
        return {"messages": []}

    return app


async def test_valid_token_passes(auth_config):
    """Request with valid token shape passes through."""
    app = _make_app(auth_config)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        # /v1/charges route exists; auth resolves "stripe" via prefix config
        resp = await client.get(
            "/v1/charges",
            headers={"Authorization": "Bearer sk_test_123"},
        )
    assert resp.status_code == 200


async def test_invalid_token_rejected(auth_config):
    """Request with wrong token shape returns 401."""
    app = _make_app(auth_config)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get(
            "/stripe/v1/charges",
            headers={"Authorization": "Bearer bad_token"},
        )
    assert resp.status_code == 401
    assert "authentication_error" in resp.json()["error"]["type"]


async def test_missing_header_rejected(auth_config):
    """Request without Authorization header returns 401."""
    app = _make_app(auth_config)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/stripe/v1/charges")
    assert resp.status_code == 401


async def test_disabled_skips_all():
    """When auth is disabled, all requests pass through."""
    config = MiddlewareConfig(auth_enabled=False)
    app = _make_app(config)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/v1/charges")
    assert resp.status_code == 200


async def test_internal_api_skipped(auth_config):
    """Internal /api/v1/ endpoints bypass auth."""
    app = _make_app(auth_config)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/tools")
    assert resp.status_code == 200


async def test_unknown_service_passes(auth_config):
    """Requests to services without auth rules pass through."""
    app = _make_app(auth_config)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/gmail/v1/messages")
    # gmail not in auth_config's rules — passes through
    assert resp.status_code == 200


# -- Error/edge case tests ---


async def test_options_preflight_passes(auth_config):
    """H6: CORS preflight OPTIONS requests bypass auth."""
    app = _make_app(auth_config)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.options("/stripe/v1/charges")
    # OPTIONS should not get 401
    assert resp.status_code != 401


async def test_empty_auth_header_rejected(auth_config):
    """H3: Empty Authorization header gets specific error."""
    app = _make_app(auth_config)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get(
            "/stripe/v1/charges",
            headers={"Authorization": ""},
        )
    assert resp.status_code == 401
    assert "Empty" in resp.json()["error"]["message"]


async def test_very_long_header_rejected(auth_config):
    """C3: Excessively long auth header rejected."""
    app = _make_app(auth_config)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get(
            "/stripe/v1/charges",
            headers={"Authorization": "Bearer sk_" + "x" * 1000},
        )
    assert resp.status_code == 401
    assert "too long" in resp.json()["error"]["message"]


async def test_mcp_path_skips_auth(auth_config):
    """C2: /mcp paths skip auth."""
    app = _make_app(auth_config)


    @app.get("/mcp/test")
    async def mcp_test():
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        resp = await client.get("/mcp/test")
    assert resp.status_code == 200
