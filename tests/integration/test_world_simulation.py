"""Integration tests: Full user journey — compile -> generate -> run -> report.

These tests simulate how a real user interacts with Terrarium:
1. Write YAML world definition + compiler settings
2. Compile world (resolve services, expand reality)
3. Generate entities and actors
4. Run agent actions through the pipeline
5. Verify state, events, ledger
6. Generate and inspect reports

Run with `pytest -s` to see actual output from print statements.
"""

from __future__ import annotations

import json
import os

import pytest

from terrarium.actors.definition import ActorDefinition
from terrarium.core.types import ActorId, ActorType
from terrarium.engines.world_compiler.plan_reviewer import PlanReviewer


def _ensure_agent(app, agent_id: str):
    """Register a test agent if not already present in the actor registry."""
    compiler = app.registry.get("world_compiler")
    actor_registry = compiler._config.get("_actor_registry")
    if actor_registry and not actor_registry.has_actor(ActorId(agent_id)):
        actor_registry.register(ActorDefinition(
            id=ActorId(agent_id),
            type=ActorType.AGENT,
            role="test-agent",
            permissions={"write": "all", "read": "all"},
        ))


# ── Compilation flow ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestWorldCompilationFlow:
    """Test the compilation phase (YAML -> WorldPlan).

    Compilation does NOT need LLM — uses the plain ``app`` fixture.
    """

    async def test_compile_acme_world(self, app) -> None:
        """Compile acme_support.yaml + acme_compiler.yaml -> valid WorldPlan."""
        compiler = app.registry.get("world_compiler")
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        assert plan.name == "Acme Support Organization"
        assert plan.source == "yaml"
        assert len(plan.actor_specs) >= 3
        assert plan.conditions.information.staleness == 30  # messy preset
        assert plan.conditions.reliability.failures == 20

    async def test_compile_minimal_world(self, app) -> None:
        """Compile minimal_world.yaml with defaults."""
        compiler = app.registry.get("world_compiler")
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/minimal_world.yaml",
        )
        assert plan.name
        assert plan.behavior == "dynamic"  # default

    async def test_plan_review_output(self, app) -> None:
        """PlanReviewer.format_plan() produces meaningful output."""
        compiler = app.registry.get("world_compiler")
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        reviewer = PlanReviewer()
        text = reviewer.format_plan(plan)
        assert "Acme Support" in text
        assert "staleness=" in text
        assert "Validation" in text

    async def test_plan_yaml_roundtrip(self, app) -> None:
        """WorldPlan -> YAML -> dict preserves key fields."""
        compiler = app.registry.get("world_compiler")
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        reviewer = PlanReviewer()
        yaml_str = reviewer.to_yaml(plan)
        loaded = reviewer.from_yaml(yaml_str)
        assert loaded["name"] == plan.name
        assert loaded["seed"] == plan.seed
        assert loaded["behavior"] == plan.behavior


# ── Generation flow ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestWorldGenerationFlow:
    """Test the generation phase (WorldPlan -> entities + actors).

    Uses ``app_with_mock_llm`` because generation requires LLM.
    """

    async def test_generate_produces_entities(self, app_with_mock_llm) -> None:
        """generate_world() returns populated entity dict."""
        app = app_with_mock_llm
        compiler = app.registry.get("world_compiler")
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        result = await compiler.generate_world(plan)
        assert "entities" in result
        total = sum(len(v) for v in result["entities"].values())
        assert total > 0

    async def test_generate_produces_actors(self, app_with_mock_llm) -> None:
        """generate_world() creates ActorDefinition instances."""
        app = app_with_mock_llm
        compiler = app.registry.get("world_compiler")
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        result = await compiler.generate_world(plan)
        assert "actors" in result
        assert len(result["actors"]) > 0

    async def test_generate_report(self, app_with_mock_llm) -> None:
        """generate_world() includes a comprehensive report."""
        app = app_with_mock_llm
        compiler = app.registry.get("world_compiler")
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        result = await compiler.generate_world(plan)
        report = result["report"]
        assert "TERRARIUM WORLD GENERATION REPORT" in report
        assert "GENERATED ENTITIES" in report
        assert "STATUS:" in report

    async def test_generate_with_seeds(self, app_with_mock_llm) -> None:
        """Seeds are processed and reflected in results."""
        app = app_with_mock_llm
        compiler = app.registry.get("world_compiler")
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        result = await compiler.generate_world(plan)
        # acme_support.yaml has 3+ seeds
        assert result["seeds_processed"] >= 3


