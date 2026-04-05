"""Entity schemas and tool definitions for the trading service pack.

Pure data -- no logic, no imports beyond stdlib. All field names and
response shapes match the Alpaca Markets API exactly so that agents
built on Alpaca SDKs can connect with zero code changes.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Entity schemas
# ---------------------------------------------------------------------------

ACCOUNT_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "status", "currency", "buying_power", "cash", "portfolio_value", "equity"],
    "properties": {
        "id": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["ACTIVE", "INACTIVE", "ACCOUNT_UPDATED"],
        },
        "currency": {"type": "string", "default": "USD"},
        "buying_power": {"type": "number"},
        "cash": {"type": "number"},
        "portfolio_value": {"type": "number"},
        "equity": {"type": "number"},
        "last_equity": {"type": "number"},
        "long_market_value": {"type": "number"},
        "short_market_value": {"type": "number"},
        "initial_margin": {"type": "number"},
        "maintenance_margin": {"type": "number"},
        "daytrade_count": {"type": "integer", "default": 0},
        "pattern_day_trader": {"type": "boolean", "default": False},
        "trading_blocked": {"type": "boolean", "default": False},
        "transfers_blocked": {"type": "boolean", "default": False},
        "account_blocked": {"type": "boolean", "default": False},
    },
}

ORDER_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "symbol", "qty", "type", "side", "time_in_force", "status", "created_at"],
    "properties": {
        "id": {"type": "string"},
        "client_order_id": {"type": "string"},
        "created_at": {"type": "string"},
        "submitted_at": {"type": "string"},
        "filled_at": {"type": ["string", "null"]},
        "expired_at": {"type": ["string", "null"]},
        "canceled_at": {"type": ["string", "null"]},
        "asset_id": {"type": "string", "x-volnix-ref": "alpaca_asset"},
        "symbol": {"type": "string"},
        "qty": {"type": "number"},
        "filled_qty": {"type": "number", "default": 0},
        "filled_avg_price": {"type": ["number", "null"]},
        "type": {
            "type": "string",
            "enum": ["market", "limit", "stop", "stop_limit", "trailing_stop"],
        },
        "side": {
            "type": "string",
            "enum": ["buy", "sell"],
        },
        "time_in_force": {
            "type": "string",
            "enum": ["day", "gtc", "ioc", "fok"],
        },
        "limit_price": {"type": ["number", "null"]},
        "stop_price": {"type": ["number", "null"]},
        "trail_price": {"type": ["number", "null"]},
        "trail_percent": {"type": ["number", "null"]},
        "status": {
            "type": "string",
            "enum": [
                "new", "accepted", "partially_filled", "filled",
                "cancelled", "expired", "rejected",
            ],
        },
        "order_class": {"type": "string", "default": "simple"},
    },
}

POSITION_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "symbol", "qty", "side", "avg_entry_price"],
    "properties": {
        "id": {"type": "string"},
        "asset_id": {"type": "string", "x-volnix-ref": "alpaca_asset"},
        "symbol": {"type": "string"},
        "exchange": {"type": "string"},
        "asset_class": {"type": "string", "default": "us_equity"},
        "avg_entry_price": {"type": "number"},
        "qty": {"type": "number"},
        "side": {
            "type": "string",
            "enum": ["long", "short"],
        },
        "market_value": {"type": "number"},
        "cost_basis": {"type": "number"},
        "unrealized_pl": {"type": "number"},
        "unrealized_plpc": {"type": "number"},
        "current_price": {"type": "number"},
        "lastday_price": {"type": "number"},
        "change_today": {"type": "number"},
    },
}

ASSET_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "symbol", "name", "exchange", "status"],
    "properties": {
        "id": {"type": "string"},
        "symbol": {"type": "string"},
        "name": {"type": "string"},
        "exchange": {"type": "string"},
        "asset_class": {"type": "string", "default": "us_equity"},
        "tradable": {"type": "boolean", "default": True},
        "fractionable": {"type": "boolean", "default": False},
        "shortable": {"type": "boolean", "default": True},
        "easy_to_borrow": {"type": "boolean", "default": True},
        "marginable": {"type": "boolean", "default": True},
        "status": {
            "type": "string",
            "enum": ["active", "inactive"],
        },
    },
}

BAR_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "symbol", "timestamp", "open", "high", "low", "close", "volume"],
    "properties": {
        "id": {"type": "string"},
        "symbol": {"type": "string"},
        "timestamp": {"type": "string"},
        "open": {"type": "number"},
        "high": {"type": "number"},
        "low": {"type": "number"},
        "close": {"type": "number"},
        "volume": {"type": "integer"},
        "trade_count": {"type": "integer"},
        "vwap": {"type": "number"},
        "timeframe": {"type": "string"},
    },
}

QUOTE_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "symbol", "timestamp", "bid_price", "ask_price"],
    "properties": {
        "id": {"type": "string"},
        "symbol": {"type": "string"},
        "timestamp": {"type": "string"},
        "bid_price": {"type": "number"},
        "bid_size": {"type": "integer"},
        "bid_exchange": {"type": "string"},
        "ask_price": {"type": "number"},
        "ask_size": {"type": "integer"},
        "ask_exchange": {"type": "string"},
        "conditions": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}

CLOCK_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "timestamp", "is_open"],
    "properties": {
        "id": {"type": "string"},
        "timestamp": {"type": "string"},
        "is_open": {"type": "boolean"},
        "next_open": {"type": ["string", "null"]},
        "next_close": {"type": ["string", "null"]},
    },
}

NEWS_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "headline", "created_at", "source"],
    "properties": {
        "id": {"type": "string"},
        "headline": {"type": "string"},
        "author": {"type": "string"},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
        "summary": {"type": "string"},
        "url": {"type": "string"},
        "symbols": {
            "type": "array",
            "items": {"type": "string"},
        },
        "source": {"type": "string"},
        "images": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "size": {"type": "string"},
                },
            },
        },
        # Internal metadata -- stripped from agent-facing responses,
        # available in the governance report for evaluation.
        "factual_accuracy": {"type": "number", "x-volnix-internal": True},
        "sentiment_bias": {"type": "number", "x-volnix-internal": True},
        "market_impact_expected": {"type": "number", "x-volnix-internal": True},
    },
}

ACTIVITY_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "activity_type", "date"],
    "properties": {
        "id": {"type": "string"},
        "activity_type": {
            "type": "string",
            "enum": ["FILL", "DIV", "TRANS"],
        },
        "date": {"type": "string"},
        "qty": {"type": "number"},
        "price": {"type": "number"},
        "symbol": {"type": "string"},
        "side": {
            "type": "string",
            "enum": ["buy", "sell"],
        },
        "order_id": {"type": "string", "x-volnix-ref": "alpaca_order"},
        "cum_qty": {"type": "number"},
        "leaves_qty": {"type": "number"},
        "type": {"type": "string"},
    },
}

SENTIMENT_ENTITY_SCHEMA: dict = {
    "type": "object",
    "x-volnix-identity": "id",
    "required": ["id", "symbol", "source", "score", "computed_at"],
    "properties": {
        "id": {"type": "string"},
        "symbol": {"type": "string"},
        "source": {
            "type": "string",
            "enum": ["reddit", "twitter", "all"],
        },
        "window": {"type": "string"},
        "score": {"type": "number", "minimum": -1, "maximum": 1},
        "post_count": {"type": "integer", "default": 0},
        "positive_count": {"type": "integer", "default": 0},
        "negative_count": {"type": "integer", "default": 0},
        "neutral_count": {"type": "integer", "default": 0},
        "trending_rank": {"type": ["integer", "null"]},
        "computed_at": {"type": "string"},
    },
}


# ---------------------------------------------------------------------------
# Tool definitions (22 total)
# ---------------------------------------------------------------------------

TRADING_TOOL_DEFINITIONS: list[dict] = [
    # ── Broker: Account ────────────────────────────────────────
    {
        "name": "get_account",
        "description": "Get the account details including equity, buying power, and margin status.",
        "http_path": "/v2/account",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {},
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "status": {"type": "string"},
                "buying_power": {"type": "number"},
                "cash": {"type": "number"},
                "equity": {"type": "number"},
                "portfolio_value": {"type": "number"},
            },
        },
    },
    # ── Broker: Orders ─────────────────────────────────────────
    {
        "name": "create_order",
        "description": "Submit a new order (market, limit, stop, stop_limit, trailing_stop).",
        "http_path": "/v2/orders",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["symbol", "qty", "side", "type", "time_in_force"],
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The stock symbol to trade.",
                },
                "qty": {
                    "type": "string",
                    "description": "Number of shares to trade.",
                },
                "side": {
                    "type": "string",
                    "description": "Order side.",
                    "enum": ["buy", "sell"],
                },
                "type": {
                    "type": "string",
                    "description": "Order type.",
                    "enum": ["market", "limit", "stop", "stop_limit", "trailing_stop"],
                },
                "time_in_force": {
                    "type": "string",
                    "description": "Time in force.",
                    "enum": ["day", "gtc", "ioc", "fok"],
                },
                "limit_price": {
                    "type": "string",
                    "description": "Limit price (required for limit and stop_limit orders).",
                },
                "stop_price": {
                    "type": "string",
                    "description": "Stop price (required for stop and stop_limit orders).",
                },
                "trail_price": {
                    "type": "string",
                    "description": "Trail amount in dollars (for trailing_stop).",
                },
                "trail_percent": {
                    "type": "string",
                    "description": "Trail percentage (for trailing_stop).",
                },
                "client_order_id": {
                    "type": "string",
                    "description": "Client-specified order ID for idempotency.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "list_orders",
        "description": "List orders, optionally filtered by status.",
        "http_path": "/v2/orders",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter: open, closed, or all.",
                    "enum": ["open", "closed", "all"],
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of orders to return.",
                    "default": 50,
                },
                "direction": {
                    "type": "string",
                    "description": "Sort direction.",
                    "enum": ["asc", "desc"],
                },
            },
        },
        "response_schema": {"type": "array"},
    },
    {
        "name": "get_order",
        "description": "Get a single order by ID.",
        "http_path": "/v2/orders/{id}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The order ID.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "cancel_order",
        "description": "Cancel an open order.",
        "http_path": "/v2/orders/{id}",
        "http_method": "DELETE",
        "parameters": {
            "type": "object",
            "required": ["id"],
            "properties": {
                "id": {
                    "type": "string",
                    "description": "The order ID to cancel.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    # ── Broker: Positions ──────────────────────────────────────
    {
        "name": "list_positions",
        "description": "List all open positions with live P&L computed from current quotes.",
        "http_path": "/v2/positions",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {},
        },
        "response_schema": {"type": "array"},
    },
    {
        "name": "get_position",
        "description": "Get a single position by symbol with live P&L.",
        "http_path": "/v2/positions/{symbol}",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["symbol"],
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The stock symbol.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "close_position",
        "description": "Close an open position by generating a market order for the opposite side.",
        "http_path": "/v2/positions/{symbol}",
        "http_method": "DELETE",
        "parameters": {
            "type": "object",
            "required": ["symbol"],
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The stock symbol to close.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    # ── Market Data: Bars ──────────────────────────────────────
    {
        "name": "get_bars",
        "description": "Get historical OHLCV bars for a stock.",
        "http_path": "/v2/stocks/{symbol}/bars",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["symbol"],
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The stock symbol.",
                },
                "timeframe": {
                    "type": "string",
                    "description": "Bar timeframe.",
                    "enum": ["1Min", "5Min", "15Min", "1H", "1D"],
                },
                "start": {
                    "type": "string",
                    "description": "Start timestamp (RFC 3339).",
                },
                "end": {
                    "type": "string",
                    "description": "End timestamp (RFC 3339).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max bars to return.",
                    "default": 1000,
                },
                "page_token": {
                    "type": "string",
                    "description": "Pagination token.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "bars": {"type": "array"},
                "symbol": {"type": "string"},
                "next_page_token": {"type": ["string", "null"]},
            },
        },
    },
    # ── Market Data: Quotes ────────────────────────────────────
    {
        "name": "get_latest_quote",
        "description": "Get the latest bid/ask quote for a stock.",
        "http_path": "/v2/stocks/{symbol}/quotes/latest",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["symbol"],
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The stock symbol.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "quote": {"type": "object"},
            },
        },
    },
    # ── Market Data: Trades ────────────────────────────────────
    {
        "name": "get_latest_trade",
        "description": "Get the latest trade for a stock.",
        "http_path": "/v2/stocks/{symbol}/trades/latest",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["symbol"],
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The stock symbol.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "trade": {"type": "object"},
            },
        },
    },
    # ── Market Data: Snapshot ──────────────────────────────────
    {
        "name": "get_snapshot",
        "description": "Get a complete snapshot (latest quote + bar + trade) for a stock.",
        "http_path": "/v2/stocks/{symbol}/snapshot",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["symbol"],
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The stock symbol.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "latestQuote": {"type": "object"},
                "latestTrade": {"type": ["object", "null"]},
                "minuteBar": {"type": ["object", "null"]},
                "dailyBar": {"type": ["object", "null"]},
                "prevDailyBar": {"type": ["object", "null"]},
            },
        },
    },
    # ── Reference: Clock ───────────────────────────────────────
    {
        "name": "get_clock",
        "description": "Get the current market clock (open/closed, next open/close times).",
        "http_path": "/v2/clock",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {},
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "timestamp": {"type": "string"},
                "is_open": {"type": "boolean"},
                "next_open": {"type": "string"},
                "next_close": {"type": "string"},
            },
        },
    },
    # ── Reference: Assets ──────────────────────────────────────
    {
        "name": "list_assets",
        "description": "List tradable assets, optionally filtered by status or asset class.",
        "http_path": "/v2/assets",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filter by status.",
                    "enum": ["active", "inactive"],
                },
                "asset_class": {
                    "type": "string",
                    "description": "Filter by asset class.",
                },
            },
        },
        "response_schema": {"type": "array"},
    },
    # ── News ───────────────────────────────────────────────────
    {
        "name": "get_news",
        "description": "Get news articles, optionally filtered by symbols and date range.",
        "http_path": "/v1beta1/news",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "symbols": {
                    "type": "string",
                    "description": "Comma-separated symbol list to filter by.",
                },
                "start": {
                    "type": "string",
                    "description": "Start date (RFC 3339).",
                },
                "end": {
                    "type": "string",
                    "description": "End date (RFC 3339).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max articles to return.",
                    "default": 10,
                },
                "page_token": {
                    "type": "string",
                    "description": "Pagination token.",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "news": {"type": "array"},
                "next_page_token": {"type": ["string", "null"]},
            },
        },
    },
    # ── Social Sentiment (Volnix Native) ────────────────────
    {
        "name": "social_get_feed",
        "description": "Get social media posts mentioning specific stocks.",
        "http_path": "/volnix/social/feed",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Filter by stock symbol.",
                },
                "source": {
                    "type": "string",
                    "description": "Filter by source platform.",
                    "enum": ["reddit", "twitter", "all"],
                },
                "limit": {
                    "type": "integer",
                    "description": "Max posts to return.",
                    "default": 20,
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "posts": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
    },
    {
        "name": "social_get_sentiment",
        "description": "Get aggregated sentiment score for a stock symbol.",
        "http_path": "/volnix/social/sentiment",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": ["symbol"],
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The stock symbol.",
                },
                "source": {
                    "type": "string",
                    "description": "Filter by source.",
                    "enum": ["reddit", "twitter", "all"],
                },
                "window": {
                    "type": "string",
                    "description": "Time window (e.g. '24h', '7d').",
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "score": {"type": "number"},
                "post_count": {"type": "integer"},
            },
        },
    },
    {
        "name": "social_get_trending",
        "description": "Get currently trending stock symbols by social media mention volume.",
        "http_path": "/volnix/social/trending",
        "http_method": "GET",
        "parameters": {
            "type": "object",
            "required": [],
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max trending items to return.",
                    "default": 10,
                },
            },
        },
        "response_schema": {
            "type": "object",
            "properties": {
                "trending": {"type": "array"},
                "count": {"type": "integer"},
            },
        },
    },
    # ── Animator/System: Market Evolution ──────────────────────
    {
        "name": "update_quote",
        "description": (
            "Update a stock quote (bid/ask). Used by the Animator to "
            "evolve prices in dynamic/reactive mode."
        ),
        "http_path": "/volnix/market/quote",
        "http_method": "PUT",
        "parameters": {
            "type": "object",
            "required": ["symbol", "bid_price", "ask_price"],
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The stock symbol.",
                },
                "bid_price": {"type": "number"},
                "bid_size": {"type": "integer"},
                "ask_price": {"type": "number"},
                "ask_size": {"type": "integer"},
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "create_bar",
        "description": (
            "Create a new OHLCV bar. Used by the Animator to advance "
            "price series in dynamic mode."
        ),
        "http_path": "/volnix/market/bar",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["symbol", "timestamp", "open", "high", "low", "close", "volume"],
            "properties": {
                "symbol": {"type": "string"},
                "timestamp": {"type": "string"},
                "open": {"type": "number"},
                "high": {"type": "number"},
                "low": {"type": "number"},
                "close": {"type": "number"},
                "volume": {"type": "integer"},
                "trade_count": {"type": "integer"},
                "vwap": {"type": "number"},
                "timeframe": {"type": "string", "default": "1Min"},
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "create_news",
        "description": (
            "Create a news article. Used by the Animator to inject "
            "breaking news, earnings releases, or rumors."
        ),
        "http_path": "/volnix/news",
        "http_method": "POST",
        "parameters": {
            "type": "object",
            "required": ["headline", "source"],
            "properties": {
                "headline": {"type": "string"},
                "author": {"type": "string"},
                "summary": {"type": "string"},
                "url": {"type": "string"},
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "source": {"type": "string"},
                "factual_accuracy": {
                    "type": "number",
                    "description": "Internal: how accurate is this news (0-1).",
                },
                "sentiment_bias": {
                    "type": "number",
                    "description": "Internal: sentiment direction (-1 to 1).",
                },
                "market_impact_expected": {
                    "type": "number",
                    "description": "Internal: expected price impact percent.",
                },
            },
        },
        "response_schema": {"type": "object"},
    },
    {
        "name": "social_update_sentiment",
        "description": (
            "Update aggregated sentiment for a symbol. Used by the "
            "Animator to reflect sentiment shifts in dynamic mode."
        ),
        "http_path": "/volnix/social/sentiment",
        "http_method": "PUT",
        "parameters": {
            "type": "object",
            "required": ["symbol", "source", "score"],
            "properties": {
                "symbol": {"type": "string"},
                "source": {
                    "type": "string",
                    "enum": ["reddit", "twitter", "all"],
                },
                "score": {"type": "number"},
                "post_count": {"type": "integer"},
                "positive_count": {"type": "integer"},
                "negative_count": {"type": "integer"},
                "neutral_count": {"type": "integer"},
                "trending_rank": {"type": ["integer", "null"]},
            },
        },
        "response_schema": {"type": "object"},
    },
]
