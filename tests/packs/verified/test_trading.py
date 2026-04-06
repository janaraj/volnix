"""Tests for volnix.packs.verified.alpaca -- TradingPack through pack's own handle_action."""

from __future__ import annotations

import pytest

from volnix.core.context import ResponseProposal
from volnix.core.types import ToolName
from volnix.packs.base import ServicePack
from volnix.packs.verified.alpaca.handlers import (
    SLIPPAGE_BPS,
    _compute_fill_price,
)
from volnix.packs.verified.alpaca.pack import TradingPack
from volnix.packs.verified.alpaca.state_machines import (
    ORDER_TRANSITIONS,
)


@pytest.fixture
def pack():
    return TradingPack()


@pytest.fixture
def sample_state():
    """Rich state dict covering all 10 entity types for trading pack tests."""
    return {
        "alpaca_accounts": [
            {
                "id": "acc_test_001",
                "status": "ACTIVE",
                "currency": "USD",
                "buying_power": 200000.00,
                "cash": 100000.00,
                "portfolio_value": 115000.00,
                "equity": 115000.00,
                "last_equity": 112000.00,
                "long_market_value": 15000.00,
                "short_market_value": 0,
                "initial_margin": 7500.00,
                "maintenance_margin": 4500.00,
                "daytrade_count": 0,
                "pattern_day_trader": False,
                "trading_blocked": False,
                "transfers_blocked": False,
                "account_blocked": False,
            },
        ],
        "alpaca_assets": [
            {
                "id": "asset_aapl",
                "symbol": "AAPL",
                "name": "Apple Inc",
                "exchange": "NASDAQ",
                "asset_class": "us_equity",
                "tradable": True,
                "status": "active",
            },
            {
                "id": "asset_nvda",
                "symbol": "NVDA",
                "name": "NVIDIA Corp",
                "exchange": "NASDAQ",
                "asset_class": "us_equity",
                "tradable": True,
                "status": "active",
            },
            {
                "id": "asset_tsla",
                "symbol": "TSLA",
                "name": "Tesla Inc",
                "exchange": "NASDAQ",
                "asset_class": "us_equity",
                "tradable": True,
                "status": "active",
            },
            {
                "id": "asset_halt",
                "symbol": "HALT",
                "name": "Halted Corp",
                "exchange": "NYSE",
                "asset_class": "us_equity",
                "tradable": False,
                "status": "inactive",
            },
        ],
        "alpaca_orders": [
            {
                "id": "ord_filled",
                "symbol": "AAPL",
                "qty": 100,
                "side": "buy",
                "type": "market",
                "status": "filled",
                "filled_qty": 100,
                "filled_avg_price": 150.00,
                "created_at": "2026-03-24T10:00:00Z",
                "time_in_force": "day",
                "order_class": "simple",
            },
            {
                "id": "ord_open",
                "symbol": "NVDA",
                "qty": 50,
                "side": "buy",
                "type": "limit",
                "status": "accepted",
                "filled_qty": 0,
                "limit_price": 130.00,
                "created_at": "2026-03-24T11:00:00Z",
                "time_in_force": "gtc",
                "order_class": "simple",
            },
        ],
        "alpaca_positions": [
            {
                "id": "pos_aapl",
                "asset_id": "asset_aapl",
                "symbol": "AAPL",
                "exchange": "NASDAQ",
                "asset_class": "us_equity",
                "avg_entry_price": 150.00,
                "qty": 100,
                "side": "long",
                "market_value": 15200.00,
                "cost_basis": 15000.00,
                "unrealized_pl": 200.00,
                "unrealized_plpc": 0.0133,
                "current_price": 152.00,
                "lastday_price": 150.50,
                "change_today": 0.01,
            },
        ],
        "alpaca_quotes": [
            {
                "id": "q_aapl",
                "symbol": "AAPL",
                "timestamp": "2026-03-24T14:30:00Z",
                "bid_price": 151.95,
                "bid_size": 200,
                "bid_exchange": "Q",
                "ask_price": 152.05,
                "ask_size": 300,
                "ask_exchange": "V",
                "conditions": ["R"],
            },
            {
                "id": "q_nvda",
                "symbol": "NVDA",
                "timestamp": "2026-03-24T14:30:00Z",
                "bid_price": 142.45,
                "bid_size": 200,
                "bid_exchange": "Q",
                "ask_price": 142.55,
                "ask_size": 300,
                "ask_exchange": "V",
                "conditions": ["R"],
            },
            {
                "id": "q_tsla",
                "symbol": "TSLA",
                "timestamp": "2026-03-24T14:30:00Z",
                "bid_price": 247.80,
                "bid_size": 150,
                "bid_exchange": "Q",
                "ask_price": 248.20,
                "ask_size": 250,
                "ask_exchange": "V",
                "conditions": ["R"],
            },
        ],
        "alpaca_bars": [
            {
                "id": "bar_aapl_1",
                "symbol": "AAPL",
                "timestamp": "2026-03-24T14:00:00Z",
                "open": 151.50,
                "high": 152.30,
                "low": 151.20,
                "close": 152.00,
                "volume": 1234567,
                "trade_count": 8923,
                "vwap": 151.85,
                "timeframe": "1Hour",
            },
            {
                "id": "bar_aapl_2",
                "symbol": "AAPL",
                "timestamp": "2026-03-24T13:00:00Z",
                "open": 150.80,
                "high": 151.60,
                "low": 150.50,
                "close": 151.50,
                "volume": 987654,
                "trade_count": 6543,
                "vwap": 151.10,
                "timeframe": "1Hour",
            },
            {
                "id": "bar_nvda_1",
                "symbol": "NVDA",
                "timestamp": "2026-03-24T14:00:00Z",
                "open": 141.20,
                "high": 142.80,
                "low": 140.95,
                "close": 142.50,
                "volume": 2345678,
                "trade_count": 12345,
                "vwap": 141.85,
                "timeframe": "1Hour",
            },
        ],
        "alpaca_clocks": [
            {
                "id": "clock_001",
                "timestamp": "2026-03-24T14:30:00Z",
                "is_open": True,
                "next_open": "2026-03-25T09:30:00Z",
                "next_close": "2026-03-24T16:00:00Z",
            },
        ],
        # Handler reads from "alpaca_newses" (pluralized by Responder._pluralize)
        "alpaca_newses": [
            {
                "id": "news_001",
                "headline": "NVDA Beats Q4 Estimates",
                "author": "Reuters",
                "created_at": "2026-03-24T16:05:00Z",
                "summary": "NVIDIA reported quarterly earnings above expectations.",
                "url": "https://volnix.sim/news/001",
                "symbols": ["NVDA"],
                "source": "reuters",
                "factual_accuracy": 0.95,
                "sentiment_bias": 0.8,
                "market_impact_expected": 0.12,
            },
            {
                "id": "news_002",
                "headline": "AAPL Insider: Missing Earnings",
                "author": "SocialPost",
                "created_at": "2026-03-24T09:30:00Z",
                "summary": "Unverified social post claims Apple will miss.",
                "url": "https://volnix.sim/news/002",
                "symbols": ["AAPL"],
                "source": "social",
                "factual_accuracy": 0.1,
                "sentiment_bias": -0.9,
                "market_impact_expected": -0.04,
            },
        ],
        "alpaca_activitys": [
            {
                "id": "act_001",
                "activity_type": "FILL",
                "date": "2026-03-24T10:00:00Z",
                "qty": 100,
                "price": 150.00,
                "symbol": "AAPL",
                "side": "buy",
                "order_id": "ord_filled",
            },
        ],
        "social_sentiments": [
            {
                "id": "sent_nvda",
                "symbol": "NVDA",
                "source": "all",
                "window": "24h",
                "score": 0.72,
                "post_count": 145,
                "positive_count": 98,
                "negative_count": 20,
                "neutral_count": 27,
                "trending_rank": 1,
                "computed_at": "2026-03-24T14:00:00Z",
            },
            {
                "id": "sent_aapl",
                "symbol": "AAPL",
                "source": "all",
                "window": "24h",
                "score": -0.35,
                "post_count": 89,
                "positive_count": 22,
                "negative_count": 45,
                "neutral_count": 22,
                "trending_rank": 3,
                "computed_at": "2026-03-24T14:00:00Z",
            },
            {
                "id": "sent_tsla_reddit",
                "symbol": "TSLA",
                "source": "reddit",
                "window": "24h",
                "score": 0.15,
                "post_count": 67,
                "positive_count": 30,
                "negative_count": 25,
                "neutral_count": 12,
                "trending_rank": 2,
                "computed_at": "2026-03-24T14:00:00Z",
            },
        ],
    }


