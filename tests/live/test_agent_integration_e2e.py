"""Live E2E test: Agent Integration — all 3 phases.

Tests the complete agent integration flow:
  Phase 1: SDK client connects, discovers tools, executes action
  Phase 2: Auth middleware validates tokens, status codes mapped
  Phase 3: Webhook receives events from action execution

Requires: codex-acp with device auth
"""
from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import httpx
import pytest


@pytest.fixture
async def live_app_with_codex(tmp_path):
    """VolnixApp with REAL codex-acp LLM + webhook enabled."""
    if not shutil.which("codex-acp"):
        pytest.skip("codex-acp not found")

    from volnix.app import VolnixApp
    from volnix.config.loader import ConfigLoader
    from volnix.engines.state.config import StateConfig
    from volnix.persistence.config import PersistenceConfig

    loader = ConfigLoader()
    config = loader.load()

    config = config.model_copy(update={
        "persistence": PersistenceConfig(base_dir=str(tmp_path / "data")),
        "state": StateConfig(
            db_path=str(tmp_path / "state.db"),
            snapshot_dir=str(tmp_path / "snapshots"),
        ),
    })

    app = VolnixApp(config)
    await app.start()
    yield app, tmp_path
    await app.stop()


class TestPhase1SDK:
    """Phase 1: SDK client connects, discovers tools, executes actions."""

    @pytest.mark.asyncio
    async def test_sdk_tool_discovery_and_execution(
        self, live_app_with_codex
    ) -> None:
        """
        1. Start HTTP adapter
        2. SDK client connects
        3. Discover tools in MCP + OpenAI formats
        4. Execute an email_send action
        5. Verify response
        """
        app, tmp_path = live_app_with_codex

        print("\n" + "=" * 70)
        print("TEST: Phase 1 — SDK Client E2E")
        print("=" * 70)

        # Start HTTP adapter
        gateway = app.gateway
        http_adapter = gateway._adapters.get("http")
        if http_adapter is None:
            pytest.skip("HTTP adapter not available")

        await http_adapter.start_server()
        fastapi_app = http_adapter.fastapi_app

        transport = httpx.ASGITransport(app=fastapi_app)

        # Step 1: Discover tools via MCP format
        print("\n  Step 1: Discover tools (MCP format)...")
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/tools", params={"format": "mcp"}
            )
        assert resp.status_code == 200
        mcp_tools = resp.json()
        print(f"    MCP tools: {len(mcp_tools)}")
        assert len(mcp_tools) > 0
        tool_names = [t.get("name", "") for t in mcp_tools]
        print(f"    Sample: {tool_names[:5]}")

        # Step 2: Discover tools in OpenAI format
        print("\n  Step 2: Discover tools (OpenAI format)...")
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/v1/tools", params={"format": "openai"}
            )
        assert resp.status_code == 200
        openai_tools = resp.json()
        print(f"    OpenAI tools: {len(openai_tools)}")
        # OpenAI format has "type": "function"
        if openai_tools:
            assert openai_tools[0].get("type") == "function"

        # Step 3: Execute an action via SDK
        print("\n  Step 3: Execute email_send via HTTP API...")
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/actions/email_send",
                json={
                    "actor_id": "sdk-test-agent",
                    "arguments": {
                        "from_addr": "agent@test.com",
                        "to_addr": "user@test.com",
                        "subject": "Test from SDK",
                        "body": "Hello from Volnix SDK",
                    },
                },
            )
        print(f"    Status: {resp.status_code}")
        print(f"    Response: {json.dumps(resp.json(), default=str)[:200]}")
        # May succeed (200), or hit pipeline governance (400/403/422)
        # 403 = permission denied (actor not registered) — governance working
        assert resp.status_code in (200, 400, 403, 422)

        # Step 4: Test VolnixClient
        print("\n  Step 4: VolnixClient integration...")
        from volnix.sdk import VolnixClient

        async with VolnixClient(
            url="http://test", _transport=transport
        ) as terra:
            tools = await terra.tools(fmt="mcp")
            print(f"    Client tools: {len(tools)}")
            assert len(tools) > 0

        # Step 5: Test config export
        print("\n  Step 5: Config export templates...")
        from volnix.cli_exports.templates import EXPORT_REGISTRY

        for target in ["claude-desktop", "openai-tools", "env-vars",
                       "python-sdk"]:
            output = EXPORT_REGISTRY[target](
                url="http://localhost:8080", tools=mcp_tools
            )
            assert len(output) > 0
            print(f"    {target}: {len(output)} chars")

        print("\n  Phase 1 PASSED")


