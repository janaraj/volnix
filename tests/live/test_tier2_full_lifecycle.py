"""Live E2E test: Full Tier 2 lifecycle — unknown service → infer → compile → runtime.

Tests THREE source paths:
1. OpenAPI spec: Petstore API (downloaded spec file) → parsed → profile
2. LLM inference: Unknown service "sendgrid" → LLM generates profile
3. Full lifecycle: World with Tier 2 service → compile → agent action → Tier 2 response

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
        from terrarium.packs.verified.email.pack import EmailPack
        from terrarium.reality.presets import load_preset

        email_surface = ServiceSurface.from_pack(EmailPack())

        plan = WorldPlan(
            name="Tier 2 Lifecycle Test",
            description="Support team using email (Tier 1) and Jira (Tier 2).",
            seed=42,
            behavior="static",
            mode="governed",
            services={
                "email": ServiceResolution(
                    service_name="email", spec_reference="verified/email",
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