# =========================================================================
# Pack metadata (5)
# =========================================================================


class TestTradingPackMetadata:
    def test_pack_name_and_category(self, pack):
        """Pack identifies as trading/trading with fidelity_tier 1."""
        assert pack.pack_name == "alpaca"
        assert pack.category == "trading"
        assert pack.fidelity_tier == 1

    def test_tool_count(self, pack):
        """Pack exposes exactly 22 tools (18 agent + 4 Animator)."""
        tools = pack.get_tools()
        assert len(tools) == 22

    def test_all_tool_names_present(self, pack):
        """Every handler key in _handlers has a matching tool definition."""
        handler_names = set(pack._handlers.keys())
        tool_names = {t.get("name", "") for t in pack.get_tools()}
        assert handler_names == tool_names

    def test_entity_schema_count(self, pack):
        """Pack defines exactly 10 entity schemas."""
        schemas = pack.get_entity_schemas()
        assert len(schemas) == 10

    def test_state_machine_count(self, pack):
        """Pack defines exactly 2 state machines (order + asset)."""
        machines = pack.get_state_machines()
        assert len(machines) == 2
        assert "alpaca_order" in machines
        assert "alpaca_asset" in machines


# =========================================================================
# Order lifecycle (8)
# =========================================================================


class TestOrderLifecycle:
    async def test_market_buy_fills_immediately(self, pack, sample_state):
        """Market buy creates order + position + account update + activity (4 deltas)."""
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "NVDA",
                "qty": "10",
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            },
            sample_state,
        )
        assert isinstance(result, ResponseProposal)
        body = result.response_body
        assert body["status"] == "filled"
        assert body["symbol"] == "NVDA"
        assert body["qty"] == 10.0

        # 4 deltas: order, position, account, activity
        deltas = result.proposed_state_deltas
        assert len(deltas) == 4

        order_delta = deltas[0]
        assert order_delta.entity_type == "alpaca_order"
        assert order_delta.operation == "create"
        assert order_delta.fields["status"] == "filled"

        pos_delta = deltas[1]
        assert pos_delta.entity_type == "alpaca_position"
        assert pos_delta.operation == "create"
        assert pos_delta.fields["qty"] == 10.0
        assert pos_delta.fields["symbol"] == "NVDA"

        acct_delta = deltas[2]
        assert acct_delta.entity_type == "alpaca_account"
        assert acct_delta.operation == "update"
        # buying_power should have decreased
        assert acct_delta.fields["buying_power"] < 200000.00

        activity_delta = deltas[3]
        assert activity_delta.entity_type == "alpaca_activity"
        assert activity_delta.operation == "create"
        assert activity_delta.fields["activity_type"] == "FILL"

    async def test_market_sell_existing_position(self, pack, sample_state):
        """Market sell AAPL with existing position increases cash."""
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "AAPL",
                "qty": "10",
                "side": "sell",
                "type": "market",
                "time_in_force": "day",
            },
            sample_state,
        )
        body = result.response_body
        assert body["status"] == "filled"
        assert body["side"] == "sell"

        acct_deltas = [d for d in result.proposed_state_deltas if d.entity_type == "alpaca_account"]
        assert len(acct_deltas) == 1
        # Cash should increase on sell
        assert acct_deltas[0].fields["cash"] > 100000.00

    async def test_limit_buy_fills_when_ask_below_limit(self, pack, sample_state):
        """Limit buy with limit_price > ask fills at ask price."""
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "AAPL",
                "qty": "10",
                "side": "buy",
                "type": "limit",
                "time_in_force": "day",
                "limit_price": 160.00,  # ask is 152.05, so fills
            },
            sample_state,
        )
        body = result.response_body
        assert body["status"] == "filled"
        # Fill at min(ask, limit) = ask = 152.05
        assert body["filled_avg_price"] == 152.05

    async def test_limit_buy_no_fill_when_ask_above_limit(self, pack, sample_state):
        """Limit buy with limit_price < ask does not fill."""
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "AAPL",
                "qty": "10",
                "side": "buy",
                "type": "limit",
                "time_in_force": "gtc",
                "limit_price": 140.00,  # ask is 152.05, no fill
            },
            sample_state,
        )
        body = result.response_body
        assert body["status"] == "accepted"
        assert body["filled_avg_price"] is None
        # Only 1 delta: order create (no position, account, or activity)
        assert len(result.proposed_state_deltas) == 1
        assert result.proposed_state_deltas[0].entity_type == "alpaca_order"

    async def test_cancel_accepted_order(self, pack, sample_state):
        """Cancelling an accepted order sets status to cancelled."""
        result = await pack.handle_action(
            ToolName("cancel_order"),
            {"id": "ord_open"},
            sample_state,
        )
        assert result.response_body == {}
        deltas = result.proposed_state_deltas
        assert len(deltas) == 1
        assert deltas[0].entity_type == "alpaca_order"
        assert deltas[0].operation == "update"
        assert deltas[0].fields["status"] == "cancelled"
        assert deltas[0].previous_fields["status"] == "accepted"

    async def test_stop_buy_triggers(self, pack, sample_state):
        """Stop buy triggers when ask >= stop_price."""
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "NVDA",
                "qty": "10",
                "side": "buy",
                "type": "stop",
                "time_in_force": "day",
                "stop_price": 142.00,  # ask=142.55 >= stop=142 => triggers
            },
            sample_state,
        )
        body = result.response_body
        assert body["status"] == "filled"
        # Fills as market (ask * (1 + slippage))
        expected = round(142.55 * (1 + SLIPPAGE_BPS / 10000), 4)
        assert body["filled_avg_price"] == expected

    async def test_stop_buy_no_trigger(self, pack, sample_state):
        """Stop buy does not trigger when ask < stop_price."""
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "NVDA",
                "qty": "10",
                "side": "buy",
                "type": "stop",
                "time_in_force": "day",
                "stop_price": 150.00,  # ask=142.55 < stop=150 => no trigger
            },
            sample_state,
        )
        body = result.response_body
        assert body["status"] == "accepted"
        assert body["filled_avg_price"] is None

    async def test_stop_limit_triggers_then_limit_fills(self, pack, sample_state):
        """Stop-limit triggers on stop, then fills at limit when ask <= limit."""
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "NVDA",
                "qty": "5",
                "side": "buy",
                "type": "stop_limit",
                "time_in_force": "day",
                "stop_price": 142.00,  # ask=142.55 >= 142 => triggers
                "limit_price": 143.00,  # ask=142.55 <= 143 => fills
            },
            sample_state,
        )
        body = result.response_body
        assert body["status"] == "filled"
        # Fill at min(ask, limit) = min(142.55, 143.00) = 142.55
        assert body["filled_avg_price"] == 142.55


