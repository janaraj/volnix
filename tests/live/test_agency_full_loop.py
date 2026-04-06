"""Live E2E test: Full AgencyEngine loop with SimulationRunner.

External agent submits action → EventQueue → SimulationRunner processes →
AgencyEngine.notify() → internal actors activate → LLM generates actions →
new ActionEnvelopes submitted → processed through pipeline.

This is the first test where internal actors actually MAKE DECISIONS via LLM.

Requires: codex-acp with device auth
"""

from __future__ import annotations

import shutil

import pytest

from volnix.core.envelope import ActionEnvelope
from volnix.core.types import (
    ActionSource,
    ActorId,
    EnvelopePriority,
    ServiceId,
)
from volnix.simulation.config import SimulationRunnerConfig
from volnix.simulation.event_queue import EventQueue
from volnix.simulation.runner import SimulationRunner, SimulationStatus


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


class TestFullAgencyLoop:
    """Full simulation loop: external action → internal actor reaction via LLM."""

    @pytest.mark.asyncio
    async def test_simulation_runner_with_agency(self, live_app_with_codex) -> None:
        """
        1. Compile world with internal actors
        2. Configure AgencyEngine
        3. Create EventQueue + SimulationRunner
        4. Submit external agent action as ActionEnvelope
        5. Run SimulationRunner — it processes the action, notifies AgencyEngine,
           AgencyEngine makes LLM call for activated actors, submits new envelopes
        6. Runner processes those too
        7. Observe the full chain
        """
        app = live_app_with_codex
        compiler = app.registry.get("world_compiler")

        # ────────────────────────────────────────────────────
        # STEP 1: Compile world
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 1: COMPILE WORLD")
        print("=" * 70)

        from volnix.engines.world_compiler.plan import ServiceResolution, WorldPlan
        from volnix.kernel.surface import ServiceSurface
        from volnix.packs.verified.gmail.pack import EmailPack
        from volnix.packs.verified.zendesk.pack import TicketsPack
        from volnix.reality.presets import load_preset

        email_surface = ServiceSurface.from_pack(EmailPack())
        tickets_surface = ServiceSurface.from_pack(TicketsPack())

        plan = WorldPlan(
            name="Full Agency Loop Test",
            description="Support team with autonomous customers.",
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
                "zendesk": ServiceResolution(
                    service_name="zendesk",
                    spec_reference="verified/zendesk",
                    surface=tickets_surface,
                    resolution_source="tier1_pack",
                ),
            },
            actor_specs=[
                {
                    "role": "support-agent",
                    "type": "external",
                    "count": 1,
                    "personality": "Efficient",
                },
                {
                    "role": "customer",
                    "type": "internal",
                    "count": 1,
                    "personality": "Frustrated customer waiting for refund",
                },
                {
                    "role": "supervisor",
                    "type": "internal",
                    "count": 1,
                    "personality": "Reviews escalations",
                },
            ],
            conditions=load_preset("messy"),
            reality_prompt_context={},
            seeds=["Customer Margaret waiting 7 days for $249 refund"],
            mission="Resolve support tickets.",
        )

        result = await compiler.generate_world(plan)
        total = sum(len(v) for v in result["entities"].values())
        print(f"  Entities: {total}, Actors: {len(result['actors'])}")

        app.configure_governance(plan)
        await app.configure_animator(plan)
        await app.configure_agency(plan, result)

        agency = app.registry.get("agency")
        animator = app.registry.get("animator")
        internal_count = len(agency._actor_states) if hasattr(agency, "_actor_states") else 0
        print(f"  Internal actors: {internal_count}")

        # ────────────────────────────────────────────────────
        # STEP 2: Set up EventQueue + SimulationRunner
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 2: SET UP SIMULATION RUNNER")
        print("=" * 70)

        event_queue = EventQueue()

        # Pipeline executor: converts ActionEnvelope → pipeline execution → WorldEvent
        async def pipeline_executor(envelope: ActionEnvelope):
            from datetime import UTC, datetime

            from volnix.core.events import WorldEvent
            from volnix.core.types import EntityId, Timestamp

            now = datetime.now(UTC)

            # Execute through the real pipeline
            ctx_result = await app.handle_action(
                str(envelope.actor_id),
                str(envelope.target_service or ""),
                envelope.action_type,
                envelope.payload,
                tick=int(event_queue.current_time),
            )

            # Build WorldEvent — preserve envelope's target entity for activation
            # The entity ID from the payload is what actors watch
            target_id = envelope.payload.get("id")
            target = EntityId(str(target_id)) if target_id else None
            # Also check response for created entity IDs
            if target is None and isinstance(ctx_result, dict) and not ctx_result.get("error"):
                for key in ("email_id", "ticket_id", "id", "ts"):
                    if key in ctx_result:
                        target = EntityId(str(ctx_result[key]))
                        break

            event = WorldEvent(
                event_type=f"world.{envelope.action_type}",
                timestamp=Timestamp(
                    world_time=now,
                    wall_time=now,
                    tick=int(event_queue.current_time),
                ),
                actor_id=envelope.actor_id,
                service_id=ServiceId(str(envelope.target_service or "")),
                action=envelope.action_type,
                target_entity=target,
                input_data=envelope.payload,
                source=envelope.source,
            )
            return event

        config = SimulationRunnerConfig(
            max_total_events=10,  # Process at most 10 events
            max_logical_time=100.0,
            stop_on_empty_queue=True,
            max_envelopes_per_event=5,
            max_actions_per_actor_per_window=3,
            loop_breaker_threshold=8,
        )

        runner = SimulationRunner(
            event_queue=event_queue,
            pipeline_executor=pipeline_executor,
            agency_engine=agency,
            animator=animator,
            config=config,
        )

        # Connect the external agent
        agent_actor = next(
            (a for a in result["actors"] if a.role == "support-agent"), result["actors"][0]
        )
        agent_id = str(agent_actor.id)
        runner.connect_agent(ActorId(agent_id))
        print("  Runner configured: max_events=10, loop_breaker=8")
        print(f"  External agent connected: {agent_id}")

        # ────────────────────────────────────────────────────
        # STEP 3: Submit external agent action as trigger
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 3: SUBMIT EXTERNAL ACTION → EVENT QUEUE")
        print("=" * 70)

        # Find an entity that an internal actor ACTUALLY watches
        state_engine = app.registry.get("state")
        watched_entity_id = None
        watcher_id = None
        for aid, astate in (agency._actor_states or {}).items():
            if astate.watched_entities:
                watched_entity_id = str(astate.watched_entities[0])
                watcher_id = aid
                break

        if not watched_entity_id:
            # Fallback: use first ticket
            tickets = await state_engine.query_entities("ticket")
            watched_entity_id = tickets[0].get("id", "tck_001") if tickets else "tck_001"

        print(f"  Targeting watched entity: {watched_entity_id} (watched by: {watcher_id})")

        external_envelope = ActionEnvelope(
            actor_id=ActorId(agent_id),
            source=ActionSource.EXTERNAL,
            action_type="tickets.update",
            target_service=ServiceId("tickets"),
            payload={
                "id": watched_entity_id,
                "status": "open",
                "assignee_id": agent_id,
            },
            logical_time=1.0,
            priority=EnvelopePriority.EXTERNAL,
        )
        event_queue.submit(external_envelope)
        print(f"  Submitted: {external_envelope.action_type} targeting {watched_entity_id}")
        print(f"  Queue size: {event_queue.size}")

        # ────────────────────────────────────────────────────
        # STEP 4: RUN THE SIMULATION LOOP
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 4: RUN SIMULATION LOOP")
        print("=" * 70)

        # Diagnostic: check agency state before run
        print(f"  Agency prompt_builder: {agency._prompt_builder is not None}")
        print(f"  Agency actor_states: {len(agency._actor_states)}")
        print(f"  Agency available_actions: {len(agency._available_actions)}")
        for aid, astate in agency._actor_states.items():
            print(f"    {aid}: watching {astate.watched_entities[:3]}")

        stop_reason = await runner.run()

        print(f"  Stop reason: {stop_reason}")
        print(f"  Total events processed: {runner.total_events_processed}")
        print(f"  Final queue size: {event_queue.size}")
        print(f"  Simulation status: {runner.status}")

        # ────────────────────────────────────────────────────
        # STEP 5: Inspect what happened
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 5: WHAT HAPPENED")
        print("=" * 70)

        # Check actor states after simulation
        for actor_id_str, state in (agency._actor_states or {}).items():
            if state.actor_type == "internal":
                print(f"  {actor_id_str} (role={state.role}):")
                print(f"    frustration: {state.frustration:.2f}")
                print(f"    recent_interactions: {len(state.recent_interactions)}")
                if state.recent_interactions:
                    for interaction in state.recent_interactions[-3:]:
                        print(f"      - {interaction[:80]}")
                if state.pending_notifications:
                    print(f"    pending_notifications: {len(state.pending_notifications)}")

        # Check state engine for new entities
        emails_after = await state_engine.query_entities("email")
        tickets_after = await state_engine.query_entities("ticket")
        print(f"\n  Emails in state: {len(emails_after)}")
        print(f"  Tickets in state: {len(tickets_after)}")

        # Report
        reporter = app.registry.get("reporter")
        scorecard = await reporter.generate_scorecard()
        if isinstance(scorecard, dict):
            collective = scorecard.get("collective", {})
            print(f"  Scorecard: overall={collective.get('overall_score', 'N/A')}")

        # ────────────────────────────────────────────────────
        # STEP 6: Assertions
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 6: ASSERTIONS")
        print("=" * 70)

        assert runner.total_events_processed >= 1, "At least 1 event should be processed"
        assert stop_reason is not None, "Simulation should have stopped"
        assert runner.status in (SimulationStatus.COMPLETED, SimulationStatus.STOPPED)

        print(f"  Events processed: {runner.total_events_processed}")
        print(f"  Stop reason: {stop_reason}")
        print("  ALL ASSERTIONS PASSED")
        print("=" * 70)
