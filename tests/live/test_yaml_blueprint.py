"""Live Test: YAML Blueprint World Creation

Simulates the user flow:
    volnix run acme_support.yaml --settings acme_compiler.yaml

This test:
1. User has pre-written YAML files (world definition + compiler settings)
2. YAML parser extracts services, actors, policies, seeds, reality
3. Service resolution finds packs (EmailPack for email service)
4. Reality dimensions expanded from preset + per-dimension overrides
5. WorldPlan assembled with all resolved data
6. LLM generates entities matching service schemas (email, mailbox, thread)
7. LLM generates rich personalities for all actors
8. LLM expands seed descriptions into concrete entity modifications
9. Entities populated into StateEngine
10. Actors registered in ActorRegistry
11. Snapshot taken of initial world state

Run with:
    source .env && pytest tests/live/test_yaml_blueprint.py -v -s
"""

from __future__ import annotations

import json

import pytest

from volnix.engines.world_compiler.plan_reviewer import PlanReviewer


@pytest.mark.asyncio
class TestYAMLBlueprintWorld:
    """User provides YAML blueprint files → Volnix compiles and generates."""

    async def test_acme_support_blueprint(self, live_app) -> None:
        """volnix run acme_support.yaml --settings acme_compiler.yaml"""
        compiler = live_app.registry.get("world_compiler")

        print("\n" + "=" * 70)
        print("FLOW 2: YAML BLUEPRINT → COMPILE → GENERATE WORLD")
        print("=" * 70)

        # Step 1: Compile from YAML blueprint
        print("\n📄 Loading YAML blueprints:")
        print("   World:    tests/fixtures/worlds/acme_support.yaml")
        print("   Compiler: tests/fixtures/worlds/acme_compiler.yaml")

        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )

        # Step 2: Show compiled plan
        reviewer = PlanReviewer()
        print("\n" + "-" * 40)
        print("COMPILED WORLD PLAN:")
        print("-" * 40)
        print(reviewer.format_plan(plan))

        # Step 3: Generate world with real LLM
        print("\n⏳ Generating world entities via Gemini...")
        result = await compiler.generate_world(plan)

        # Step 4: Show generated entities
        print("\n" + "-" * 40)
        print("GENERATED ENTITIES:")
        print("-" * 40)
        for etype, entities in result["entities"].items():
            print(f"\n  {etype}: {len(entities)} entities")
            for entity in entities[:2]:  # Show first 2 per type
                print(f"    {json.dumps(entity, indent=6, default=str)[:300]}")
            if len(entities) > 2:
                print(f"    ... and {len(entities) - 2} more")

        # Step 5: Show actors with LLM-generated personalities
        print("\n" + "-" * 40)
        print("GENERATED ACTORS:")
        print("-" * 40)
        for actor in result["actors"][:5]:
            p = actor.personality
            friction = actor.friction_profile
            print(f"\n  {actor.id} ({actor.role}, {actor.type})")
            if p:
                print(f"    Style: {p.style}")
                print(f"    Strengths: {p.strengths}")
                print(f"    Weaknesses: {p.weaknesses}")
                print(f"    Description: {p.description[:100]}")
            if friction:
                print(f"    Friction: {friction.category} (intensity={friction.intensity})")

        # Step 6: Show validation status
        print(f"\n  Validation warnings: {len(result['warnings'])}")
        for w in result["warnings"][:5]:
            print(f"    ⚠ {w}")

        # Step 7: Show snapshot
        print(f"\n  Seeds processed: {result['seeds_processed']}")
        print(f"  Snapshot: {result['snapshot_id']}")

        # Assertions
        assert result["entities"], "LLM should generate entities"
        assert result["actors"], "LLM should generate actors"
        assert result["seeds_processed"] >= 3, "acme_support.yaml has 3+ seeds"
        assert result["snapshot_id"], "Snapshot should be taken"

    async def test_minimal_blueprint(self, live_app) -> None:
        """volnix run minimal_world.yaml (simplest possible world)"""
        compiler = live_app.registry.get("world_compiler")

        print("\n" + "=" * 70)
        print("FLOW 2b: MINIMAL BLUEPRINT → SIMPLE WORLD")
        print("=" * 70)

        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/minimal_world.yaml",
        )
        print(f"\n📄 World: {plan.name}")
        print(f"   Services: {plan.get_service_names()}")
        print(f"   Actors: {len(plan.actor_specs)}")

        result = await compiler.generate_world(plan)

        total = sum(len(v) for v in result["entities"].values())
        print(f"\n✅ Generated {total} entities, {len(result['actors'])} actors")

        assert total > 0
        assert result["actors"]