# =========================================================================
# Order errors (5)
# =========================================================================


class TestOrderErrors:
    async def test_create_order_invalid_symbol(self, pack, sample_state):
        """Unknown symbol returns 422 error."""
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "FAKE",
                "qty": "10",
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            },
            sample_state,
        )
        assert result.response_body["code"] == 422
        assert "FAKE" in result.response_body["message"]

    async def test_create_order_untradable_asset(self, pack, sample_state):
        """Asset with tradable=False returns 422 error."""
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "HALT",
                "qty": "10",
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            },
            sample_state,
        )
        assert result.response_body["code"] == 422
        assert "not tradable" in result.response_body["message"]

    async def test_create_order_insufficient_buying_power(self, pack, sample_state):
        """Buy exceeding buying_power returns 403 error."""
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "AAPL",
                "qty": "10000",
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            },
            sample_state,
        )
        # 10000 * 152.05 (ask) = 1,520,500 > 200,000 buying_power
        assert result.response_body["code"] == 403
        assert "Insufficient buying power" in result.response_body["message"]

    async def test_create_order_trading_blocked(self, pack, sample_state):
        """Account with trading_blocked=True returns 403 error."""
        blocked_state = {**sample_state}
        blocked_state["alpaca_accounts"] = [
            {**sample_state["alpaca_accounts"][0], "trading_blocked": True}
        ]
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "AAPL",
                "qty": "10",
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            },
            blocked_state,
        )
        assert result.response_body["code"] == 403
        assert "Trading blocked" in result.response_body["message"]

    async def test_cancel_filled_order(self, pack, sample_state):
        """Cancelling a filled order returns 422 error."""
        result = await pack.handle_action(
            ToolName("cancel_order"),
            {"id": "ord_filled"},
            sample_state,
        )
        assert result.response_body["code"] == 422
        assert "Cannot cancel" in result.response_body["message"]


