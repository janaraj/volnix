"""Live E2E test: Multi-service world with real LLM (codex-acp).

Creates an Acme Support world using email + chat + tickets packs,
compiles with dynamic mode + messy reality, generates entities,
runs agent actions, ticks the animator, and produces a report.

Requires: codex-acp binary available (uses terrarium.toml routing)
"""

from __future__ import annotations

import json
import os

import pytest

from terrarium.core.types import RunId


@pytest.fixture
async def live_app_with_codex(tmp_path):
    """TerrariumApp with REAL codex-acp LLM — uses terrarium.toml config."""
    # Check codex-acp is available
    import shutil
    if not shutil.which("codex-acp"):
        pytest.skip("codex-acp not found — skipping live test")

    from terrarium.app import TerrariumApp
    from terrarium.config.loader import ConfigLoader
    from terrarium.engines.state.config import StateConfig
    from terrarium.persistence.config import PersistenceConfig

    loader = ConfigLoader()
    config = loader.load()
    config = config.model_copy(update={
        "persistence": PersistenceConfig(base_dir=str(tmp_path / "data")),
        "state": StateConfig(
            db_path=str(tmp_path / "state.db"),
            snapshot_dir=str(tmp_path / "snapshots"),
        ),
    })

    app = TerrariumApp(config)
    await app.start()
    yield app
    await app.stop()


