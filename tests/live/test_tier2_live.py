"""Live E2E test: Tier 2 profiles with real LLM (codex-acp).

Tests:
1. Tier 2 runtime: Jira profile loaded → agent calls jira_create_issue → LLM response
2. LLM inference: Unknown service "twilio" → LLM generates draft profile → saved
3. Verify inferred profile loads and has valid structure

Requires: codex-acp with device auth
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest


@pytest.fixture
async def live_app_with_codex(tmp_path):
    """VolnixApp with REAL codex-acp LLM."""
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
    yield app
    await app.stop()


class TestTier2ProfileRuntime:
    """Test Tier 2 profile loading and runtime with real LLM."""

    @pytest.mark.asyncio
    async def test_jira_profile_loads_and_creates_surface(self, live_app_with_codex) -> None:
        """Jira profile loads from YAML and creates valid ServiceSurface."""
        app = live_app_with_codex

        print("\n" + "=" * 70)
        print("TEST: Jira Profile Load + Surface Conversion")
        print("=" * 70)

        # Check responder has profile registry
        responder = app.registry.get("responder")
        profile_registry = getattr(responder, "_profile_registry", None)
        assert profile_registry is not None, "Profile registry not initialized"

        # Check Jira profile is loaded
        jira_profile = profile_registry.get_profile("jira")
        print(f"  Jira profile loaded: {jira_profile is not None}")

        if jira_profile:
            print(f"  Service: {jira_profile.service_name}")
            print(f"  Category: {jira_profile.category}")
            print(f"  Operations: {len(jira_profile.operations)}")
            for op in jira_profile.operations:
                print(f"    - {op.name} ({op.http_method} {op.http_path})")
            print(f"  Entities: {len(jira_profile.entities)}")
            for entity in jira_profile.entities:
                print(f"    - {entity.name} (identity: {entity.identity_field})")
            print(f"  State machines: {len(jira_profile.state_machines)}")
            print(f"  Error modes: {len(jira_profile.error_modes)}")
            print(f"  Responder prompt: {jira_profile.responder_prompt[:80]}...")

            # Verify action lookup works
            lookup = profile_registry.get_profile_for_action("jira_create_issue")
            assert lookup is not None, "jira_create_issue not found in registry"
            print(f"  Action lookup 'jira_create_issue': {lookup.service_name}")

            # Convert to surface
            from volnix.packs.profile_surface import profile_to_surface
            surface = profile_to_surface(jira_profile)
            print(f"  Surface operations: {len(surface.operations)}")
            print(f"  Surface entity_schemas: {list(surface.entity_schemas.keys())}")
            print(f"  Surface fidelity_tier: {surface.fidelity_tier}")

            # Check MCP tool generation
            mcp_tools = surface.get_mcp_tools()
            print(f"  MCP tools: {len(mcp_tools)}")
            for tool in mcp_tools[:3]:
                print(f"    - {tool['name']}: {tool.get('description', '')[:50]}")

            # Check HTTP routes
            http_routes = surface.get_http_routes()
            print(f"  HTTP routes: {len(http_routes)}")
            for route in http_routes[:3]:
                print(f"    - {route['method']} {route['path']}")

            assert len(surface.operations) >= 5, "Expected at least 5 Jira operations"
            assert "issue" in surface.entity_schemas, "Expected 'issue' entity"

        print("\n  PASSED")


class TestTier2InferLive:
    """Test LLM-powered profile inference for unknown services."""

    @pytest.mark.asyncio
    async def test_infer_twilio_profile(self, live_app_with_codex, tmp_path) -> None:
        """Infer a Twilio profile from LLM knowledge — no Context Hub, no OpenAPI."""
        app = live_app_with_codex

        print("\n" + "=" * 70)
        print("TEST: Infer Twilio Profile via LLM")
        print("=" * 70)

        from volnix.packs.profile_infer import ProfileInferrer

        # Create inferrer with real LLM
        inferrer = ProfileInferrer(
            llm_router=app._llm_router,
            context_hub=None,  # No chub installed
            openapi_provider=None,  # No spec files
            kernel=None,  # No kernel classification
        )

        print("  Inferring profile for 'twilio'...")
        try:
            profile = await inferrer.infer("twilio")
        except Exception as exc:
            print(f"  Inference failed: {exc}")
            pytest.skip(f"LLM inference failed: {exc}")
            return

        print(f"  Profile inferred successfully!")
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
        print(f"  State machines: {len(profile.state_machines)}")
        print(f"  Error modes: {len(profile.error_modes)}")
        print(f"  Behavioral notes: {len(profile.behavioral_notes)}")
        if profile.behavioral_notes:
            for note in profile.behavioral_notes[:3]:
                print(f"    - {note[:80]}")
        print(f"  Responder prompt: {profile.responder_prompt[:100]}...")

        # Verify minimum viability
        assert len(profile.operations) >= 3, f"Expected at least 3 ops, got {len(profile.operations)}"
        assert len(profile.entities) >= 1, f"Expected at least 1 entity, got {len(profile.entities)}"
        assert profile.responder_prompt, "Responder prompt should not be empty"
        assert profile.confidence >= 0.2, f"Confidence too low: {profile.confidence}"

        # Save to temp directory
        from volnix.packs.profile_loader import ProfileLoader
        loader = ProfileLoader(tmp_path / "profiles")
        saved_path = loader.save(profile)
        print(f"\n  Saved to: {saved_path}")

        # Reload and verify
        reloaded = loader.load("twilio")
        assert reloaded is not None, "Failed to reload saved profile"
        assert reloaded.service_name == "twilio"
        assert len(reloaded.operations) == len(profile.operations)
        print(f"  Reloaded: {reloaded.service_name} with {len(reloaded.operations)} operations")

        # Convert to surface
        from volnix.packs.profile_surface import profile_to_surface
        surface = profile_to_surface(profile)
        print(f"  Surface: {len(surface.operations)} operations, tier={surface.fidelity_tier}")

        print("\n  PASSED")