# =========================================================================
# Account state (3)
# =========================================================================


class TestAccountState:
    async def test_get_account_returns_fields(self, pack, sample_state):
        """Get account returns all standard Alpaca account fields."""
        result = await pack.handle_action(
            ToolName("get_account"),
            {},
            sample_state,
        )
        body = result.response_body
        assert body["id"] == "acc_test_001"
        assert body["status"] == "ACTIVE"
        assert body["currency"] == "USD"
        assert body["buying_power"] == 200000.00
        assert body["cash"] == 100000.00
        assert body["equity"] == 115000.00
        assert "pattern_day_trader" in body
        assert "trading_blocked" in body

    async def test_get_account_empty_state(self, pack):
        """Empty accounts list returns 404 error."""
        result = await pack.handle_action(
            ToolName("get_account"),
            {},
            {"alpaca_accounts": []},
        )
        assert result.response_body["code"] == 404
        assert "Account not found" in result.response_body["message"]

    async def test_buying_power_math_on_buy(self, pack, sample_state):
        """After market buy: new_bp = old_bp - (fill_price * qty)."""
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "TSLA",
                "qty": "5",
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            },
            sample_state,
        )
        body = result.response_body
        assert body["status"] == "filled"
        fill_price = body["filled_avg_price"]

        acct_deltas = [d for d in result.proposed_state_deltas if d.entity_type == "alpaca_account"]
        assert len(acct_deltas) == 1
        expected_bp = round(200000.00 - fill_price * 5.0, 2)
        assert acct_deltas[0].fields["buying_power"] == expected_bp


# =========================================================================
# Positions (5)
# =========================================================================