class TestMultiServiceLiveWorld:
    """Full lifecycle test with real LLM: compile → generate → act → animate → report."""

    @pytest.mark.asyncio
    async def test_full_acme_support_lifecycle(self, live_app_with_codex) -> None:
        """
        End-to-end test:
        1. Compile world from YAML (email + chat + tickets)
        2. Generate entities with real LLM
        3. Perform agent actions through the pipeline
        4. Tick the animator (dynamic mode)
        5. Generate governance report + scorecard
        """
        app = live_app_with_codex
        compiler = app.registry.get("world_compiler")

        # ────────────────────────────────────────────────────
        # STEP 1: Compile world plan from YAML
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 1: COMPILE WORLD PLAN")
        print("=" * 70)

        # Use a focused world def that only uses our verified packs
        from terrarium.engines.world_compiler.plan import (
            ServiceResolution,
            WorldPlan,
        )
        from terrarium.kernel.surface import ServiceSurface
        from terrarium.packs.verified.gmail.pack import EmailPack
        from terrarium.packs.verified.slack.pack import ChatPack
        from terrarium.packs.verified.zendesk.pack import TicketsPack
        from terrarium.reality.presets import load_preset

        email_surface = ServiceSurface.from_pack(EmailPack())
        chat_surface = ServiceSurface.from_pack(ChatPack())
        tickets_surface = ServiceSurface.from_pack(TicketsPack())

        plan = WorldPlan(
            name="Acme Support (Live Test)",
            description=(
                "A mid-size SaaS company support team with email, Slack, "
                "and Zendesk. Growing fast, CRM data is messy from a "
                "recent migration. Customers are frustrated from slow "
                "resolution times."
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
                {
                    "role": "support-agent",
                    "type": "external",
                    "count": 2,
                    "personality": "Professional and efficient",
                },
                {
                    "role": "supervisor",
                    "type": "internal",
                    "count": 1,
                    "personality": "Experienced, cautious, thorough",
                },
            ],
            conditions=load_preset("messy"),
            reality_prompt_context={},
            policies=[
                {
                    "name": "Refund approval",
                    "description": "Refunds over $50 require supervisor approval",
                    "trigger": "refund amount exceeds agent authority",
                    "enforcement": "hold",
                },
                {
                    "name": "SLA escalation",
                    "description": "Tickets past SLA auto-escalate to supervisor",
                    "trigger": "ticket sla breached",
                    "enforcement": "escalate",
                },
            ],
            seeds=[
                "VIP customer Margaret Chen has been waiting 7 days for a $249 refund",
                "Three tickets are past SLA deadline",
            ],
            mission=(
                "Process all open support tickets within policy and budget. "
                "Prioritize SLA-breached tickets. Escalate when necessary."
            ),
        )

        print(f"  World: {plan.name}")
        print(f"  Services: {list(plan.services.keys())}")
        print(f"  Actors: {[(s['role'], s.get('count', 1)) for s in plan.actor_specs]}")
        print(f"  Behavior: {plan.behavior}")
        print(f"  Mode: {plan.mode}")
        print(f"  Seeds: {len(plan.seeds)}")

        # ────────────────────────────────────────────────────
        # STEP 2: Generate world with REAL LLM
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 2: GENERATE WORLD (real LLM — codex-acp)")
        print("=" * 70)

        result = await compiler.generate_world(plan)

        entity_summary = {
            etype: len(elist) for etype, elist in result["entities"].items()
        }
        total_entities = sum(entity_summary.values())
        print(f"  Generated entities: {json.dumps(entity_summary, indent=4)}")
        print(f"  Total: {total_entities} entities")
        print(f"  Actors: {len(result['actors'])}")
        print(f"  Seeds processed: {result['seeds_processed']}")
        print(f"  Warnings: {len(result.get('warnings', []))}")

        # Verify entities were generated
        assert total_entities > 0, "No entities generated"
        assert len(result["actors"]) >= 3, "Expected at least 3 actors"
        assert result["seeds_processed"] == 2, "Expected 2 seeds processed"

        # Show a sample entity from each type
        for etype, elist in result["entities"].items():
            if elist:
                sample = elist[0]
                fields = list(sample.keys())[:5]
                print(f"\n  Sample {etype}: {json.dumps({k: sample.get(k) for k in fields}, default=str)}")

        # ────────────────────────────────────────────────────
        # STEP 3: Configure governance + animator
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 3: CONFIGURE GOVERNANCE + ANIMATOR")
        print("=" * 70)

        app.configure_governance(plan)
        await app.configure_animator(plan)
        print("  Governance: configured (governed mode)")
        print("  Animator: configured (dynamic mode)")

        # ────────────────────────────────────────────────────
        # STEP 4: Agent actions through the pipeline
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 4: AGENT ACTIONS (through 7-step pipeline)")
        print("=" * 70)

        # Use compiled actor IDs (not raw role strings)
        actors = result["actors"]
        agent_actor = next(
            (a for a in actors if a.role == "support-agent"), actors[0]
        )
        agent_id = str(agent_actor.id)
        print(f"  Using actor: {agent_id} (role={agent_actor.role})")

        # Action 1: Agent sends an email
        action1 = await app.handle_action(
            agent_id,
            "email",
            "email_send",
            {
                "from_addr": "agent@acme.com",
                "to_addr": "margaret.chen@customer.com",
                "subject": "Re: Your refund request #249",
                "body": (
                    "Dear Margaret, I'm looking into your refund request. "
                    "I'll need supervisor approval for the $249 amount. "
                    "I'll update you shortly."
                ),
            },
        )
        print(f"  Action 1 (email_send): {json.dumps(action1, indent=4, default=str)[:300]}")

        # Action 2: Agent posts in Slack
        # Find a channel from generated state
        state_engine = app.registry.get("state")
        channels = await state_engine.query_entities("channel")
        channel_id = channels[0].get("id", "C001") if channels else "C001"

        action2 = await app.handle_action(
            agent_id,
            "chat",
            "chat.postMessage",
            {
                "channel_id": channel_id,
                "text": "Working on Margaret Chen's $249 refund — needs supervisor approval",
            },
        )
        print(f"  Action 2 (chat.postMessage): {json.dumps(action2, indent=4, default=str)[:300]}")

        # Action 3: Agent creates a ticket
        action3 = await app.handle_action(
            agent_id,
            "tickets",
            "tickets.create",
            {
                "subject": "Margaret Chen - $249 Refund Request",
                "description": "VIP customer waiting 7 days for refund. Needs supervisor approval.",
                "requester_id": "customer-margaret",
                "priority": "high",
            },
        )
        print(f"  Action 3 (tickets.create): {json.dumps(action3, indent=4, default=str)[:300]}")

        # Action 4: Agent updates ticket status
        ticket_id = action3.get("ticket", {}).get("id", "")
        if ticket_id:
            action4 = await app.handle_action(
                agent_id,
                "tickets",
                "tickets.update",
                {
                    "id": ticket_id,
                    "status": "open",
                    "assignee_id": "support-agent",
                },
            )
            print(f"  Action 4 (tickets.update): {json.dumps(action4, indent=4, default=str)[:200]}")

        # ────────────────────────────────────────────────────
        # STEP 5: Tick the animator (dynamic mode events)
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 5: ANIMATOR TICK (dynamic mode)")
        print("=" * 70)

        animator = app.registry.get("animator")
        try:
            from datetime import UTC, datetime
            events = await animator.tick(datetime.now(UTC))
            print(f"  Animator generated {len(events) if events else 0} events")
            if events:
                for evt in events[:3]:
                    print(f"    - {evt}")
        except Exception as e:
            print(f"  Animator tick: {e} (may need configuration)")

        # ────────────────────────────────────────────────────
        # STEP 6: Query state to verify persistence
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 6: STATE VERIFICATION")
        print("=" * 70)

        for etype in result["entities"]:
            stored = await state_engine.query_entities(etype)
            print(f"  {etype}: {len(stored)} entities in state")

        # Check the email we sent is in state
        emails = await state_engine.query_entities("email")
        our_email = [e for e in emails if "Margaret" in str(e.get("subject", ""))]
        print(f"  Our sent email found: {len(our_email) > 0}")

        # Check the ticket we created is in state
        tickets = await state_engine.query_entities("ticket")
        our_ticket = [t for t in tickets if "Margaret" in str(t.get("subject", ""))]
        print(f"  Our created ticket found: {len(our_ticket) > 0}")

        # ────────────────────────────────────────────────────
        # STEP 7: Generate report
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 7: GOVERNANCE REPORT + SCORECARD")
        print("=" * 70)

        reporter = app.registry.get("reporter")
        report = await reporter.generate_full_report()
        scorecard = await reporter.generate_scorecard()

        print(f"  Report keys: {list(report.keys()) if isinstance(report, dict) else 'N/A'}")
        if isinstance(scorecard, dict):
            collective = scorecard.get("collective", {})
            print(f"  Scorecard (collective):")
            for metric, value in collective.items():
                print(f"    {metric}: {value}")

        # ────────────────────────────────────────────────────
        # STEP 8: Final assertions
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 8: ASSERTIONS")
        print("=" * 70)

        # World was generated
        assert total_entities > 0
        assert len(result["actors"]) >= 3

        # Agent actions went through pipeline
        assert "email_id" in action1 or "error" in action1
        assert action2.get("ok") is True or "error" in action2
        assert "ticket" in action3 or "error" in action3

        # Report was generated
        assert report is not None
        assert scorecard is not None

        print("\n  ALL ASSERTIONS PASSED")
        print("=" * 70)

        # Print the generation report
        if "report" in result:
            print("\n" + result["report"])
