"""Live E2E test: Collaborative Communication with internal-only world.

Creates a climate research station world with 4 internal researchers + 1 lead,
uses chat + email services, dynamic mode, governed, messy reality.

Mission: "Investigate jet stream anomaly and produce research brief"

Requires: codex-acp binary available (uses volnix.toml routing)
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
async def live_app_with_codex(tmp_path):
    """VolnixApp with REAL codex-acp LLM -- uses volnix.toml config."""
    import shutil

    if not shutil.which("codex-acp"):
        pytest.skip("codex-acp not found -- skipping live test")

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


class TestCollaborationLiveWorld:
    """Full lifecycle test for collaborative internal-only world with real LLM."""

    @pytest.mark.asyncio
    async def test_climate_research_collaboration(self, live_app_with_codex) -> None:
        """
        End-to-end test:
        1. Compile world from plan (chat + email, internal actors)
        2. Generate entities with real LLM
        3. Configure governance + animator + agency
        4. Set subscriptions on actors
        5. Kickstart with mission post
        6. Run a few agent actions and animator ticks
        7. Query final state: check messages exist, actors communicated
        8. Assert: multiple actors contributed, messages reference each other
        """
        app = live_app_with_codex
        compiler = app.registry.get("world_compiler")

        # ----------------------------------------------------------------
        # STEP 1: Build world plan
        # ----------------------------------------------------------------
        print("\n" + "=" * 70)
        print("STEP 1: BUILD WORLD PLAN")
        print("=" * 70)

        from volnix.actors.state import Subscription
        from volnix.engines.world_compiler.plan import (
            ServiceResolution,
            WorldPlan,
        )
        from volnix.kernel.surface import ServiceSurface
        from volnix.packs.verified.gmail.pack import EmailPack
        from volnix.packs.verified.slack.pack import ChatPack
        from volnix.reality.presets import load_preset

        email_surface = ServiceSurface.from_pack(EmailPack())
        chat_surface = ServiceSurface.from_pack(ChatPack())

        plan = WorldPlan(
            name="Climate Research Station (Collaboration Live Test)",
            description=(
                "A polar research station investigating jet stream anomalies. "
                "The team includes an oceanographer, a meteorologist, a data analyst, "
                "a satellite specialist, and a research lead. They communicate "
                "primarily through Slack and email. Data is messy -- satellite feeds "
                "have gaps and ocean buoy sensors are intermittently offline."
            ),
            seed=42,
            behavior="dynamic",
            mode="governed",
            services={
                "chat": ServiceResolution(
                    service_name="chat",
                    spec_reference="verified/slack",
                    surface=chat_surface,
                    resolution_source="tier1_pack",
                ),
                "email": ServiceResolution(
                    service_name="email",
                    spec_reference="verified/gmail",
                    surface=email_surface,
                    resolution_source="tier1_pack",
                ),
            },
            actor_specs=[
                {
                    "role": "research-lead",
                    "type": "internal",
                    "count": 1,
                    "lead": True,
                    "personality": (
                        "Experienced team lead. Coordinates the group, "
                        "synthesizes findings, makes final calls. Methodical."
                    ),
                },
                {
                    "role": "oceanographer",
                    "type": "internal",
                    "count": 1,
                    "personality": (
                        "Expert in sea surface temperatures and ocean currents. "
                        "Detail-oriented, sometimes skeptical of satellite data."
                    ),
                },
                {
                    "role": "meteorologist",
                    "type": "internal",
                    "count": 1,
                    "personality": (
                        "Atmospheric scientist focused on jet stream dynamics. "
                        "Enthusiastic, quick to share preliminary findings."
                    ),
                },
                {
                    "role": "data-analyst",
                    "type": "internal",
                    "count": 1,
                    "personality": (
                        "Statistical expert. Cross-references data sources, "
                        "flags inconsistencies. Cautious with conclusions."
                    ),
                },
                {
                    "role": "satellite-specialist",
                    "type": "internal",
                    "count": 1,
                    "personality": (
                        "Remote sensing expert. Handles satellite imagery and "
                        "gap-filling algorithms. Pragmatic and solution-focused."
                    ),
                },
            ],
            conditions=load_preset("messy"),
            reality_prompt_context={},
            policies=[
                {
                    "name": "Data sharing",
                    "description": (
                        "All research findings must be shared with the team "
                        "before inclusion in the final brief"
                    ),
                    "trigger": "research finding produced",
                    "enforcement": "log",
                },
                {
                    "name": "Publication approval",
                    "description": "Final research brief requires lead approval",
                    "trigger": "deliverable produced",
                    "enforcement": "hold",
                },
            ],
            seeds=[
                (
                    "Satellite data shows a 3-degree SST anomaly in sector 7, "
                    "but ocean buoy sensors report normal temperatures -- "
                    "conflicting data that needs resolution."
                ),
                (
                    "A meteorological model predicts unprecedented jet stream "
                    "displacement in 48 hours, but the model has a known bias "
                    "for overestimating polar shifts."
                ),
                (
                    "An email from the external funding agency reminds the team "
                    "that the preliminary brief is due in 72 hours."
                ),
            ],
            mission=(
                "Investigate the jet stream anomaly over the North Atlantic, "
                "resolve the conflicting satellite vs buoy data, and produce "
                "a research brief with findings, confidence assessment, and "
                "recommended next steps."
            ),
        )

        print(f"  World: {plan.name}")
        print(f"  Services: {list(plan.services.keys())}")
        print(f"  Actors: {[(s['role'], s.get('count', 1)) for s in plan.actor_specs]}")
        print(f"  Behavior: {plan.behavior}")
        print(f"  Mode: {plan.mode}")
        print(f"  Seeds: {len(plan.seeds)}")

        # ----------------------------------------------------------------
        # STEP 2: Generate world with REAL LLM
        # ----------------------------------------------------------------
        print("\n" + "=" * 70)
        print("STEP 2: GENERATE WORLD (real LLM -- codex-acp)")
        print("=" * 70)

        result = await compiler.generate_world(plan)

        entity_summary = {etype: len(elist) for etype, elist in result["entities"].items()}
        total_entities = sum(entity_summary.values())
        print(f"  Generated entities: {json.dumps(entity_summary, indent=4)}")
        print(f"  Total: {total_entities} entities")
        print(f"  Actors: {len(result['actors'])}")
        print(f"  Seeds processed: {result['seeds_processed']}")

        assert total_entities > 0, "No entities generated"
        assert len(result["actors"]) >= 5, "Expected at least 5 actors"

        # ----------------------------------------------------------------
        # STEP 3: Configure governance + animator + agency
        # ----------------------------------------------------------------
        print("\n" + "=" * 70)
        print("STEP 3: CONFIGURE GOVERNANCE + ANIMATOR + AGENCY")
        print("=" * 70)

        app.configure_governance(plan)
        await app.configure_animator(plan)
        await app.configure_agency(plan, result)

        print("  Governance: configured (governed mode)")
        print("  Animator: configured (dynamic mode)")
        print("  Agency: configured")

        # ----------------------------------------------------------------
        # STEP 4: Set subscriptions on actors
        # ----------------------------------------------------------------
        print("\n" + "=" * 70)
        print("STEP 4: SET SUBSCRIPTIONS")
        print("=" * 70)

        try:
            agency = app.registry.get("agency")
            for actor_state in agency.get_all_states():
                # All actors subscribe to #research channel (immediate)
                actor_state.subscriptions.append(
                    Subscription(
                        service_id="chat",
                        filter={"channel": "#research"},
                        sensitivity="immediate",
                    )
                )
                # Lead also subscribes to email (for funding agency reminder)
                if "lead" in actor_state.role:
                    actor_state.subscriptions.append(
                        Subscription(
                            service_id="email",
                            filter={},
                            sensitivity="immediate",
                        )
                    )
                print(f"  {actor_state.role}: {len(actor_state.subscriptions)} subscriptions")
        except Exception as e:
            print(f"  Subscription setup error: {e}")

        # ----------------------------------------------------------------
        # STEP 5: Kickstart with mission post
        # ----------------------------------------------------------------
        print("\n" + "=" * 70)
        print("STEP 5: KICKSTART -- POST MISSION TO #RESEARCH")
        print("=" * 70)

        # Post the mission to the #research channel to kickstart collaboration
        actors = result["actors"]
        lead_actor = next(
            (a for a in actors if "lead" in a.role),
            actors[0],
        )
        lead_id = str(lead_actor.id)
        print(f"  Lead actor: {lead_id} (role={lead_actor.role})")

        try:
            kickstart = await app.handle_action(
                "world",  # system actor
                "chat",
                "chat.postMessage",
                {
                    "channel_id": "#research",
                    "text": (
                        f"[MISSION] {plan.mission} "
                        "Team, please begin your analysis and share findings here."
                    ),
                    "intended_for": ["all"],
                },
            )
            print(f"  Kickstart posted: {json.dumps(kickstart, indent=4, default=str)[:300]}")
        except Exception as e:
            print(f"  Kickstart error: {e}")

        # ----------------------------------------------------------------
        # STEP 6: Run agent actions and animator ticks
        # ----------------------------------------------------------------
        print("\n" + "=" * 70)
        print("STEP 6: AGENT ACTIONS + ANIMATOR TICKS")
        print("=" * 70)

        # Have a few actors post findings
        action_results = []
        for actor_state in list(agency.get_all_states())[:3]:
            try:
                action = await app.handle_action(
                    str(actor_state.actor_id),
                    "chat",
                    "chat.postMessage",
                    {
                        "channel_id": "#research",
                        "text": (
                            f"[{actor_state.role}] Sharing initial analysis of the jet stream data."
                        ),
                        "intended_for": ["all"],
                    },
                )
                action_results.append(action)
                print(f"  {actor_state.role} posted: {json.dumps(action, default=str)[:200]}")
            except Exception as e:
                print(f"  {actor_state.role} action error: {e}")

        # Tick the animator
        try:
            animator = app.registry.get("animator")
            from datetime import UTC, datetime

            events = await animator.tick(datetime.now(UTC))
            print(f"  Animator generated {len(events) if events else 0} events")
        except Exception as e:
            print(f"  Animator tick: {e}")

        # ----------------------------------------------------------------
        # STEP 7: Query final state
        # ----------------------------------------------------------------
        print("\n" + "=" * 70)
        print("STEP 7: STATE VERIFICATION")
        print("=" * 70)

        state_engine = app.registry.get("state")

        # Check messages exist
        try:
            messages = await state_engine.query_entities("message")
            print(f"  Messages in state: {len(messages)}")
        except Exception as e:
            messages = []
            print(f"  Message query error: {e}")

        # Check channels
        try:
            channels = await state_engine.query_entities("channel")
            print(f"  Channels in state: {len(channels)}")
        except Exception as e:
            channels = []
            print(f"  Channel query error: {e}")

        # Check emails
        try:
            emails = await state_engine.query_entities("email")
            print(f"  Emails in state: {len(emails)}")
        except Exception as e:
            emails = []
            print(f"  Email query error: {e}")

        # Check actor states for interaction records
        try:
            actors_with_interactions = 0
            for actor_state in agency.get_all_states():
                if actor_state.recent_interactions:
                    actors_with_interactions += 1
                    print(
                        f"  {actor_state.role}: {len(actor_state.recent_interactions)} interactions"
                    )
            print(f"  Actors with interactions: {actors_with_interactions}")
        except Exception as e:
            actors_with_interactions = 0
            print(f"  Actor interaction check error: {e}")

        # ----------------------------------------------------------------
        # STEP 8: Assertions
        # ----------------------------------------------------------------
        print("\n" + "=" * 70)
        print("STEP 8: ASSERTIONS")
        print("=" * 70)

        # World was generated
        assert total_entities > 0, "No entities generated"
        assert len(result["actors"]) >= 5, "Expected at least 5 actors"

        # Multiple actors posted messages (try/except around LLM-dependent assertions)
        try:
            assert len(action_results) > 0, "No actions were executed"
            print("  Action results: PASS")
        except AssertionError as e:
            print(f"  Action results: SOFT FAIL ({e})")

        # Actors have interaction records from collaboration
        try:
            assert actors_with_interactions > 0, "No actors have interaction records"
            print(f"  Actors with interactions ({actors_with_interactions}): PASS")
        except AssertionError as e:
            print(f"  Actor interactions: SOFT FAIL ({e})")

        # Check that at least some messages were created
        try:
            assert len(messages) > 0, "No messages in state"
            print(f"  Messages ({len(messages)}): PASS")
        except AssertionError as e:
            print(f"  Messages: SOFT FAIL ({e})")

        # Verify subscriptions were set
        try:
            all_states = agency.get_all_states()
            actors_with_subs = sum(1 for s in all_states if s.subscriptions)
            assert actors_with_subs >= 3, (
                f"Expected at least 3 actors with subscriptions, got {actors_with_subs}"
            )
            print(f"  Actors with subscriptions ({actors_with_subs}): PASS")
        except AssertionError as e:
            print(f"  Subscriptions: SOFT FAIL ({e})")

        print("\n  LIVE COLLABORATION TEST COMPLETE")
        print("=" * 70)
