"""Live Test: Animator with Real LLM (Codex ACP)

Tests the Animator generating REAL organic events via LLM.
Shows how different presets produce different event content.

Run with:
    source .env && pytest tests/live/test_animator_live.py -v -s
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from volnix.engines.animator.context import AnimatorContext


@pytest.mark.asyncio
class TestAnimatorLive:
    """Animator with real LLM — generates narrative events."""

    async def test_live_dynamic_messy_world(self, live_app) -> None:
        """Compile messy world → generate → configure animator → tick with real LLM."""
        compiler = live_app.registry.get("world_compiler")

        # 1. Compile
        plan = await compiler.compile_from_yaml(
            "tests/fixtures/worlds/acme_support.yaml",
            "tests/fixtures/worlds/acme_compiler.yaml",
        )

        # 2. Generate world
        result = await compiler.generate_world(plan)

        # 3. Configure governance + animator
        live_app.configure_governance(plan)
        await live_app.configure_animator(plan)

        print(f"\n{'=' * 70}")
        print("LIVE ANIMATOR: Dynamic Messy World")
        print(f"{'=' * 70}")
        print(f"  World: {plan.name}")
        print(f"  Behavior: {plan.behavior}")
        print("  Reality: messy")
        print(f"  Entities: {sum(len(v) for v in result['entities'].values())}")
        print(f"  Actors: {len(result['actors'])}")

        # 4. Show probabilities
        ctx = AnimatorContext(plan)
        print("\n  Probabilities per tick:")
        print(f"    reliability.failures  = {ctx.get_probability('reliability', 'failures'):.0%}")
        print(f"    reliability.timeouts  = {ctx.get_probability('reliability', 'timeouts'):.0%}")
        print(f"    complexity.volatility = {ctx.get_probability('complexity', 'volatility'):.0%}")
        print(
            f"    boundaries.gaps       = {ctx.get_probability('boundaries', 'boundary_gaps'):.0%}"
        )

        # 5. Run 3 ticks
        animator = live_app.registry.get("animator")
        now = datetime.now(UTC)

        print("\n  Running 3 animator ticks...")
        for tick in range(3):
            tick_time = now + timedelta(minutes=tick)
            results = await animator.tick(tick_time)
            print(f"\n  Tick {tick + 1}: {len(results)} events")
            for i, evt in enumerate(results):
                if isinstance(evt, dict):
                    evt.get("action", evt.get("error", "?"))
                    print(f"    Event {i + 1}: {json.dumps(evt, default=str)[:150]}")

        # 6. Check ledger
        from volnix.ledger.query import LedgerQuery

        entries = await live_app.ledger.query(LedgerQuery(limit=500))
        by_type = {}
        for e in entries:
            by_type[e.entry_type] = by_type.get(e.entry_type, 0) + 1

        print(f"\n  Ledger: {len(entries)} entries")
        for etype, count in sorted(by_type.items()):
            print(f"    {etype}: {count}")

        assert result["entities"], "World should have entities"