class TestPositions:
    async def test_position_created_on_first_buy(self, pack, sample_state):
        """Buying NVDA (no existing position) creates a new position."""
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "NVDA",
                "qty": "10",
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            },
            sample_state,
        )
        pos_deltas = [d for d in result.proposed_state_deltas if d.entity_type == "alpaca_position"]
        assert len(pos_deltas) == 1
        assert pos_deltas[0].operation == "create"
        assert pos_deltas[0].fields["symbol"] == "NVDA"
        assert pos_deltas[0].fields["qty"] == 10.0
        assert pos_deltas[0].fields["side"] == "long"

    async def test_position_avg_price_updated(self, pack, sample_state):
        """Buying more AAPL updates avg_entry_price with weighted average."""
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "AAPL",
                "qty": "50",
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            },
            sample_state,
        )
        pos_deltas = [d for d in result.proposed_state_deltas if d.entity_type == "alpaca_position"]
        assert len(pos_deltas) == 1
        assert pos_deltas[0].operation == "update"
        fill_price = result.response_body["filled_avg_price"]
        # new_avg = (150 * 100 + fill_price * 50) / 150
        expected_avg = round((150.00 * 100 + fill_price * 50) / 150, 4)
        assert pos_deltas[0].fields["avg_entry_price"] == expected_avg
        assert pos_deltas[0].fields["qty"] == 150.0
        assert pos_deltas[0].previous_fields["qty"] == 100.0

    async def test_close_position_generates_sell_order(self, pack, sample_state):
        """Closing AAPL position creates market sell + deletes position + updates account."""
        result = await pack.handle_action(
            ToolName("close_position"),
            {"symbol": "AAPL"},
            sample_state,
        )
        body = result.response_body
        assert body["side"] == "sell"
        assert body["type"] == "market"
        assert body["status"] == "filled"
        assert body["qty"] == 100.0

        deltas = result.proposed_state_deltas
        # order create, position delete, account update, activity create
        assert len(deltas) == 4

        order_delta = deltas[0]
        assert order_delta.entity_type == "alpaca_order"
        assert order_delta.operation == "create"

        pos_delta = deltas[1]
        assert pos_delta.entity_type == "alpaca_position"
        assert pos_delta.operation == "delete"
        assert pos_delta.entity_id == "pos_aapl"

        acct_delta = deltas[2]
        assert acct_delta.entity_type == "alpaca_account"
        assert acct_delta.operation == "update"
        # Cash should increase (sold position)
        assert acct_delta.fields["cash"] > 100000.00

    async def test_list_positions_enriches_with_live_pl(self, pack, sample_state):
        """P&L computed from current quote, not stored values."""
        result = await pack.handle_action(
            ToolName("list_positions"),
            {},
            sample_state,
        )
        positions = result.response_body["positions"]
        assert len(positions) == 1
        pos = positions[0]
        # Enriched using quote ask_price (152.05)
        assert pos["current_price"] == 152.05
        assert pos["market_value"] == round(152.05 * 100, 2)
        assert pos["cost_basis"] == round(150.00 * 100, 2)
        expected_pl = round(152.05 * 100 - 150.00 * 100, 2)
        assert pos["unrealized_pl"] == expected_pl

    async def test_get_position_not_found(self, pack, sample_state):
        """Getting position for a symbol with no position returns 404."""
        result = await pack.handle_action(
            ToolName("get_position"),
            {"symbol": "GOOG"},
            sample_state,
        )
        assert result.response_body["code"] == 404
        assert "Position not found" in result.response_body["message"]


# =========================================================================
# Market data (5)
# =========================================================================


class TestMarketData:
    async def test_get_bars_returns_alpaca_format(self, pack, sample_state):
        """Bars response uses Alpaca short-field format {t, o, h, l, c, v, n, vw}."""
        result = await pack.handle_action(
            ToolName("get_bars"),
            {"symbol": "AAPL"},
            sample_state,
        )
        body = result.response_body
        assert body["symbol"] == "AAPL"
        assert "bars" in body
        assert "next_page_token" in body
        bar = body["bars"][0]
        for key in ("t", "o", "h", "l", "c", "v", "n", "vw"):
            assert key in bar

    async def test_get_bars_filters_by_symbol(self, pack, sample_state):
        """Only bars matching requested symbol are returned."""
        result = await pack.handle_action(
            ToolName("get_bars"),
            {"symbol": "AAPL"},
            sample_state,
        )
        bars = result.response_body["bars"]
        assert len(bars) == 2  # 2 AAPL bars in fixture

    async def test_get_bars_pagination(self, pack, sample_state):
        """Limit=1 returns 1 bar and a next_page_token."""
        result = await pack.handle_action(
            ToolName("get_bars"),
            {"symbol": "AAPL", "limit": "1"},
            sample_state,
        )
        body = result.response_body
        assert len(body["bars"]) == 1
        assert body["next_page_token"] is not None

    async def test_get_latest_quote_alpaca_format(self, pack, sample_state):
        """Latest quote uses Alpaca short-field format {t, bp, bs, bx, ap, as, ax, c}."""
        result = await pack.handle_action(
            ToolName("get_latest_quote"),
            {"symbol": "AAPL"},
            sample_state,
        )
        body = result.response_body
        assert body["symbol"] == "AAPL"
        quote = body["quote"]
        assert quote["bp"] == 151.95
        assert quote["ap"] == 152.05
        assert quote["bs"] == 200
        for key in ("t", "bp", "bs", "bx", "ap", "as", "ax", "c"):
            assert key in quote

    async def test_get_snapshot_composition(self, pack, sample_state):
        """Snapshot contains latestQuote, minuteBar, dailyBar, prevDailyBar."""
        result = await pack.handle_action(
            ToolName("get_snapshot"),
            {"symbol": "AAPL"},
            sample_state,
        )
        body = result.response_body
        assert body["latestQuote"] is not None
        assert body["latestQuote"]["symbol"] == "AAPL"
        assert body["minuteBar"] is not None
        assert body["dailyBar"] is not None
        assert body["prevDailyBar"] is not None
        # minuteBar should be the latest bar (sorted desc by timestamp)
        assert body["minuteBar"]["id"] == "bar_aapl_1"
        assert body["prevDailyBar"]["id"] == "bar_aapl_2"