# ── Agent actions after generation ────────────────────────────────


@pytest.mark.asyncio
class TestAgentActionsAfterGeneration:
    """After world generation, agents can perform actions through the pipeline.

    Uses ``app_with_mock_llm`` because generation requires LLM.
    """

    async def test_email_send_after_generation(self, app_with_mock_llm) -> None:
        """Agent sends email after world is generated."""
        app = app_with_mock_llm
        compiler = app.registry.get("world_compiler")
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        await compiler.generate_world(plan)

        # Register test agent so governance allows the action
        _ensure_agent(app, "agent-1")

        # Agent performs action through pipeline
        result = await app.handle_action(
            "agent-1",
            "email",
            "email_send",
            {
                "from_addr": "agent@acme.com",
                "to_addr": "customer@test.com",
                "subject": "Support response",
                "body": "We are looking into your issue.",
            },
        )
        assert "email_id" in result

    async def test_state_queryable_after_generation(self, app_with_mock_llm) -> None:
        """Generated entities are queryable in StateEngine."""
        app = app_with_mock_llm
        compiler = app.registry.get("world_compiler")
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        result = await compiler.generate_world(plan)

        # Verify entities are in state
        state = app.registry.get("state")
        for entity_type, entity_list in result["entities"].items():
            entities = await state.query_entities(entity_type)
            assert len(entities) == len(entity_list)


# ── E2E simulation with report ────────────────────────────────────


@pytest.mark.asyncio
class TestEndToEndReport:
    """Full simulation: compile -> generate -> act -> report.

    Uses ``app_with_mock_llm`` because generation requires LLM.
    """

    async def test_full_simulation_report(self, app_with_mock_llm) -> None:
        """Run complete simulation and print report for manual review."""
        app = app_with_mock_llm
        compiler = app.registry.get("world_compiler")

        # 1. Compile
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )

        # 2. Generate
        gen_result = await compiler.generate_world(plan)

        # 3. Act (send some emails)
        action_results = []
        for i in range(3):
            try:
                r = await app.handle_action(
                    f"agent-{i}",
                    "email",
                    "email_send",
                    {
                        "from_addr": f"agent{i}@acme.com",
                        "to_addr": f"customer{i}@test.com",
                        "subject": f"Support ticket #{i + 1}",
                        "body": f"Responding to your inquiry #{i + 1}.",
                    },
                )
                action_results.append(r)
            except Exception as e:
                action_results.append({"error": str(e)})

        # 4. Verify report
        report = gen_result["report"]
        assert "TERRARIUM WORLD GENERATION REPORT" in report
        assert gen_result["entities"]
        assert gen_result["actors"]

        # Print for manual inspection (visible with -s flag)
        print("\n" + "=" * 60)
        print("FULL SIMULATION REPORT")
        print("=" * 60)
        print(report)
        print(f"\nAgent actions executed: {len(action_results)}")
        print(
            f"Successful: {sum(1 for r in action_results if 'error' not in r)}"
        )
        print(f"Failed: {sum(1 for r in action_results if 'error' in r)}")


# ── NL interpretation -> YAML -> full flow ─────────────────────────


