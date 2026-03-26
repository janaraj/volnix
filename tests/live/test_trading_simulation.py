"""Live E2E test: Trading world with Alpaca-style brokerage simulation.

Creates a trading world where:
- A portfolio of stocks (AAPL, NVDA, TSLA) with realistic quotes and bars
- News articles and social sentiment affect the market
- A trading agent places orders, monitors positions, reads news
- Animator generates price updates, breaking news, sentiment shifts

Requires: codex-acp binary available (uses terrarium.toml routing)

Run with:
    uv run pytest tests/live/test_trading_simulation.py -v -s
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta

import pytest

from terrarium.core.types import RunId


@pytest.fixture
async def trading_app(tmp_path):
    """TerrariumApp with codex-acp for trading simulation."""
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


class TestTradingSimulation:
    """Full lifecycle: compile → generate → trade → animate → report."""

    @pytest.mark.asyncio
    async def test_trading_full_lifecycle(self, trading_app) -> None:
        """E2E simulation of a trading agent managing a portfolio."""
        app = trading_app
        compiler = app.registry.get("world_compiler")

        # ────────────────────────────────────────────────────
        # STEP 1: Build world plan with Trading pack
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 1: BUILD TRADING WORLD PLAN")
        print("=" * 70)

        from terrarium.engines.world_compiler.plan import (
            ServiceResolution,
            WorldPlan,
        )
        from terrarium.kernel.surface import ServiceSurface
        from terrarium.packs.verified.trading.pack import TradingPack
        from terrarium.reality.presets import load_preset

        trading_surface = ServiceSurface.from_pack(TradingPack())

        plan = WorldPlan(
            name="Acme Capital Trading Desk",
            description=(
                "A quantitative trading desk at Acme Capital. The team "
                "trades US equities (AAPL, NVDA, TSLA, MSFT, AMZN) using "
                "a mix of fundamental and momentum strategies. NVDA just "
                "reported strong Q4 earnings. There are rumors about AAPL "
                "missing next quarter. TSLA is volatile after a product "
                "announcement. The desk has a $100,000 portfolio."
            ),
            seed=42,
            behavior="dynamic",
            mode="governed",
            services={
                "trading": ServiceResolution(
                    service_name="trading",
                    spec_reference="verified/trading",
                    surface=trading_surface,
                    resolution_source="tier1_pack",
                ),
            },
            actor_specs=[
                {
                    "role": "portfolio-manager",
                    "type": "external",
                    "count": 1,
                    "personality": (
                        "Disciplined quantitative trader. Uses fundamental "
                        "analysis and momentum signals. Risk-aware."
                    ),
                },
                {
                    "role": "market-maker",
                    "type": "internal",
                    "count": 1,
                    "personality": (
                        "Provides liquidity. Adjusts quotes based on "
                        "order flow and news."
                    ),
                },
            ],
            conditions=load_preset("messy"),
            reality_prompt_context={},
            policies=[
                {
                    "name": "Position concentration limit",
                    "description": (
                        "No single position may exceed 30% of portfolio value"
                    ),
                    "trigger": "position exceeds concentration threshold",
                    "enforcement": "log",
                },
                {
                    "name": "Daily loss limit",
                    "description": "Stop trading if daily loss exceeds 5%",
                    "trigger": "portfolio drawdown exceeds 5%",
                    "enforcement": "hold",
                },
            ],
            seeds=[
                (
                    "NVDA just beat Q4 earnings estimates — revenue up 40% "
                    "YoY. Stock gapped up 12% after hours."
                ),
                (
                    "Unverified social media rumor: AAPL will miss next "
                    "quarter's earnings. Sentiment turning negative."
                ),
                (
                    "TSLA announced a new product line. Stock is volatile "
                    "with high trading volume."
                ),
            ],
            mission=(
                "Manage the portfolio to maximize risk-adjusted returns. "
                "React to earnings, news, and sentiment signals. "
                "Stay within position limits and loss thresholds."
            ),
        )

        print(f"  World: {plan.name}")
        print(f"  Services: {list(plan.services.keys())}")
        print(f"  Behavior: {plan.behavior}")
        print(f"  Mode: {plan.mode}")
        print(f"  Seeds: {len(plan.seeds)} scenarios")

        # ────────────────────────────────────────────────────
        # STEP 2: Generate world with REAL LLM
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 2: GENERATE WORLD (codex-acp)")
        print("=" * 70)

        result = await compiler.generate_world(plan)

        entity_summary = {
            etype: len(elist) for etype, elist in result["entities"].items()
        }
        total_entities = sum(entity_summary.values())
        print(f"  Generated entities: {json.dumps(entity_summary, indent=4)}")
        print(f"  Total: {total_entities} entities")
        print(f"  Actors: {len(result['actors'])}")

        assert total_entities > 0, "No entities generated"

        # Show sample entities
        for etype, elist in result["entities"].items():
            if elist:
                sample = elist[0]
                fields = list(sample.keys())[:6]
                print(
                    f"\n  Sample {etype}: "
                    f"{json.dumps({k: sample.get(k) for k in fields}, default=str)}"
                )

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
        # STEP 4: Agent trading actions
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 4: AGENT TRADING ACTIONS")
        print("=" * 70)

        actors = result["actors"]
        agent_actor = next(
            (a for a in actors if a.role == "portfolio-manager"),
            actors[0],
        )
        agent_id = str(agent_actor.id)
        print(f"  Using actor: {agent_id} (role={agent_actor.role})")

        state_engine = app.registry.get("state")

        # 4a: Check account
        print("\n  4a. Checking account...")
        r_account = await app.handle_action(
            agent_id, "trading", "alpaca_get_account", {},
        )
        print(f"      Account: {json.dumps(r_account, default=str)[:300]}")

        # 4b: List available assets
        print("\n  4b. Listing assets...")
        r_assets = await app.handle_action(
            agent_id, "trading", "alpaca_list_assets", {},
        )
        assets_data = r_assets.get("assets", r_assets)
        asset_count = len(assets_data) if isinstance(assets_data, list) else 0
        print(f"      Assets available: {asset_count}")

        # 4c: Get market data — latest quote
        quotes = await state_engine.query_entities("alpaca_quote")
        if quotes:
            first_symbol = quotes[0].get("symbol", "AAPL")
            print(f"\n  4c. Getting latest quote for {first_symbol}...")
            r_quote = await app.handle_action(
                agent_id, "trading", "alpaca_get_latest_quote",
                {"symbol": first_symbol},
            )
            print(f"      Quote: {json.dumps(r_quote, default=str)[:200]}")

        # 4d: Get historical bars
        if quotes:
            print(f"\n  4d. Getting bars for {first_symbol}...")
            r_bars = await app.handle_action(
                agent_id, "trading", "alpaca_get_bars",
                {"symbol": first_symbol, "limit": 5},
            )
            bar_count = len(r_bars.get("bars", []))
            print(f"      Bars returned: {bar_count}")

        # 4e: Place a market buy order
        if quotes:
            print(f"\n  4e. Placing market buy for {first_symbol}...")
            r_order = await app.handle_action(
                agent_id, "trading", "alpaca_create_order",
                {
                    "symbol": first_symbol,
                    "qty": "10",
                    "side": "buy",
                    "type": "market",
                    "time_in_force": "day",
                },
            )
            order_status = r_order.get("status", "unknown")
            print(f"      Order status: {order_status}")
            print(f"      Response: {json.dumps(r_order, default=str)[:300]}")

        # 4f: Check positions
        print("\n  4f. Checking positions...")
        r_positions = await app.handle_action(
            agent_id, "trading", "alpaca_list_positions", {},
        )
        positions_data = r_positions.get("positions", r_positions)
        pos_count = len(positions_data) if isinstance(positions_data, list) else 0
        print(f"      Open positions: {pos_count}")
        if isinstance(positions_data, list):
            for p in positions_data[:3]:
                print(
                    f"        {p.get('symbol')}: "
                    f"{p.get('qty')} shares @ "
                    f"${p.get('avg_entry_price', 0):.2f}"
                )

        # 4g: Get market clock
        print("\n  4g. Market clock...")
        r_clock = await app.handle_action(
            agent_id, "trading", "alpaca_get_clock", {},
        )
        print(f"      Clock: {json.dumps(r_clock, default=str)[:150]}")

        # 4h: Read news
        print("\n  4h. Reading news...")
        r_news = await app.handle_action(
            agent_id, "trading", "alpaca_get_news", {"limit": 3},
        )
        news_items = r_news.get("news", [])
        print(f"      News articles: {len(news_items)}")
        for n in news_items[:3]:
            print(f"        [{n.get('source', '?')}] {n.get('headline', '?')[:60]}")
            # Verify internal fields are stripped
            assert "factual_accuracy" not in n, "Internal field leaked to agent!"

        # 4i: Check social sentiment
        print("\n  4i. Social sentiment...")
        sentiments = await state_engine.query_entities("social_sentiment")
        if sentiments:
            sym = sentiments[0].get("symbol", "NVDA")
            r_sent = await app.handle_action(
                agent_id, "trading", "social_get_sentiment",
                {"symbol": sym},
            )
            print(f"      {sym} sentiment: {r_sent.get('score', 'N/A')}")

        # 4j: Check trending
        print("\n  4j. Trending symbols...")
        r_trending = await app.handle_action(
            agent_id, "trading", "social_get_trending", {"limit": 5},
        )
        trending = r_trending.get("trending", [])
        print(f"      Trending: {[t.get('symbol') for t in trending[:5]]}")

        # ────────────────────────────────────────────────────
        # STEP 5: Animator ticks (dynamic mode)
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 5: ANIMATOR TICKS (dynamic mode)")
        print("=" * 70)

        animator = app.registry.get("animator")
        now = datetime.now(UTC)

        for tick in range(3):
            tick_time = now + timedelta(minutes=tick * 5)
            results = await animator.tick(tick_time)
            print(f"\n  Tick {tick + 1}: {len(results)} events generated")
            for evt in results[:3]:
                print(f"    → {json.dumps(evt, default=str)[:150]}")

        # ────────────────────────────────────────────────────
        # STEP 6: Close position
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 6: CLOSE POSITION")
        print("=" * 70)

        positions = await state_engine.query_entities("alpaca_position")
        if positions:
            close_symbol = positions[0].get("symbol", "")
            print(f"  Closing position: {close_symbol}...")
            r_close = await app.handle_action(
                agent_id, "trading", "alpaca_close_position",
                {"symbol": close_symbol},
            )
            close_status = r_close.get("status", "unknown")
            print(f"  Close order status: {close_status}")
            print(f"  Response: {json.dumps(r_close, default=str)[:200]}")

        # ────────────────────────────────────────────────────
        # STEP 7: Final state
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 7: FINAL STATE")
        print("=" * 70)

        for etype in [
            "alpaca_account", "alpaca_order", "alpaca_position",
            "alpaca_asset", "alpaca_bar", "alpaca_quote",
            "alpaca_clock", "alpaca_news", "alpaca_activity",
            "social_sentiment",
        ]:
            entities = await state_engine.query_entities(etype)
            print(f"  {etype}: {len(entities)} entities")

        # ────────────────────────────────────────────────────
        # STEP 8: Report
        # ────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("STEP 8: GOVERNANCE REPORT")
        print("=" * 70)

        reporter = app.registry.get("reporter")
        if reporter:
            try:
                scorecard = await reporter.compute_scorecard(
                    await state_engine.get_event_log(),
                    plan,
                )
                print(
                    f"  Scorecard: "
                    f"{json.dumps(scorecard, indent=4, default=str)[:500]}"
                )
            except (AttributeError, Exception) as exc:
                print(f"  Scorecard: skipped ({exc})")

        # ── ASSERTIONS ──────────────────────────────────────
        print("\n" + "=" * 70)
        print("ASSERTIONS")
        print("=" * 70)

        assert total_entities > 0, "World should have entities"
        print("  ✅ All assertions passed")
        print(f"  Total entities generated: {total_entities}")
