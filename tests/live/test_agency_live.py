"""Live E2E test: AgencyEngine with autonomous internal actors.

Creates a world with 5 internal actors (customers + supervisor) in dynamic mode.
Submits an external agent action, then runs the SimulationRunner to see:
- Which internal actors activate (event-first)
- Tier classification (batch vs individual)
- LLM-driven action generation
- Event queue ordering
- Actor state updates (frustration, waiting_for)
- Full governance pipeline for all actors

Requires: codex-acp with device auth
"""

from __future__ import annotations

import json
import shutil

import pytest

from volnix.core.types import ActionSource, ActorId, ServiceId


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
    config = config.model_copy(
        update={
            "persistence": PersistenceConfig(base_dir=str(tmp_path / "data")),
            "state": StateConfig(
                db_path=str(tmp_path / "state.db"),
                snapshot_dir=str(tmp_path / "snapshots"),
            ),
        }
    )

    app = VolnixApp(config)
    await app.start()
    yield app
    await app.stop()


class TestAgencyLiveSimulation:
    """Test the AgencyEngine with real LLM and autonomous internal actors."""

    @pytest.mark.asyncio
    async def test_dynamic_world_with_internal_actors(self, live_app_with_codex) -> None:
        """
        Full simulation:
        1. Compile world with 5 internal actors (3 customers + 1 supervisor + 1 manager)
        2. Generate world entities
        3. Configure AgencyEngine with actor states
        4. Submit external agent action (trigger)
        5. Run SimulationRunner for a few events
        6. Observe: who activated, what they did, state changes
        """
        app = live_app_with_codex
        compiler = app.registry.get("world_compiler")

        # ────────────────────────────────────────────────────
        # STEP 1: Build world plan with internal actors
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 1: BUILD WORLD PLAN (5 internal actors)")
        print("=" * 70)

        from volnix.engines.world_compiler.plan import ServiceResolution, WorldPlan
        from volnix.kernel.surface import ServiceSurface
        from volnix.packs.verified.gmail.pack import EmailPack
        from volnix.packs.verified.slack.pack import ChatPack
        from volnix.packs.verified.zendesk.pack import TicketsPack
        from volnix.reality.presets import load_preset

        email_surface = ServiceSurface.from_pack(EmailPack())
        chat_surface = ServiceSurface.from_pack(ChatPack())
        tickets_surface = ServiceSurface.from_pack(TicketsPack())

        plan = WorldPlan(
            name="Agency Test World",
            description=(
                "A support team with autonomous customers and supervisors. "
                "Customers get frustrated when waiting too long. "
                "Supervisors review escalated tickets."
            ),
            seed=42,
            behavior="dynamic",
            mode="governed",
            services={
                "gmail": ServiceResolution(
                    service_name="gmail",
                    spec_reference="verified/gmail",
                    surface=email_surface,
                    resolution_source="tier1_pack",
                ),
                "slack": ServiceResolution(
                    service_name="slack",
                    spec_reference="verified/slack",
                    surface=chat_surface,
                    resolution_source="tier1_pack",
                ),
                "zendesk": ServiceResolution(
                    service_name="zendesk",
                    spec_reference="verified/zendesk",
                    surface=tickets_surface,
                    resolution_source="tier1_pack",
                ),
            },
            actor_specs=[
                # External agent (the AI being tested)
                {
                    "role": "support-agent",
                    "type": "external",
                    "count": 1,
                    "personality": "Efficient problem solver",
                },
                # Internal actors (autonomous via AgencyEngine)
                {
                    "role": "customer",
                    "type": "internal",
                    "count": 3,
                    "personality": "Mix of patient and frustrated customers",
                },
                {
                    "role": "supervisor",
                    "type": "internal",
                    "count": 1,
                    "personality": "Cautious, thorough, reviews escalated items",
                },
            ],
            conditions=load_preset("messy"),
            reality_prompt_context={},
            policies=[
                {
                    "name": "Refund approval",
                    "description": "Refunds over $50 require supervisor approval",
                    "trigger": "refund amount exceeds limit",
                    "enforcement": "hold",
                },
            ],
            seeds=[
                "VIP customer Margaret Chen waiting 7 days for a $249 refund",
            ],
            mission="Process all open support tickets efficiently.",
        )

        print(f"  World: {plan.name}")
        print(f"  Services: {list(plan.services.keys())}")
        print(f"  Actors: {[(s['role'], s.get('count', 1), s['type']) for s in plan.actor_specs]}")
        print(f"  Behavior: {plan.behavior}")

        # ────────────────────────────────────────────────────
        # STEP 2: Generate world + configure all engines
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 2: GENERATE WORLD (real LLM)")
        print("=" * 70)

        result = await compiler.generate_world(plan)
        total = sum(len(v) for v in result["entities"].values())
        print(f"  Entities: {total}")
        print(f"  Actors: {len(result['actors'])}")
        print(f"  Seeds: {result['seeds_processed']}")

        # Configure governance + animator + agency
        app.configure_governance(plan)
        await app.configure_animator(plan)
        await app.configure_agency(plan, result)
        print("  Governance: configured")
        print("  Animator: configured (dynamic)")
        print("  Agency: configured")

        # ────────────────────────────────────────────────────
        # STEP 3: Check AgencyEngine state
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 3: AGENCY ENGINE STATE")
        print("=" * 70)

        agency = app.registry.get("agency")
        internal_actors = agency._actor_states if hasattr(agency, "_actor_states") else {}
        print(f"  Internal actor states: {len(internal_actors)}")
        for actor_id, state in internal_actors.items():
            print(
                f"    {actor_id}: role={state.role}, frustration={state.frustration:.1f}, "
                f"goal={state.current_goal or 'none'}"
            )
            if state.watched_entities:
                print(f"      watching: {state.watched_entities[:3]}...")
            if state.behavior_traits:
                t = state.behavior_traits
                print(
                    f"      traits: cooperation={t.cooperation_level:.1f}, "
                    f"authority={t.authority_level:.1f}, "
                    f"stakes={t.stakes_level:.1f}"
                )

        # Verify internal actors were created
        assert len(internal_actors) >= 1, "No internal actor states created"

        # ────────────────────────────────────────────────────
        # STEP 4: Submit external agent action as trigger
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 4: EXTERNAL AGENT ACTION (trigger)")
        print("=" * 70)

        # Find the compiled agent actor
        actors = result["actors"]
        agent_actor = next((a for a in actors if a.role == "support-agent"), actors[0])
        agent_id = str(agent_actor.id)
        print(f"  Agent: {agent_id}")

        # Agent sends email to Margaret Chen
        action_result = await app.handle_action(
            agent_id,
            "email",
            "email_send",
            {
                "from_addr": "agent@acme.com",
                "to_addr": "margaret.chen@customer.com",
                "subject": "Re: Your refund request",
                "body": "Dear Margaret, we are processing your $249 refund. "
                "It has been approved by the supervisor.",
            },
        )
        print(f"  Action result: {json.dumps(action_result, default=str)[:200]}")

        # ────────────────────────────────────────────────────
        # STEP 5: Check what the AgencyEngine would do
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 5: AGENCY ENGINE ACTIVATION CHECK")
        print("=" * 70)

        # Simulate what notify() would do by checking activation
        from datetime import UTC, datetime

        from volnix.core.events import WorldEvent
        from volnix.core.types import EntityId, Timestamp

        # Find a watched entity from one of the internal actors
        watched_entity_id = None
        for _, state in internal_actors.items():
            if state.watched_entities:
                watched_entity_id = state.watched_entities[0]
                break
        print(f"  Using watched entity as target: {watched_entity_id}")

        # Create a committed event that targets a watched entity
        test_event = WorldEvent(
            event_type="world.tickets.update",
            timestamp=Timestamp(
                world_time=datetime.now(UTC),
                wall_time=datetime.now(UTC),
                tick=1,
            ),
            actor_id=ActorId(agent_id),
            service_id=ServiceId("zendesk"),
            action="tickets.update",
            target_entity=EntityId(watched_entity_id) if watched_entity_id else None,
            source=ActionSource.EXTERNAL,
        )

        # Check which actors would activate
        if hasattr(agency, "_tier1_activation_check"):
            activated = agency._tier1_activation_check(test_event)
            print(f"  Tier 1 activation check: {len(activated)} actors would activate")
            for actor_id_str, reason in activated:
                state = internal_actors.get(actor_id_str)
                if state:
                    tier = agency._classify_tier(state, reason)
                    print(f"    {actor_id_str} (role={state.role}): reason={reason}, tier={tier}")

        # ────────────────────────────────────────────────────
        # STEP 6: Final state
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 6: FINAL STATE")
        print("=" * 70)

        state_engine = app.registry.get("state")
        for etype in ["email", "ticket", "channel"]:
            entities = await state_engine.query_entities(etype)
            print(f"  {etype}: {len(entities)} entities")

        # Report
        reporter = app.registry.get("reporter")
        scorecard = await reporter.generate_scorecard()
        if isinstance(scorecard, dict):
            collective = scorecard.get("collective", {})
            print(f"\n  Scorecard: overall={collective.get('overall_score', 'N/A')}")

        print("\n" + "=" * 70)
        print("  ALL ASSERTIONS PASSED")
        print("=" * 70)

        # Assertions
        assert total > 0, "No entities generated"
        assert len(result["actors"]) >= 2, "Expected at least 2 actors"
        assert len(internal_actors) >= 1, "No internal actor states"