@pytest.mark.asyncio
class TestNLToWorldFlow:
    """Tests showing how NL gets interpreted, YAML generated, and full flow works.

    These tests print actual intermediate outputs for manual inspection.
    Run with `pytest -s` to see the full output.
    """

    async def test_nl_interpretation_and_yaml_output(self, app) -> None:
        """Show how NL description becomes a structured world definition.

        This test uses mock LLM to demonstrate the NL -> structured data flow.
        The actual YAML format that would be generated is printed for inspection.

        NOTE: Compilation only (no generate_world) — does NOT need mock LLM.
        """
        import yaml
        from unittest.mock import AsyncMock
        from terrarium.engines.world_compiler.nl_parser import NLParser
        from terrarium.engines.world_compiler.prompt_templates import (
            NL_TO_WORLD_DEF,
            NL_TO_COMPILER_SETTINGS,
        )
        from terrarium.llm.types import LLMResponse

        # 1. Show what the NL templates look like
        print("\n" + "=" * 70)
        print("NL -> WORLD DEFINITION: Template Rendering")
        print("=" * 70)

        description = "A support team with email and 10 customers, some frustrated"

        sys_prompt, user_prompt = NL_TO_WORLD_DEF.render(
            categories="communication, crm, payments",
            verified_packs="email",
            description=description,
        )
        print(f"\n--- System Prompt (first 200 chars) ---")
        print(sys_prompt[:200] + "...")
        print(f"\n--- User Prompt ---")
        print(user_prompt)

        # 2. Simulate what LLM would return
        mock_world_def = {
            "world": {
                "name": "Support Team Simulation",
                "description": "A support team handling email with 10 customers, "
                "some of whom are frustrated from slow resolution times.",
                "services": {"email": "verified/email"},
                "actors": [
                    {
                        "role": "support-agent",
                        "type": "external",
                        "count": 2,
                        "personality": "Diligent and methodical",
                    },
                    {
                        "role": "customer",
                        "type": "internal",
                        "count": 10,
                        "personality": "Mix of patient and frustrated",
                    },
                ],
                "policies": [
                    {
                        "name": "escalation_on_frustration",
                        "description": "Escalate when customer frustration detected",
                        "enforcement": "escalate",
                    }
                ],
                "seeds": [
                    "A VIP customer Margaret Chen has 3 unresolved tickets from last week",
                    "Two customers have duplicate tickets about the same billing issue",
                ],
                "mission": "Resolve all support tickets within SLA",
            }
        }

        mock_compiler = {
            "compiler": {
                "seed": 42,
                "behavior": "dynamic",
                "fidelity": "auto",
                "mode": "governed",
                "reality": {"preset": "messy"},
            }
        }

        print("\n" + "=" * 70)
        print("LLM INTERPRETATION: Generated World Definition YAML")
        print("=" * 70)
        print(yaml.dump(mock_world_def, default_flow_style=False, sort_keys=False))

        print("=" * 70)
        print("LLM INTERPRETATION: Generated Compiler Settings YAML")
        print("=" * 70)
        print(yaml.dump(mock_compiler, default_flow_style=False, sort_keys=False))

        # 3. Parse through the actual YAML parser
        from terrarium.engines.world_compiler.yaml_parser import YAMLParser
        from terrarium.reality.expander import ConditionExpander

        parser = YAMLParser(ConditionExpander())
        partial, specs = await parser.parse_from_dicts(mock_world_def, mock_compiler)

        print("=" * 70)
        print("PARSED WorldPlan:")
        print("=" * 70)
        reviewer = PlanReviewer()
        print(reviewer.format_plan(partial))

        # 4. Verify the parsed plan
        assert partial.name == "Support Team Simulation"
        assert partial.behavior == "dynamic"
        assert partial.conditions.information.staleness == 30  # messy
        assert len(partial.actor_specs) == 2
        assert len(partial.seeds) == 2

    async def test_yaml_compilation_with_visible_output(self, app_with_mock_llm) -> None:
        """Full YAML -> compile -> generate -> report with visible output.

        Shows the complete flow a user would see when running:
        `terrarium create acme_support.yaml --settings acme_compiler.yaml`

        Uses ``app_with_mock_llm`` because generation requires LLM.
        """
        app = app_with_mock_llm
        compiler = app.registry.get("world_compiler")

        # 1. Compile from YAML
        print("\n" + "=" * 70)
        print("STEP 1: COMPILE FROM YAML")
        print("=" * 70)

        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )

        reviewer = PlanReviewer()
        print(reviewer.format_plan(plan))

        # 2. Generate world
        print("\n" + "=" * 70)
        print("STEP 2: GENERATE WORLD")
        print("=" * 70)

        result = await compiler.generate_world(plan)

        # 3. Show entity details
        for etype, entities in result["entities"].items():
            print(f"\n  {etype}: {len(entities)} entities")
            if entities:
                sample = entities[0]
                fields = list(sample.keys())[:5]
                print(f"    sample fields: {fields}")
                print(f"    sample: {json.dumps(sample, indent=6, default=str)[:200]}")

        # 4. Show actor details
        print(f"\n  Actors: {len(result['actors'])}")
        for actor in result["actors"][:3]:
            p = actor.personality
            style = p.style if p else "none"
            friction = actor.friction_profile.category if actor.friction_profile else "none"
            print(f"    {actor.role} ({actor.type}) -- style={style}, friction={friction}")

        # 5. Full report
        print("\n" + "=" * 70)
        print("STEP 3: GENERATION REPORT")
        print("=" * 70)
        print(result["report"])

        # 6. Run agent actions
        print("\n" + "=" * 70)
        print("STEP 4: AGENT ACTIONS")
        print("=" * 70)

        _ensure_agent(app, "agent-1")
        action = await app.handle_action("agent-1", "email", "email_send", {
            "from_addr": "agent@acme.com",
            "to_addr": "customer@test.com",
            "subject": "Re: Your support ticket",
            "body": "We have investigated your issue and found a solution.",
        })
        print(f"  email_send result: {json.dumps(action, indent=4, default=str)[:300]}")

        # 7. Query state to show persisted entities
        print("\n" + "=" * 70)
        print("STEP 5: STATE ENGINE QUERY")
        print("=" * 70)

        state = app.registry.get("state")
        for etype in result["entities"]:
            entities = await state.query_entities(etype)
            print(f"  {etype}: {len(entities)} entities in state")

        emails = await state.query_entities("email")
        # Show the email we just sent
        for e in emails:
            if e.get("subject") == "Re: Your support ticket":
                print(f"\n  Sent email found in state:")
                print(f"    {json.dumps(e, indent=6, default=str)[:300]}")

        # 8. Verify everything worked
        assert plan.name == "Acme Support Organization"
        assert result["entities"]
        assert result["actors"]
        assert "email_id" in action

    async def test_entity_values_verified_after_population(self, app_with_mock_llm) -> None:
        """Verify entity field VALUES, not just counts, after StateEngine population.

        Uses ``app_with_mock_llm`` because generation requires LLM.
        """
        app = app_with_mock_llm
        compiler = app.registry.get("world_compiler")
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        result = await compiler.generate_world(plan)

        state = app.registry.get("state")
        for entity_type, entity_list in result["entities"].items():
            stored = await state.query_entities(entity_type)
            assert len(stored) == len(entity_list), (
                f"{entity_type}: expected {len(entity_list)}, got {len(stored)}"
            )
            # Verify IDs match
            generated_ids = sorted(e.get("id", "") for e in entity_list)
            stored_ids = sorted(
                e.get("_entity_id", e.get("id", "")) for e in stored
            )
            assert generated_ids == stored_ids, (
                f"{entity_type} IDs mismatch: {generated_ids[:3]} vs {stored_ids[:3]}"
            )
            # Verify field values preserved
            if entity_list:
                gen_sample = entity_list[0]
                gen_id = gen_sample.get("id", "")
                for stored_e in stored:
                    sid = stored_e.get("_entity_id", stored_e.get("id", ""))
                    if sid == gen_id:
                        for k, v in gen_sample.items():
                            if not k.startswith("_"):
                                assert stored_e.get(k) == v, (
                                    f"{entity_type}.{k}: expected {v}, "
                                    f"got {stored_e.get(k)}"
                                )
                        break


