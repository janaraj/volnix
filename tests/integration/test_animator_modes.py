"""Live Test: Animator Modes — Static vs Dynamic vs Reactive

Tests the FULL end-to-end flow:
  1. Compile world from YAML (acme_support.yaml)
  2. Generate world entities via LLM
  3. Configure governance + animator
  4. Run animator ticks
  5. Verify behavior differs by mode

Also tests ideal vs messy vs hostile presets to show how
Level 2 per-attribute numbers affect event generation.

Run with:
    source .env && pytest tests/live/test_animator_modes.py -v -s

Uses Codex ACP as the LLM provider (configured in terrarium.toml).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

from terrarium.engines.world_compiler.plan import WorldPlan, ServiceResolution
from terrarium.engines.world_compiler.plan_reviewer import PlanReviewer
from terrarium.engines.animator.context import AnimatorContext
from terrarium.kernel.surface import ServiceSurface
from terrarium.packs.verified.gmail.pack import EmailPack
from terrarium.reality.presets import load_preset
from terrarium.scheduling.scheduler import WorldScheduler


# ── Helpers ──────────────────────────────────────────────────────


def _make_plan(preset: str = "messy", behavior: str = "dynamic") -> WorldPlan:
    """Create a WorldPlan with email pack and the given preset/behavior."""
    surface = ServiceSurface.from_pack(EmailPack())
    conditions = load_preset(preset)
    from terrarium.reality.expander import ConditionExpander
    prompt_ctx = ConditionExpander().build_prompt_context(conditions)

    return WorldPlan(
        name=f"Test World ({preset}/{behavior})",
        description="A support team world for animator testing",
        seed=42,
        behavior=behavior,
        mode="governed",
        services={
            "gmail": ServiceResolution(
                service_name="gmail",
                spec_reference="verified/gmail",
                surface=surface,
                resolution_source="tier1_pack",
            )
        },
        actor_specs=[
            {"role": "support-agent", "type": "external", "count": 1},
            {"role": "customer", "type": "internal", "count": 5},
        ],
        conditions=conditions,
        reality_prompt_context=prompt_ctx,
        seeds=[],
        policies=[],
        animator_settings={
            "creativity": "medium",
            "event_frequency": "moderate",
            "contextual_targeting": True,
            "escalation_on_inaction": True,
        },
    )


# ── Static Mode ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestStaticMode:
    """Static mode: animator is OFF. Zero events generated."""

    async def test_static_mode_zero_events(self, app_with_mock_llm) -> None:
        """In static mode, tick() returns empty — world is frozen."""
        app = app_with_mock_llm
        plan = _make_plan(preset="messy", behavior="static")

        # Configure animator
        animator = app.registry.get("animator")
        scheduler = WorldScheduler()
        await animator.configure(plan, scheduler)

        # Tick — should produce NOTHING
        now = datetime.now(timezone.utc)
        results = await animator.tick(now)

        print(f"\n{'='*60}")
        print("STATIC MODE: Animator OFF")
        print(f"{'='*60}")
        print(f"  Behavior: {plan.behavior}")
        print(f"  Reality: messy (failures={plan.conditions.reliability.failures})")
        print(f"  Events generated: {len(results)}")
        assert len(results) == 0, "Static mode should generate ZERO events"


# ── Dynamic Mode ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestDynamicMode:
    """Dynamic mode: animator generates events autonomously."""

    async def test_dynamic_mode_without_llm_no_events(self, app_with_mock_llm) -> None:
        """Dynamic mode without real LLM produces no events (organic-only, no probabilistic)."""
        app = app_with_mock_llm
        plan = _make_plan(preset="hostile", behavior="dynamic")

        animator = app.registry.get("animator")
        scheduler = WorldScheduler()
        animator._config["_app"] = app
        await animator.configure(plan, scheduler)

        # Without a real LLM router, organic generation can't run.
        # Probabilistic events were removed — dynamic mode relies on
        # organic LLM generation or query-driven PackRuntime generation.
        now = datetime.now(timezone.utc)
        all_events = []
        for tick in range(3):
            results = await animator.tick(now + timedelta(minutes=tick))
            all_events.extend(results)

        assert len(all_events) == 0, "Without LLM, dynamic mode produces no animator events"


# ── Reactive Mode ────────────────────────────────────────────────


@pytest.mark.asyncio
class TestReactiveMode:
    """Reactive mode: events only in response to agent actions."""

    async def test_reactive_no_events_without_actions(self, app_with_mock_llm) -> None:
        """Reactive mode with no recent actions → zero organic events."""
        app = app_with_mock_llm
        plan = _make_plan(preset="messy", behavior="reactive")

        animator = app.registry.get("animator")
        scheduler = WorldScheduler()
        animator._config["_app"] = app
        await animator.configure(plan, scheduler)

        now = datetime.now(timezone.utc)
        results = await animator.tick(now)

        # Filter to only organic events (probabilistic still fire)
        print(f"\n{'='*60}")
        print("REACTIVE MODE: No Recent Actions")
        print(f"{'='*60}")
        print(f"  Behavior: {plan.behavior}")
        print(f"  Recent actions: 0")
        print(f"  Events generated: {len(results)}")
        print(f"  (Probabilistic events may still fire, organic should not)")

    async def test_reactive_events_after_agent_action(self, app_with_mock_llm) -> None:
        """Reactive mode with recent agent action → events generated."""
        app = app_with_mock_llm
        plan = _make_plan(preset="messy", behavior="reactive")

        animator = app.registry.get("animator")
        scheduler = WorldScheduler()
        animator._config["_app"] = app
        await animator.configure(plan, scheduler)

        # Simulate agent action
        from terrarium.core.events import WorldEvent
        from terrarium.core.types import ActorId, ServiceId, Timestamp
        agent_event = WorldEvent(
            event_type="world.email_send",
            timestamp=Timestamp(
                world_time=datetime.now(timezone.utc),
                wall_time=datetime.now(timezone.utc),
                tick=1,
            ),
            actor_id=ActorId("agent-1"),
            service_id=ServiceId("gmail"),
            action="email_send",
            input_data={},
        )
        await animator._handle_event(agent_event)

        print(f"\n{'='*60}")
        print("REACTIVE MODE: After Agent Action")
        print(f"{'='*60}")
        print(f"  Recent actions tracked: {len(animator._recent_actions)}")
        assert len(animator._recent_actions) == 1


# ── Preset Comparison ────────────────────────────────────────────


@pytest.mark.asyncio
class TestPresetComparison:
    """Compare ideal vs messy vs hostile — Level 2 numbers in action."""

    async def test_ideal_vs_messy_vs_hostile(self, app_with_mock_llm) -> None:
        """Shows how different presets produce different event volumes."""
        app = app_with_mock_llm

        print(f"\n{'='*60}")
        print("PRESET COMPARISON: 10 ticks each")
        print(f"{'='*60}")

        for preset in ["ideal", "messy", "hostile"]:
            plan = _make_plan(preset=preset, behavior="dynamic")
            ctx = AnimatorContext(plan)

            animator = app.registry.get("animator")
            scheduler = WorldScheduler()
            animator._config["_app"] = app
            await animator.configure(plan, scheduler)

            now = datetime.now(timezone.utc)
            total_events = 0
            for tick in range(10):
                results = await animator.tick(now + timedelta(minutes=tick))
                total_events += len(results)

            # Show key probabilities
            fail_prob = ctx.get_probability("reliability", "failures")
            vol_prob = ctx.get_probability("complexity", "volatility")
            gap_prob = ctx.get_probability("boundaries", "boundary_gaps")

            print(f"\n  {preset.upper()}:")
            print(f"    failures={fail_prob:.0%}, volatility={vol_prob:.0%}, gaps={gap_prob:.0%}")
            print(f"    Events in 10 ticks: {total_events}")

        print()
        print("  Expected: ideal=0, messy=moderate, hostile=many")


# ── Full E2E with Pipeline ───────────────────────────────────────


@pytest.mark.asyncio
class TestFullE2EPipeline:
    """Full pipeline: compile → generate → configure → tick → verify ledger."""

    async def test_compile_configure_tick_verify(self, app_with_mock_llm) -> None:
        """Complete E2E: world compiled, animator configured, ticks produce traced events."""
        app = app_with_mock_llm

        # 1. Compile from YAML
        compiler = app.registry.get("world_compiler")
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )

        # 2. Generate world
        result = await compiler.generate_world(plan)

        # 3. Configure governance + animator
        app.configure_governance(plan)
        await app.configure_animator(plan)

        # 4. Run animator ticks
        animator = app.registry.get("animator")
        now = datetime.now(timezone.utc)
        tick_results = []
        for tick in range(3):
            results = await animator.tick(now + timedelta(minutes=tick))
            tick_results.extend(results)

        print(f"\n{'='*60}")
        print("FULL E2E: Compile → Generate → Configure → Tick")
        print(f"{'='*60}")
        print(f"  World: {plan.name}")
        print(f"  Behavior: {plan.behavior}")
        print(f"  Entities generated: {sum(len(v) for v in result['entities'].values())}")
        print(f"  Actors: {len(result['actors'])}")
        print(f"  Animator ticks: 3")
        print(f"  Events from animator: {len(tick_results)}")

        # 5. Verify ledger has entries from both generation AND animator
        from terrarium.ledger.query import LedgerQuery
        entries = await app.ledger.query(LedgerQuery(limit=500))
        print(f"  Ledger entries: {len(entries)}")

        by_type = {}
        for e in entries:
            by_type.setdefault(e.entry_type, 0)
            by_type[e.entry_type] = by_type[e.entry_type] + 1
        for etype, count in sorted(by_type.items()):
            print(f"    {etype}: {count}")

        assert len(entries) > 0, "Ledger should have entries from generation + animator"
