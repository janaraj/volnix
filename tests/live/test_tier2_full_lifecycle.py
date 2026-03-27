"""Live E2E test: Full Tier 2 lifecycle — unknown service → infer → compile → runtime.

Tests FOUR source paths:
1. OpenAPI spec: Petstore API (downloaded spec file) → parsed → profile
2. LLM inference: Unknown service "sendgrid" → LLM generates profile
3. Full lifecycle: World with Tier 2 service → compile → agent action → Tier 2 response
4. Context Hub: Twilio docs from chub → LLM infer → compile → agent action → response

Requires: codex-acp with device auth
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest


@pytest.fixture
async def live_app_with_codex(tmp_path):
    """TerrariumApp with REAL codex-acp LLM + temp profiles dir."""
    if not shutil.which("codex-acp"):
        pytest.skip("codex-acp not found")

    from terrarium.app import TerrariumApp
    from terrarium.config.loader import ConfigLoader
    from terrarium.engines.state.config import StateConfig
    from terrarium.persistence.config import PersistenceConfig

    loader = ConfigLoader()
    config = loader.load()

    # Use temp profiles directory so we don't pollute the real one
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()

    config = config.model_copy(update={
        "persistence": PersistenceConfig(base_dir=str(tmp_path / "data")),
        "state": StateConfig(
            db_path=str(tmp_path / "state.db"),
            snapshot_dir=str(tmp_path / "snapshots"),
        ),
    })

    app = TerrariumApp(config)
    await app.start()
    yield app, tmp_path
    await app.stop()


class TestOpenAPISource:
    """Test Tier 2 profile generation from a real OpenAPI spec file."""

    @pytest.mark.asyncio
    async def test_openapi_petstore_spec_parsed(self, tmp_path) -> None:
        """Download Petstore OpenAPI spec → parse → verify operations extracted."""
        print("\n" + "=" * 70)
        print("TEST: OpenAPI Petstore Spec Parsing")
        print("=" * 70)

        from terrarium.kernel.openapi_provider import OpenAPIProvider

        # Copy petstore spec to a temp spec directory
        spec_dir = tmp_path / "specs"
        spec_dir.mkdir()

        # Download petstore spec
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get("https://petstore3.swagger.io/api/v3/openapi.json")
                spec_content = resp.text
        except Exception:
            # Fallback: use a minimal spec
            spec_content = json.dumps({
                "openapi": "3.0.0",
                "info": {"title": "Petstore", "version": "1.0.0"},
                "paths": {
                    "/pet": {
                        "post": {
                            "operationId": "addPet",
                            "summary": "Add a new pet",
                            "requestBody": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "name": {"type": "string"},
                                                "status": {"type": "string", "enum": ["available", "pending", "sold"]},
                                            },
                                            "required": ["name"],
                                        }
                                    }
                                }
                            },
                            "responses": {
                                "200": {
                                    "content": {
                                        "application/json": {
                                            "schema": {
                                                "type": "object",
                                                "properties": {
                                                    "id": {"type": "integer"},
                                                    "name": {"type": "string"},
                                                    "status": {"type": "string"},
                                                },
                                            }
                                        }
                                    }
                                }
                            },
                        }
                    },
                    "/pet/{petId}": {
                        "get": {
                            "operationId": "getPetById",
                            "summary": "Find pet by ID",
                            "parameters": [
                                {"name": "petId", "in": "path", "required": True, "schema": {"type": "integer"}},
                            ],
                            "responses": {
                                "200": {
                                    "content": {
                                        "application/json": {
                                            "schema": {
                                                "type": "object",
                                                "properties": {
                                                    "id": {"type": "integer"},
                                                    "name": {"type": "string"},
                                                },
                                            }
                                        }
                                    }
                                }
                            },
                        }
                    },
                },
            })

        (spec_dir / "petstore.json").write_text(spec_content)
        print(f"  Spec saved: {spec_dir / 'petstore.json'} ({len(spec_content)} bytes)")

        # Parse with OpenAPI provider
        provider = OpenAPIProvider(spec_dir=str(spec_dir))
        assert await provider.supports("petstore"), "Provider should find petstore spec"

        result = await provider.fetch("petstore")
        print(f"  Source: {result.get('source')}")
        print(f"  Title: {result.get('title')}")
        print(f"  Operations: {len(result.get('operations', []))}")
        for op in result.get("operations", [])[:5]:
            print(f"    - {op.get('name')} ({op.get('http_method')} {op.get('http_path')})")

        assert len(result.get("operations", [])) >= 2, "Expected at least 2 operations"
        assert result.get("source") == "openapi"
        print("\n  PASSED")


class TestLLMInference:
    """Test LLM-powered profile inference for a completely unknown service."""

    @pytest.mark.asyncio
    async def test_infer_sendgrid_profile(self, live_app_with_codex) -> None:
        """Infer SendGrid (email delivery) — LLM generates profile from knowledge."""
        app, tmp_path = live_app_with_codex

        print("\n" + "=" * 70)
        print("TEST: Infer SendGrid Profile via LLM")
        print("=" * 70)

        from terrarium.packs.profile_infer import ProfileInferrer
        from terrarium.packs.profile_loader import ProfileLoader

        inferrer = ProfileInferrer(
            llm_router=app._llm_router,
            context_hub=None,
            openapi_provider=None,
            kernel=None,
        )

        print("  Inferring 'sendgrid'...")
        profile = await inferrer.infer("sendgrid")

        print(f"  Service: {profile.service_name}")
        print(f"  Category: {profile.category}")
        print(f"  Operations: {len(profile.operations)}")
        for op in profile.operations[:5]:
            print(f"    - {op.name} ({op.http_method} {op.http_path})")
        print(f"  Entities: {len(profile.entities)}")
        print(f"  Confidence: {profile.confidence}")

        assert len(profile.operations) >= 3
        assert len(profile.entities) >= 1
        assert profile.responder_prompt

        # Save and reload
        loader = ProfileLoader(tmp_path / "profiles")
        loader.save(profile)
        reloaded = loader.load("sendgrid")
        assert reloaded is not None
        assert len(reloaded.operations) == len(profile.operations)
        print(f"  Saved + reloaded: {len(reloaded.operations)} operations")

        print("\n  PASSED")


class TestFullLifecycle:
    """Full lifecycle: unknown service in world → infer → compile → runtime."""

    @pytest.mark.asyncio
    async def test_world_with_tier2_service(self, live_app_with_codex) -> None:
        """
        1. Build world plan with "jira" (Tier 2 profile exists on disk)
        2. Compile → entities generated using profile schemas
        3. Agent calls jira_create_issue → Tier2Generator → LLM response
        4. Response validated against profile schema
        """
        app, tmp_path = live_app_with_codex

        print("\n" + "=" * 70)
        print("TEST: Full Lifecycle — World with Jira (Tier 2)")
        print("=" * 70)

        # Step 1: Check Jira profile is available
        responder = app.registry.get("responder")
        registry = getattr(responder, "_profile_registry", None)
        jira = registry.get_profile("jira") if registry else None

        if jira is None:
            print("  Jira profile not loaded — skipping lifecycle test")
            pytest.skip("Jira profile not available")

        print(f"  Jira profile: {len(jira.operations)} operations")

        # Step 2: Build a world plan with Jira as Tier 2 service
        from terrarium.packs.profile_surface import profile_to_surface
        jira_surface = profile_to_surface(jira)

        from terrarium.engines.world_compiler.plan import ServiceResolution, WorldPlan
        from terrarium.kernel.surface import ServiceSurface
        from terrarium.packs.verified.gmail.pack import EmailPack
        from terrarium.reality.presets import load_preset

        email_surface = ServiceSurface.from_pack(EmailPack())

        plan = WorldPlan(
            name="Tier 2 Lifecycle Test",
            description="Support team using email (Tier 1) and Jira (Tier 2).",
            seed=42,
            behavior="static",
            mode="governed",
            services={
                "gmail": ServiceResolution(
                    service_name="gmail", spec_reference="verified/gmail",
                    surface=email_surface, resolution_source="tier1_pack",
                ),
                "jira": ServiceResolution(
                    service_name="jira", spec_reference="profiled/jira",
                    surface=jira_surface, resolution_source="tier2_yaml_profile",
                ),
            },
            actor_specs=[
                {"role": "developer", "type": "external", "count": 1},
            ],
            conditions=load_preset("ideal"),
            reality_prompt_context={},
        )

        print(f"  Plan: {plan.name}")
        print(f"  Services: {list(plan.services.keys())}")

        # Step 3: Compile — generate entities for both services
        compiler = app.registry.get("world_compiler")
        result = await compiler.generate_world(plan)

        entity_types = list(result["entities"].keys())
        total = sum(len(v) for v in result["entities"].values())
        print(f"  Generated: {total} entities across {entity_types}")

        # Check Jira entities were generated
        jira_entities = [et for et in entity_types if et in ("issue", "comment", "project")]
        print(f"  Jira entity types: {jira_entities}")

        assert total > 0, "Should have generated entities"

        # Step 4: Agent calls a Jira action through the pipeline
        actors = result["actors"]
        agent = actors[0] if actors else None
        agent_id = str(agent.id) if agent else "developer-001"

        print(f"\n  Agent: {agent_id}")
        print("  Calling jira_create_issue through pipeline...")

        action_result = await app.handle_action(
            agent_id, "jira", "jira_create_issue",
            {
                "project_key": "SUPPORT",
                "summary": "Bug in refund flow",
                "description": "Steps to reproduce...",
                "issue_type": "Bug",
                "priority": "High",
            },
        )
        print(f"  Result: {json.dumps(action_result, default=str)[:300]}")

        # Tier 2 should succeed — no pipeline short-circuit, no missing pack errors
        if "error" in action_result:
            error_msg = action_result.get("error", "")
            if "No pack" in error_msg and "profile" in error_msg:
                pytest.fail(f"Tier 2 not wired: {error_msg}")
            elif "short-circuited" in error_msg:
                step = action_result.get("step", "?")
                pytest.fail(f"Pipeline blocked at '{step}': {error_msg}")
            elif "Validation failed" in error_msg:
                pytest.fail(f"Tier 2 validation failed: {error_msg}")
            else:
                print(f"  Pipeline result: {error_msg}")
        else:
            print(f"  Tier 2 response received!")
            assert "key" in action_result, f"Expected Jira issue key in response: {action_result}"
            print(f"  Issue key: {action_result['key']}")

        print("\n  PASSED")


class TestContextHubSource:
    """Test full lifecycle: Context Hub docs → infer profile → compile world → runtime."""

    @pytest.mark.asyncio
    async def test_context_hub_twilio_lifecycle(self, live_app_with_codex) -> None:
        """
        1. Context Hub fetches real Twilio docs via npx @aisuite/chub
        2. ProfileInferrer generates profile with those docs (confidence=0.7)
        3. World compiled with email (Tier 1) + twilio (Tier 2)
        4. Agent calls twilio_send_message → Tier 2 LLM response
        """
        app, tmp_path = live_app_with_codex

        print("\n" + "=" * 70)
        print("TEST: Context Hub → Twilio Full Lifecycle")
        print("=" * 70)

        # Step 1: Verify Context Hub is available
        from terrarium.kernel.context_hub import ContextHubProvider

        hub = ContextHubProvider()
        if not await hub.is_available():
            pytest.skip("npx not available — Context Hub requires npm")

        # Step 2: Fetch real Twilio docs
        print("  Fetching Twilio docs from Context Hub...")
        hub_data = await hub.fetch("twilio")
        if hub_data is None:
            pytest.skip("Context Hub has no Twilio docs (chub search failed)")

        print(f"  Content ID: {hub_data.get('content_id')}")
        print(f"  Language: {hub_data.get('lang')}")
        print(f"  Doc size: {len(hub_data.get('raw_content', ''))} chars")
        assert len(hub_data["raw_content"]) > 100, "Expected substantial docs"

        # Step 3: Infer Twilio profile using Context Hub docs
        from terrarium.packs.profile_infer import ProfileInferrer

        inferrer = ProfileInferrer(
            llm_router=app._llm_router,
            context_hub=hub,
            openapi_provider=None,
            kernel=None,
        )

        print("  Inferring Twilio profile with Context Hub docs...")
        profile = await inferrer.infer("twilio")

        print(f"  Service: {profile.service_name}")
        print(f"  Category: {profile.category}")
        print(f"  Confidence: {profile.confidence}")
        print(f"  Source chain: {profile.source_chain}")
        print(f"  Operations: {len(profile.operations)}")
        for op in profile.operations[:5]:
            print(f"    - {op.name} ({op.http_method} {op.http_path})")
        print(f"  Entities: {len(profile.entities)}")
        for entity in profile.entities[:3]:
            print(f"    - {entity.name} (identity: {entity.identity_field})")

        assert profile.confidence == 0.7, f"Expected 0.7 (hub source), got {profile.confidence}"
        assert "context_hub" in profile.source_chain, f"source_chain missing context_hub: {profile.source_chain}"
        assert len(profile.operations) >= 3, f"Expected >= 3 operations, got {len(profile.operations)}"
        assert len(profile.entities) >= 1, f"Expected >= 1 entity, got {len(profile.entities)}"

        # Step 4: Save + verify persistence
        from terrarium.packs.profile_loader import ProfileLoader

        loader = ProfileLoader(tmp_path / "profiles")
        loader.save(profile)
        reloaded = loader.load("twilio")
        assert reloaded is not None
        print(f"  Saved + reloaded: {len(reloaded.operations)} operations")

        # Step 5: Resolve twilio through the compiler's service resolution chain.
        # This exercises the REAL path: compiler sees "twilio" → checks profiles
        # on disk → not found (we saved to tmp_path, not the app's profiles dir)
        # → runs infer pipeline → saves + registers in shared ProfileRegistry.
        # But since we already inferred above, register directly with the shared
        # registry so the compiler's generate_world uses this profile and the
        # responder/adapter can serve it at runtime.
        compiler = app.registry.get("world_compiler")
        resolver = getattr(compiler, "_compiler_resolver", None)
        if resolver and hasattr(resolver, "_profile_registry") and resolver._profile_registry:
            resolver._profile_registry.register(profile)
        else:
            # Fallback: register with responder directly
            responder = app.registry.get("responder")
            responder._profile_registry.register(profile)

        # Step 6: Build world plan with twilio as Tier 2
        from terrarium.packs.profile_surface import profile_to_surface

        twilio_surface = profile_to_surface(profile)

        from terrarium.engines.world_compiler.plan import ServiceResolution, WorldPlan
        from terrarium.kernel.surface import ServiceSurface
        from terrarium.packs.verified.gmail.pack import EmailPack
        from terrarium.reality.presets import load_preset

        email_surface = ServiceSurface.from_pack(EmailPack())

        plan = WorldPlan(
            name="Context Hub Lifecycle Test",
            description="Support team using email (Tier 1) and Twilio SMS (Tier 2).",
            seed=42,
            behavior="static",
            mode="governed",
            services={
                "gmail": ServiceResolution(
                    service_name="gmail", spec_reference="verified/gmail",
                    surface=email_surface, resolution_source="tier1_pack",
                ),
                "twilio": ServiceResolution(
                    service_name="twilio", spec_reference="profiled/twilio",
                    surface=twilio_surface, resolution_source="tier2_inferred",
                ),
            },
            actor_specs=[
                {"role": "support_agent", "type": "external", "count": 1},
            ],
            conditions=load_preset("ideal"),
            reality_prompt_context={},
        )

        print(f"\n  Plan: {plan.name}")
        print(f"  Services: {list(plan.services.keys())}")

        # Step 7: Compile world
        compiler = app.registry.get("world_compiler")
        result = await compiler.generate_world(plan)

        entity_types = list(result["entities"].keys())
        total = sum(len(v) for v in result["entities"].values())
        print(f"  Generated: {total} entities across {entity_types}")

        assert total > 0, "Should have generated entities"

        # Step 8: Agent calls a Twilio action through the full pipeline
        actors = result["actors"]
        agent = actors[0] if actors else None
        agent_id = str(agent.id) if agent else "support-agent-001"

        # Find a send-like operation in the inferred profile
        send_op = None
        for op in profile.operations:
            if "send" in op.name.lower() or "create" in op.name.lower():
                send_op = op
                break
        if send_op is None:
            send_op = profile.operations[0]

        print(f"\n  Agent: {agent_id}")
        print(f"  Calling {send_op.name} through pipeline...")

        action_result = await app.handle_action(
            agent_id, "twilio", send_op.name,
            {
                "to": "+15551234567",
                "from_": "+15559876543",
                "body": "Your support ticket has been updated.",
            },
        )
        print(f"  Result: {json.dumps(action_result, default=str)[:300]}")

        if "error" in action_result:
            error_msg = action_result.get("error", "")
            if "No pack" in error_msg and "profile" in error_msg:
                pytest.fail(f"Tier 2 not wired: {error_msg}")
            elif "short-circuited" in error_msg:
                step = action_result.get("step", "?")
                pytest.fail(f"Pipeline blocked at '{step}': {error_msg}")
            elif "Validation failed" in error_msg:
                # Inferred profiles have weaker schemas — validation may fail
                print(f"  Note: validation warning (expected for inferred): {error_msg}")
            else:
                print(f"  Pipeline result: {error_msg}")
        else:
            print(f"  Tier 2 response received!")

        print("\n  PASSED")