# =========================================================================
# Clock and assets (3)
# =========================================================================


class TestClockAndAssets:
    async def test_get_clock(self, pack, sample_state):
        """Clock returns is_open, next_open, next_close."""
        result = await pack.handle_action(
            ToolName("get_clock"),
            {},
            sample_state,
        )
        body = result.response_body
        assert body["is_open"] is True
        assert body["next_open"] == "2026-03-25T09:30:00Z"
        assert body["next_close"] == "2026-03-24T16:00:00Z"

    async def test_list_assets_all(self, pack, sample_state):
        """Listing all assets returns all 4 assets."""
        result = await pack.handle_action(
            ToolName("list_assets"),
            {},
            sample_state,
        )
        assets = result.response_body["assets"]
        assert len(assets) == 4

    async def test_list_assets_filter_inactive(self, pack, sample_state):
        """Filtering by status=inactive returns only HALT."""
        result = await pack.handle_action(
            ToolName("list_assets"),
            {"status": "inactive"},
            sample_state,
        )
        assets = result.response_body["assets"]
        assert len(assets) == 1
        assert assets[0]["symbol"] == "HALT"


# =========================================================================
# News (4)
# =========================================================================


class TestNews:
    async def test_get_news_all(self, pack, sample_state):
        """Get news returns all articles (sorted newest first)."""
        result = await pack.handle_action(
            ToolName("get_news"),
            {},
            sample_state,
        )
        body = result.response_body
        assert len(body["news"]) == 2
        # Sorted by created_at desc -- news_001 (16:05) before news_002 (09:30)
        assert body["news"][0]["id"] == "news_001"
        assert body["news"][1]["id"] == "news_002"

    async def test_get_news_filter_by_symbol(self, pack, sample_state):
        """Filtering by symbols=NVDA returns only NVDA news."""
        result = await pack.handle_action(
            ToolName("get_news"),
            {"symbols": "NVDA"},
            sample_state,
        )
        news = result.response_body["news"]
        assert len(news) == 1
        assert "NVDA" in news[0]["symbols"]

    async def test_get_news_pagination(self, pack, sample_state):
        """Limit=1 returns 1 article and a next_page_token."""
        result = await pack.handle_action(
            ToolName("get_news"),
            {"limit": "1"},
            sample_state,
        )
        body = result.response_body
        assert len(body["news"]) == 1
        assert body["next_page_token"] is not None

    async def test_get_news_strips_internal_fields(self, pack, sample_state):
        """Internal metadata fields are stripped from news response."""
        result = await pack.handle_action(
            ToolName("get_news"),
            {},
            sample_state,
        )
        for article in result.response_body["news"]:
            assert "factual_accuracy" not in article
            assert "sentiment_bias" not in article
            assert "market_impact_expected" not in article
            # But public fields are still present
            assert "headline" in article
            assert "source" in article


# =========================================================================
# Social sentiment (4)
# =========================================================================


class TestSocialSentiment:
    async def test_get_feed_filters_by_symbol(self, pack, sample_state):
        """Social feed filtered by symbol returns matching entries."""
        result = await pack.handle_action(
            ToolName("social_get_feed"),
            {"symbol": "NVDA"},
            sample_state,
        )
        body = result.response_body
        assert body["count"] >= 1
        for post in body["posts"]:
            assert post["symbol"] == "NVDA"

    async def test_get_sentiment_returns_score(self, pack, sample_state):
        """NVDA sentiment score is 0.72 from fixture data."""
        result = await pack.handle_action(
            ToolName("social_get_sentiment"),
            {"symbol": "NVDA"},
            sample_state,
        )
        body = result.response_body
        assert body["score"] == 0.72
        assert body["symbol"] == "NVDA"
        assert body["post_count"] == 145

    async def test_get_sentiment_default_when_missing(self, pack, sample_state):
        """Missing symbol returns default score=0.0, post_count=0."""
        result = await pack.handle_action(
            ToolName("social_get_sentiment"),
            {"symbol": "GOOG"},
            sample_state,
        )
        body = result.response_body
        assert body["symbol"] == "GOOG"
        assert body["score"] == 0.0
        assert body["post_count"] == 0

    async def test_get_trending_ranked_order(self, pack, sample_state):
        """Trending returns entries sorted by trending_rank ascending."""
        result = await pack.handle_action(
            ToolName("social_get_trending"),
            {},
            sample_state,
        )
        body = result.response_body
        trending = body["trending"]
        assert body["count"] == 3
        # Ranks: NVDA=1, TSLA=2, AAPL=3
        assert trending[0]["trending_rank"] == 1
        assert trending[0]["symbol"] == "NVDA"
        assert trending[1]["trending_rank"] == 2
        assert trending[1]["symbol"] == "TSLA"
        assert trending[2]["trending_rank"] == 3
        assert trending[2]["symbol"] == "AAPL"