# ── Live LLM tests (require GOOGLE_API_KEY) ──────────────────────


@pytest.mark.asyncio
class TestLiveWorldGeneration:
    """Integration tests that use a REAL LLM via the ``live_app`` fixture.

    These are skipped unless GOOGLE_API_KEY is set in the environment.
    """

    async def test_live_generate_produces_entities(self, live_app) -> None:
        """generate_world() with real LLM returns populated entity dict."""
        compiler = live_app.registry.get("world_compiler")
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/minimal_world.yaml",
        )
        result = await compiler.generate_world(plan)
        assert "entities" in result
        total = sum(len(v) for v in result["entities"].values())
        assert total > 0

    async def test_live_generate_produces_actors(self, live_app) -> None:
        """generate_world() with real LLM creates ActorDefinition instances."""
        compiler = live_app.registry.get("world_compiler")
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/minimal_world.yaml",
        )
        result = await compiler.generate_world(plan)
        assert "actors" in result
        assert len(result["actors"]) > 0

    async def test_live_full_acme_flow(self, live_app) -> None:
        """Full compile -> generate -> act with real LLM on acme world."""
        compiler = live_app.registry.get("world_compiler")
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        result = await compiler.generate_world(plan)
        assert result["entities"]
        assert result["actors"]
        assert result["seeds_processed"] >= 3

        # Agent action after generation
        action = await live_app.handle_action(
            "agent-1", "email", "email_send",
            {
                "from_addr": "agent@acme.com",
                "to_addr": "customer@test.com",
                "subject": "Live test",
                "body": "Testing with real LLM.",
            },
        )
        assert "email_id" in action