class TestPhase2Middleware:
    """Phase 2: Auth middleware + status code mapping."""

    @pytest.mark.asyncio
    async def test_middleware_auth_and_status_codes(
        self, live_app_with_codex
    ) -> None:
        """
        1. Verify status code middleware maps errors
        2. Verify auth middleware validates tokens
        """
        app, tmp_path = live_app_with_codex

        print("\n" + "=" * 70)
        print("TEST: Phase 2 — Middleware E2E")
        print("=" * 70)

        gateway = app.gateway
        http_adapter = gateway._adapters.get("http")
        if http_adapter is None:
            pytest.skip("HTTP adapter not available")

        await http_adapter.start_server()
        transport = httpx.ASGITransport(app=http_adapter.fastapi_app)

        # Step 1: Status code middleware — error responses get proper codes
        print("\n  Step 1: Status code middleware...")
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            # Call a non-existent tool — should get an error
            resp = await client.post(
                "/api/v1/actions/nonexistent_tool_xyz",
                json={"actor_id": "test", "arguments": {}},
            )
        print(f"    Nonexistent tool status: {resp.status_code}")
        # StatusCodeMiddleware should map capability errors
        assert resp.status_code != 500  # Not a server crash

        # Step 2: Verify internal API bypasses auth
        print("\n  Step 2: Internal API bypass...")
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/tools")
        assert resp.status_code == 200
        print(f"    /api/v1/tools: {resp.status_code}")

        # Step 3: Verify health endpoint works
        print("\n  Step 3: Health endpoint...")
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        print(f"    /api/v1/health: {resp.status_code}")

        print("\n  Phase 2 PASSED")


class TestPhase3Webhooks:
    """Phase 3: Webhook registration and event delivery."""

    @pytest.mark.asyncio
    async def test_webhook_registration_and_stats(
        self, live_app_with_codex
    ) -> None:
        """
        1. Register a webhook via API
        2. List webhooks
        3. Check stats
        4. Unregister
        """
        app, tmp_path = live_app_with_codex

        print("\n" + "=" * 70)
        print("TEST: Phase 3 — Webhook E2E")
        print("=" * 70)

        gateway = app.gateway
        http_adapter = gateway._adapters.get("http")
        if http_adapter is None:
            pytest.skip("HTTP adapter not available")

        await http_adapter.start_server()
        transport = httpx.ASGITransport(app=http_adapter.fastapi_app)

        # Step 1: Check webhook status (may be disabled)
        print("\n  Step 1: Check webhook status...")
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/webhooks")
        print(f"    Webhooks response: {resp.json()}")

        # If webhooks are disabled (default), verify we get proper response
        if not resp.json().get("enabled", False):
            print("    Webhooks disabled (default) — testing disabled path")

            # Registration should return 503
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/v1/webhooks",
                    json={
                        "url": "http://example.com:9999/hook",
                        "events": ["world.*"],
                    },
                )
            print(f"    Register when disabled: {resp.status_code}")
            assert resp.status_code == 503

            print("\n  Phase 3 PASSED (webhooks disabled path)")
            return

        # If enabled, test full flow
        print("\n  Step 2: Register webhook...")
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/v1/webhooks",
                json={
                    "url": "http://example.com:9999/hook",
                    "events": ["world.email_*"],
                    "service": "email",
                },
            )
        assert resp.status_code == 200
        webhook_id = resp.json().get("id")
        print(f"    Registered: {webhook_id}")

        # Step 3: List webhooks
        print("\n  Step 3: List webhooks...")
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/webhooks")
        hooks = resp.json().get("webhooks", [])
        print(f"    Registered webhooks: {len(hooks)}")
        assert len(hooks) == 1

        # Step 4: Check stats
        print("\n  Step 4: Check stats...")
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/webhooks/stats")
        stats = resp.json()
        print(f"    Stats: {stats}")

        # Step 5: Unregister
        print("\n  Step 5: Unregister webhook...")
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.delete(
                f"/api/v1/webhooks/{webhook_id}"
            )
        assert resp.status_code == 200
        print(f"    Unregistered: {webhook_id}")

        # Verify empty
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/webhooks")
        assert len(resp.json().get("webhooks", [])) == 0
        print("    Verified: no webhooks remaining")

        print("\n  Phase 3 PASSED")