# =========================================================================
# Fill model (4)
# =========================================================================


class TestFillModel:
    def test_market_buy_slippage(self):
        """Market buy fill_price = ask * (1 + 0.001) exactly."""
        quote = {"ask_price": 100.00, "bid_price": 99.90}
        fill_price, status = _compute_fill_price(quote, "buy", "market", None, None)
        assert status == "filled"
        expected = round(100.00 * (1 + SLIPPAGE_BPS / 10000), 4)
        assert fill_price == expected
        assert fill_price == 100.10

    def test_market_sell_slippage(self):
        """Market sell fill_price = bid * (1 - 0.001) exactly."""
        quote = {"ask_price": 100.00, "bid_price": 99.90}
        fill_price, status = _compute_fill_price(quote, "sell", "market", None, None)
        assert status == "filled"
        expected = round(99.90 * (1 - SLIPPAGE_BPS / 10000), 4)
        assert fill_price == expected
        assert fill_price == 99.8001

    def test_limit_fill_at_limit_not_ask(self):
        """When ask < limit, fill at min(ask, limit) = ask."""
        quote = {"ask_price": 95.00, "bid_price": 94.90}
        fill_price, status = _compute_fill_price(quote, "buy", "limit", 100.00, None)
        assert status == "filled"
        assert fill_price == 95.00  # min(ask=95, limit=100) = 95

    def test_compute_fill_price_unknown_type(self):
        """Unknown order type returns (None, 'rejected')."""
        quote = {"ask_price": 100.00, "bid_price": 99.90}
        fill_price, status = _compute_fill_price(quote, "buy", "foo", None, None)
        assert fill_price is None
        assert status == "rejected"


# =========================================================================
# State machines (3)
# =========================================================================


class TestStateMachines:
    def test_order_valid_transitions(self):
        """Accepted orders can transition to filled or cancelled."""
        assert "filled" in ORDER_TRANSITIONS["accepted"]
        assert "cancelled" in ORDER_TRANSITIONS["accepted"]
        assert "accepted" in ORDER_TRANSITIONS["new"]

    def test_order_invalid_transitions(self):
        """Filled orders cannot transition to accepted; cancelled cannot go to filled."""
        assert "accepted" not in ORDER_TRANSITIONS["filled"]
        assert "filled" not in ORDER_TRANSITIONS["cancelled"]

    def test_order_terminal_states(self):
        """Filled, cancelled, expired, and rejected are terminal (empty transitions)."""
        assert ORDER_TRANSITIONS["filled"] == []
        assert ORDER_TRANSITIONS["cancelled"] == []
        assert ORDER_TRANSITIONS["expired"] == []
        assert ORDER_TRANSITIONS["rejected"] == []


# =========================================================================
# Pack auto-discovery (1)
# =========================================================================


class TestPackAutoDiscovery:
    def test_pack_discoverable(self):
        """TradingPack is a ServicePack subclass."""
        assert issubclass(TradingPack, ServicePack)
        pack = TradingPack()
        assert pack.pack_name == "alpaca"
        assert pack.fidelity_tier == 1


# ---------------------------------------------------------------------------
# Edge case tests (Bug fix validation)
# ---------------------------------------------------------------------------


class TestBugFixEquityAllPositions:
    """Bug 1: Equity must include ALL position market values, not just the new one."""

    async def test_equity_includes_existing_positions(self, pack, sample_state):
        """Buy NVDA when AAPL position already exists. Equity must include both."""
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "NVDA",
                "qty": "10",
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            },
            sample_state,
        )
        # Find account update delta
        acct_delta = None
        for d in result.proposed_state_deltas:
            if d.entity_type == "alpaca_account":
                acct_delta = d
                break
        assert acct_delta is not None
        new_equity = acct_delta.fields["equity"]
        new_cash = acct_delta.fields["cash"]
        long_mv = acct_delta.fields["long_market_value"]
        # Equity = cash + ALL positions (existing AAPL + new NVDA)
        assert new_equity == round(new_cash + long_mv, 2)
        # long_market_value must be > just the new NVDA position value
        # (should include existing AAPL at ~$15,200)
        assert long_mv > 14000, "Must include existing AAPL position value"


