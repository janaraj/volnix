"""Trading service pack (Tier 1 -- verified).

Provides the canonical tool surface for Alpaca Markets-style brokerage
services: account management, order submission and lifecycle, position
tracking with live P&L, market data (bars, quotes, trades, snapshots),
market clock, news, and social sentiment.

Agent connection pattern:
    APCA_API_BASE_URL=http://localhost:8080/alpaca
    APCA_API_KEY_ID=TERRARIUM_SIM_KEY
    APCA_API_SECRET_KEY=TERRARIUM_SIM_SECRET

All paths, request shapes, and response shapes match the Alpaca Markets
API exactly so that agents built on Alpaca SDKs connect with zero code
changes.
"""

from __future__ import annotations

from typing import ClassVar

from terrarium.core.context import ResponseProposal
from terrarium.core.types import ToolName
from terrarium.packs.base import ActionHandler, ServicePack
from terrarium.packs.verified.trading.handlers import (
    handle_alpaca_cancel_order,
    handle_alpaca_close_position,
    handle_alpaca_create_bar,
    handle_alpaca_create_news,
    handle_alpaca_create_order,
    handle_alpaca_get_account,
    handle_alpaca_get_bars,
    handle_alpaca_get_clock,
    handle_alpaca_get_latest_quote,
    handle_alpaca_get_latest_trade,
    handle_alpaca_get_news,
    handle_alpaca_get_order,
    handle_alpaca_get_position,
    handle_alpaca_get_snapshot,
    handle_alpaca_list_assets,
    handle_alpaca_list_orders,
    handle_alpaca_list_positions,
    handle_alpaca_update_quote,
    handle_social_get_feed,
    handle_social_get_sentiment,
    handle_social_get_trending,
    handle_social_update_sentiment,
)
from terrarium.packs.verified.trading.schemas import (
    ACCOUNT_ENTITY_SCHEMA,
    ACTIVITY_ENTITY_SCHEMA,
    ASSET_ENTITY_SCHEMA,
    BAR_ENTITY_SCHEMA,
    CLOCK_ENTITY_SCHEMA,
    NEWS_ENTITY_SCHEMA,
    ORDER_ENTITY_SCHEMA,
    POSITION_ENTITY_SCHEMA,
    QUOTE_ENTITY_SCHEMA,
    SENTIMENT_ENTITY_SCHEMA,
    TRADING_TOOL_DEFINITIONS,
)
from terrarium.packs.verified.trading.state_machines import (
    ASSET_TRANSITIONS,
    ORDER_TRANSITIONS,
)


class TradingPack(ServicePack):
    """Verified pack for Alpaca Markets-style trading services.

    Tools: alpaca_get_account, alpaca_create_order, alpaca_list_orders,
    alpaca_get_order, alpaca_cancel_order, alpaca_list_positions,
    alpaca_get_position, alpaca_close_position, alpaca_get_bars,
    alpaca_get_latest_quote, alpaca_get_latest_trade, alpaca_get_snapshot,
    alpaca_get_clock, alpaca_list_assets, alpaca_get_news,
    social_get_feed, social_get_sentiment, social_get_trending,
    alpaca_update_quote, alpaca_create_bar, alpaca_create_news,
    social_update_sentiment.
    """

    pack_name: ClassVar[str] = "trading"
    category: ClassVar[str] = "trading"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        # Broker: Account
        "alpaca_get_account": handle_alpaca_get_account,
        # Broker: Orders
        "alpaca_create_order": handle_alpaca_create_order,
        "alpaca_list_orders": handle_alpaca_list_orders,
        "alpaca_get_order": handle_alpaca_get_order,
        "alpaca_cancel_order": handle_alpaca_cancel_order,
        # Broker: Positions
        "alpaca_list_positions": handle_alpaca_list_positions,
        "alpaca_get_position": handle_alpaca_get_position,
        "alpaca_close_position": handle_alpaca_close_position,
        # Market Data
        "alpaca_get_bars": handle_alpaca_get_bars,
        "alpaca_get_latest_quote": handle_alpaca_get_latest_quote,
        "alpaca_get_latest_trade": handle_alpaca_get_latest_trade,
        "alpaca_get_snapshot": handle_alpaca_get_snapshot,
        # Reference
        "alpaca_get_clock": handle_alpaca_get_clock,
        "alpaca_list_assets": handle_alpaca_list_assets,
        # News
        "alpaca_get_news": handle_alpaca_get_news,
        # Social Sentiment
        "social_get_feed": handle_social_get_feed,
        "social_get_sentiment": handle_social_get_sentiment,
        "social_get_trending": handle_social_get_trending,
        # Animator/System: Market Evolution
        "alpaca_update_quote": handle_alpaca_update_quote,
        "alpaca_create_bar": handle_alpaca_create_bar,
        "alpaca_create_news": handle_alpaca_create_news,
        "social_update_sentiment": handle_social_update_sentiment,
    }

    def get_tools(self) -> list[dict]:
        """Return the trading tool manifest."""
        return list(TRADING_TOOL_DEFINITIONS)

    def get_entity_schemas(self) -> dict:
        """Return entity schemas for all trading entities."""
        return {
            "alpaca_account": ACCOUNT_ENTITY_SCHEMA,
            "alpaca_order": ORDER_ENTITY_SCHEMA,
            "alpaca_position": POSITION_ENTITY_SCHEMA,
            "alpaca_asset": ASSET_ENTITY_SCHEMA,
            "alpaca_bar": BAR_ENTITY_SCHEMA,
            "alpaca_quote": QUOTE_ENTITY_SCHEMA,
            "alpaca_clock": CLOCK_ENTITY_SCHEMA,
            "alpaca_news": NEWS_ENTITY_SCHEMA,
            "alpaca_activity": ACTIVITY_ENTITY_SCHEMA,
            "social_sentiment": SENTIMENT_ENTITY_SCHEMA,
        }

    def get_state_machines(self) -> dict:
        """Return state machines for order and asset entities."""
        return {
            "alpaca_order": {"transitions": ORDER_TRANSITIONS},
            "alpaca_asset": {"transitions": ASSET_TRANSITIONS},
        }

    async def handle_action(
        self,
        action: ToolName,
        input_data: dict,
        state: dict,
    ) -> ResponseProposal:
        """Dispatch to the appropriate trading action handler."""
        return await self.dispatch_action(action, input_data, state)
