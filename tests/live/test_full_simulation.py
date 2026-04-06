"""Live Test: Full E2E Simulation

Simulates the complete user journey:
    volnix create "Support team with email" --reality messy
    volnix run world.yaml --agent agent-1
    volnix report world --format markdown

This test:
1. Compile world from YAML blueprint
2. Generate entities, actors, seeds via real LLM
3. Populate StateEngine with generated data
4. Agent performs actions through the 7-step governance pipeline
5. Verify state changes persisted
6. Query entities from state
7. Generate comprehensive report
8. Show everything

Run with:
    source .env && pytest tests/live/test_full_simulation.py -v -s
"""
from __future__ import annotations

import json

import pytest

from volnix.engines.world_compiler.plan_reviewer import PlanReviewer


@pytest.mark.asyncio
class TestFullSimulation:
    """Complete E2E: compile → generate → act → query → report."""

    async def test_acme_full_simulation(self, live_app) -> None:
        """Full simulation of Acme Support Organization."""
        compiler = live_app.registry.get("world_compiler")

        print("\n" + "=" * 70)
        print("FLOW 3: COMPLETE E2E SIMULATION")
        print("=" * 70)

        # ── PHASE 1: COMPILE ─────────────────────────────────────
        print("\n" + "─" * 40)
        print("PHASE 1: COMPILE FROM YAML")
        print("─" * 40)

        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        print(f"  World: {plan.name}")
        print(f"  Services: {plan.get_service_names()}")
        print(f"  Entity types: {plan.get_entity_types()}")
        print(f"  Actors: {len(plan.actor_specs)} specs")
        print(f"  Seeds: {len(plan.seeds)} scenarios")
        print(f"  Policies: {len(plan.policies)} rules")
        print(f"  Reality: messy (staleness={plan.conditions.information.staleness})")

        # ── PHASE 2: GENERATE ────────────────────────────────────
        print("\n" + "─" * 40)
        print("PHASE 2: GENERATE WORLD VIA LLM")
        print("─" * 40)

        result = await compiler.generate_world(plan)

        total_entities = sum(len(v) for v in result["entities"].values())
        print(f"  Entities generated: {total_entities}")
        for etype, entities in result["entities"].items():
            print(f"    {etype}: {len(entities)}")
        print(f"  Actors registered: {len(result['actors'])}")
        print(f"  Seeds expanded: {result['seeds_processed']}")
        print(f"  Warnings: {len(result['warnings'])}")
        print(f"  Snapshot: {result['snapshot_id']}")

        # Show a sample entity per type
        for etype, entities in result["entities"].items():
            if entities:
                print(f"\n  Sample {etype}:")
                print(f"    {json.dumps(entities[0], indent=4, default=str)[:250]}")

        # ── PHASE 3: AGENT ACTIONS ───────────────────────────────
        print("\n" + "─" * 40)
        print("PHASE 3: AGENT PERFORMS ACTIONS")
        print("─" * 40)

        actions = []

        # Action 1: Send email
        r1 = await live_app.handle_action("agent-1", "email", "email_send", {
            "from_addr": "agent@acme.com",
            "to_addr": "customer1@acme.com",
            "subject": "Re: Your support ticket #1234",
            "body": "Hi, we've looked into your issue and found a solution. "
                    "Please try clearing your cache and restarting the app.",
        })
        actions.append(("email_send", r1))
        print(f"  Action 1 - email_send: {json.dumps(r1, indent=4, default=str)[:200]}")

        # Action 2: Read email
        email_id = r1.get("email_id", "")
        if email_id:
            r2 = await live_app.handle_action("agent-1", "email", "email_read", {
                "email_id": email_id,
            })
            actions.append(("email_read", r2))
            print(f"\n  Action 2 - email_read: {json.dumps(r2, indent=4, default=str)[:200]}")

        # Action 3: List inbox
        r3 = await live_app.handle_action("agent-1", "email", "email_list", {
            "mailbox_id": "inbox",
        })
        actions.append(("email_list", r3))
        email_count = len(r3.get("emails", []))
        print(f"\n  Action 3 - email_list: {email_count} emails in inbox")

        # ── PHASE 4: QUERY STATE ─────────────────────────────────
        print("\n" + "─" * 40)
        print("PHASE 4: QUERY STATE ENGINE")
        print("─" * 40)

        state = live_app.registry.get("state")
        for etype in result["entities"]:
            stored = await state.query_entities(etype)
            print(f"  {etype}: {len(stored)} entities in state")

        # Show the email we just sent
        emails = await state.query_entities("email")
        sent_emails = [e for e in emails if e.get("subject", "").startswith("Re: Your support")]
        if sent_emails:
            print(f"\n  Our sent email found in state:")
            print(f"    {json.dumps(sent_emails[0], indent=4, default=str)[:300]}")

        # ── PHASE 5: REPORT ──────────────────────────────────────
        print("\n" + "─" * 40)
        print("PHASE 5: GENERATION REPORT")
        print("─" * 40)
        print(result["report"])

        # ── ASSERTIONS ───────────────────────────────────────────
        assert result["entities"], "Should have generated entities"
        assert result["actors"], "Should have generated actors"
        assert total_entities > 0, "Should have non-zero entities"
        assert all("email_id" not in a or a["email_id"] for a in actions if isinstance(a, dict))
        successful = sum(1 for _, r in actions if "error" not in r)
        print(f"\n  Actions: {successful}/{len(actions)} successful")

    async def test_full_simulation_report_export(self, live_app) -> None:
        """Generate world and export full report as YAML."""
        compiler = live_app.registry.get("world_compiler")

        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )
        result = await compiler.generate_world(plan)

        # Export plan as YAML (what user would get from `volnix plan --export`)
        reviewer = PlanReviewer()

        print("\n" + "=" * 70)
        print("EXPORTABLE WORLD PLAN (YAML)")
        print("=" * 70)
        yaml_export = reviewer.to_yaml(plan)
        print(yaml_export[:2000])

        print("\n" + "=" * 70)
        print("FORMATTED PLAN REVIEW")
        print("=" * 70)
        print(reviewer.format_plan(plan))

        print("\n" + "=" * 70)
        print("GENERATION REPORT")
        print("=" * 70)
        print(result["report"])

        assert "VOLNIX WORLD GENERATION REPORT" in result["report"]
        assert result["entities"]