class TestBugFixCancelStateMachine:
    """Bug 3: Cancel must only work for 'accepted' and 'partially_filled'."""

    async def test_cancel_new_order_rejected(self, pack, sample_state):
        """Orders in 'new' status cannot be cancelled per state machine."""
        # Add a "new" order to state
        sample_state["alpaca_orders"].append(
            {
                "id": "ord_new_test",
                "symbol": "AAPL",
                "qty": 10,
                "side": "buy",
                "type": "limit",
                "status": "new",
                "time_in_force": "day",
                "created_at": "2026-03-24T10:00:00Z",
            }
        )
        result = await pack.handle_action(
            ToolName("cancel_order"),
            {"id": "ord_new_test"},
            sample_state,
        )
        # Must return error — "new" is not cancellable
        assert result.response_body.get("code") == 422
        assert "Cannot cancel" in result.response_body.get("message", "")
        assert len(result.proposed_state_deltas) == 0


class TestBugFixClosePositionEquity:
    """Bug 4: close_position must update equity, portfolio_value, long_market_value."""

    async def test_close_position_updates_equity(self, pack, sample_state):
        """Closing AAPL position must update equity to reflect no AAPL."""
        result = await pack.handle_action(
            ToolName("close_position"),
            {"symbol": "AAPL"},
            sample_state,
        )
        # Find account delta
        acct_delta = None
        for d in result.proposed_state_deltas:
            if d.entity_type == "alpaca_account":
                acct_delta = d
                break
        assert acct_delta is not None
        assert "equity" in acct_delta.fields
        assert "portfolio_value" in acct_delta.fields
        assert "long_market_value" in acct_delta.fields
        # After closing AAPL, long_market_value should be 0 (only position)
        assert acct_delta.fields["long_market_value"] == 0


class TestBugFixZeroQtyPosition:
    """Bug 5: Selling exactly all shares via create_order deletes position."""

    async def test_sell_all_shares_deletes_position(self, pack, sample_state):
        """Sell 100 AAPL (exact position qty) via create_order → position deleted."""
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "AAPL",
                "qty": "100",
                "side": "sell",
                "type": "market",
                "time_in_force": "day",
            },
            sample_state,
        )
        # Position delta should be a DELETE, not an update to qty=0
        pos_delta = None
        for d in result.proposed_state_deltas:
            if d.entity_type == "alpaca_position":
                pos_delta = d
                break
        assert pos_delta is not None
        assert pos_delta.operation == "delete", f"Expected delete, got {pos_delta.operation}"


class TestBugFixInputValidation:
    """Bug 6: qty<=0 and negative prices must be rejected."""

    async def test_zero_qty_rejected(self, pack, sample_state):
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "AAPL",
                "qty": "0",
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            },
            sample_state,
        )
        assert result.response_body.get("code") == 422
        assert "qty" in result.response_body.get("message", "").lower()

    async def test_negative_qty_rejected(self, pack, sample_state):
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "AAPL",
                "qty": "-10",
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            },
            sample_state,
        )
        assert result.response_body.get("code") == 422

    async def test_negative_limit_price_rejected(self, pack, sample_state):
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "AAPL",
                "qty": "10",
                "side": "buy",
                "type": "limit",
                "time_in_force": "day",
                "limit_price": "-100",
            },
            sample_state,
        )
        assert result.response_body.get("code") == 422
        assert "limit_price" in result.response_body.get("message", "")

    async def test_negative_stop_price_rejected(self, pack, sample_state):
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "AAPL",
                "qty": "10",
                "side": "buy",
                "type": "stop",
                "time_in_force": "day",
                "stop_price": "-50",
            },
            sample_state,
        )
        assert result.response_body.get("code") == 422
        assert "stop_price" in result.response_body.get("message", "")


class TestBugFixStateConsistency:
    """Cross-cutting: verify state consistency after operations."""

    async def test_equity_equals_cash_plus_positions(self, pack, sample_state):
        """After a buy, equity must exactly equal cash + sum(position market values)."""
        result = await pack.handle_action(
            ToolName("create_order"),
            {
                "symbol": "TSLA",
                "qty": "5",
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
            },
            sample_state,
        )
        acct_delta = None
        for d in result.proposed_state_deltas:
            if d.entity_type == "alpaca_account":
                acct_delta = d
                break
        assert acct_delta is not None
        equity = acct_delta.fields["equity"]
        cash = acct_delta.fields["cash"]
        long_mv = acct_delta.fields["long_market_value"]
        assert equity == round(cash + long_mv, 2), (
            f"equity={equity} != cash({cash}) + long_mv({long_mv})"
        )
