"""Trading service pack (Tier 1 -- verified).

Provides the canonical tool surface for Alpaca Markets-style brokerage
services: account management, order submission and lifecycle, position
tracking with live P&L, market data (bars, quotes, trades, snapshots),
market clock, news, and social sentiment.

Agent connection pattern:
    APCA_API_BASE_URL=http://localhost:8080/alpaca
    APCA_API_KEY_ID=VOLNIX_SIM_KEY
    APCA_API_SECRET_KEY=VOLNIX_SIM_SECRET

All paths, request shapes, and response shapes match the Alpaca Markets
API exactly so that agents built on Alpaca SDKs connect with zero code
changes.
"""

from __future__ import annotations

from typing import ClassVar

from volnix.core.context import ResponseProposal
from volnix.core.types import ToolName
from volnix.packs.base import ActionHandler, ServicePack
from volnix.packs.verified.alpaca.handlers import (
    handle_cancel_order,
    handle_close_position,
    handle_create_bar,
    handle_create_news,
    handle_create_order,
    handle_get_account,
    handle_get_bars,
    handle_get_clock,
    handle_get_latest_quote,
    handle_get_latest_trade,
    handle_get_news,
    handle_get_order,
    handle_get_position,
    handle_get_snapshot,
    handle_list_assets,
    handle_list_orders,
    handle_list_positions,
    handle_social_get_feed,
    handle_social_get_sentiment,
    handle_social_get_trending,
    handle_social_update_sentiment,
    handle_update_quote,
)
from volnix.packs.verified.alpaca.schemas import (
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
from volnix.packs.verified.alpaca.state_machines import (
    ASSET_TRANSITIONS,
    ORDER_TRANSITIONS,
)


class TradingPack(ServicePack):
    """Verified pack for Alpaca Markets-style trading services.

    Tools: get_account, create_order, list_orders,
    get_order, cancel_order, list_positions,
    get_position, close_position, get_bars,
    get_latest_quote, get_latest_trade, get_snapshot,
    get_clock, list_assets, get_news,
    social_get_feed, social_get_sentiment, social_get_trending,
    update_quote, create_bar, create_news,
    social_update_sentiment.
    """

    pack_name: ClassVar[str] = "alpaca"
    category: ClassVar[str] = "trading"
    fidelity_tier: ClassVar[int] = 1

    _handlers: ClassVar[dict[str, ActionHandler]] = {
        # Broker: Account
        "get_account": handle_get_account,
        # Broker: Orders
        "create_order": handle_create_order,
        "list_orders": handle_list_orders,
        "get_order": handle_get_order,
        "cancel_order": handle_cancel_order,
        # Broker: Positions
        "list_positions": handle_list_positions,
        "get_position": handle_get_position,
        "close_position": handle_close_position,
        # Market Data
        "get_bars": handle_get_bars,
        "get_latest_quote": handle_get_latest_quote,
        "get_latest_trade": handle_get_latest_trade,
        "get_snapshot": handle_get_snapshot,
        # Reference
        "get_clock": handle_get_clock,
        "list_assets": handle_list_assets,
        # News
        "get_news": handle_get_news,
        # Social Sentiment
        "social_get_feed": handle_social_get_feed,
        "social_get_sentiment": handle_social_get_sentiment,
        "social_get_trending": handle_social_get_trending,
        # Animator/System: Market Evolution
        "update_quote": handle_update_quote,
        "create_bar": handle_create_bar,
        "create_news": handle_create_news,
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
