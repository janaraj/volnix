# Terrarium Trading Service Pack — Spec

## Overview

The Trading Pack simulates a complete brokerage + market data + news + social sentiment environment, following the **Alpaca Markets API** surface. Any trading agent built on Alpaca (or any agent using the `alpaca-trade-api` Python/JS SDK) can connect via Path 1 (API base URL swap) with zero code changes.

```
APCA_API_BASE_URL=http://localhost:7400/alpaca    # the only change
APCA_API_KEY_ID=TERRARIUM_SIM_KEY
APCA_API_SECRET_KEY=TERRARIUM_SIM_SECRET
```

The pack is split into four sub-packs that compose together in a single world.

---

## Sub-Pack 1: Broker (Trading API)

**Real base:** `https://paper-api.alpaca.markets`
**Terrarium base:** `http://localhost:7400/alpaca`
**Source spec:** https://docs.alpaca.markets/reference

### Account

| Method | Endpoint | Simulated behavior |
|--------|----------|--------------------|
| `GET` | `/v2/account` | Returns account state: equity, buying_power, cash, portfolio_value, margin status. Terrarium world engine tracks all values as orders fill and positions change. |
| `GET` | `/v2/account/configurations` | Returns account config (dtbp_check, trade_confirm_email, pdt_check). Static per world definition. |
| `PATCH` | `/v2/account/configurations` | Updates config. Stored in world state. |
| `GET` | `/v2/account/activities` | Returns trade and non-trade activities. Built from world event log. |
| `GET` | `/v2/account/activities/:type` | Filtered activities (FILL, DIV, TRANS, etc). |

**Key response shape — `GET /v2/account`:**

```json
{
  "id": "acc_terra_001",
  "status": "ACTIVE",
  "currency": "USD",
  "buying_power": "127340.00",
  "cash": "63670.00",
  "portfolio_value": "163670.00",
  "equity": "163670.00",
  "last_equity": "160000.00",
  "long_market_value": "100000.00",
  "short_market_value": "0",
  "initial_margin": "50000.00",
  "maintenance_margin": "30000.00",
  "daytrade_count": 1,
  "pattern_day_trader": false,
  "trading_blocked": false,
  "transfers_blocked": false,
  "account_blocked": false
}
```

### Orders

| Method | Endpoint | Simulated behavior |
|--------|----------|--------------------|
| `POST` | `/v2/orders` | Submit order. Terrarium fills based on market data state + fill simulation (instant for market, price-match for limit). Applies slippage model. Returns order object. |
| `GET` | `/v2/orders` | List orders. Filters: status (open/closed/all), limit, after, until, direction, nested, symbols. |
| `GET` | `/v2/orders/:id` | Single order by ID. |
| `PATCH` | `/v2/orders/:id` | Replace order (modify qty, limit_price, stop_price, time_in_force, trail). |
| `DELETE` | `/v2/orders` | Cancel all open orders. |
| `DELETE` | `/v2/orders/:id` | Cancel single order. |

**Key request shape — `POST /v2/orders`:**

```json
{
  "symbol": "NVDA",
  "qty": "10",
  "side": "buy",
  "type": "limit",
  "time_in_force": "day",
  "limit_price": "142.50",
  "client_order_id": "agent-order-001"
}
```

**Supported order types:** `market`, `limit`, `stop`, `stop_limit`, `trailing_stop`
**Supported TIF:** `day`, `gtc`, `opg`, `cls`, `ioc`, `fok`
**Supported side:** `buy`, `sell`

**Fill simulation model:**
- `market` → fills at current quote ± simulated slippage (configurable: 0-0.5%)
- `limit` → fills when simulated price crosses limit_price
- `stop` → triggers when price crosses stop_price, then fills as market
- `stop_limit` → triggers at stop_price, then limit order at limit_price
- `trailing_stop` → maintains trailing offset, triggers on trail breach
- Partial fills: configurable probability for large orders

**Key response shape — order object:**

```json
{
  "id": "ord_terra_001",
  "client_order_id": "agent-order-001",
  "created_at": "2026-03-24T14:30:00Z",
  "submitted_at": "2026-03-24T14:30:00Z",
  "filled_at": null,
  "asset_id": "asset_nvda",
  "symbol": "NVDA",
  "qty": "10",
  "filled_qty": "0",
  "filled_avg_price": null,
  "type": "limit",
  "side": "buy",
  "time_in_force": "day",
  "limit_price": "142.50",
  "status": "accepted",
  "order_class": "simple"
}
```

**Order statuses:** `new` → `accepted` → `partially_filled` → `filled` | `cancelled` | `expired` | `rejected`

### Positions

| Method | Endpoint | Simulated behavior |
|--------|----------|--------------------|
| `GET` | `/v2/positions` | All open positions with current P&L calculated from live market data state. |
| `GET` | `/v2/positions/:symbol` | Single position. |
| `DELETE` | `/v2/positions` | Close all positions (generates market sell orders). |
| `DELETE` | `/v2/positions/:symbol` | Close single position. Optional `qty` or `percentage` param. |

**Key response shape — position object:**

```json
{
  "asset_id": "asset_nvda",
  "symbol": "NVDA",
  "exchange": "NASDAQ",
  "asset_class": "us_equity",
  "avg_entry_price": "135.20",
  "qty": "50",
  "side": "long",
  "market_value": "7125.00",
  "cost_basis": "6760.00",
  "unrealized_pl": "365.00",
  "unrealized_plpc": "0.054",
  "current_price": "142.50",
  "lastday_price": "140.10",
  "change_today": "0.0171"
}
```

### Assets

| Method | Endpoint | Simulated behavior |
|--------|----------|--------------------|
| `GET` | `/v2/assets` | List tradable assets. Returns assets defined in the world. |
| `GET` | `/v2/assets/:symbol` | Single asset details (tradable, fractionable, shortable, exchange, class). |

### Clock & Calendar

| Method | Endpoint | Simulated behavior |
|--------|----------|--------------------|
| `GET` | `/v2/clock` | Returns simulated market clock (open/closed, next_open, next_close). Terrarium controls simulated time. |
| `GET` | `/v2/calendar` | Returns market calendar (open/close times per date). |

### Watchlists

| Method | Endpoint | Simulated behavior |
|--------|----------|--------------------|
| `GET` | `/v2/watchlists` | List watchlists. |
| `POST` | `/v2/watchlists` | Create watchlist. |
| `GET` | `/v2/watchlists/:id` | Get watchlist. |
| `PUT` | `/v2/watchlists/:id` | Update watchlist. |
| `DELETE` | `/v2/watchlists/:id` | Delete watchlist. |
| `POST` | `/v2/watchlists/:id` | Add asset to watchlist. |
| `DELETE` | `/v2/watchlists/:id/:symbol` | Remove asset from watchlist. |

---

## Sub-Pack 2: Market Data

**Real base:** `https://data.alpaca.markets`
**Terrarium base:** `http://localhost:7400/alpaca-data`
**Source spec:** https://docs.alpaca.markets/docs/about-market-data-api

### Stock Bars (OHLCV Candles)

| Method | Endpoint | Simulated behavior |
|--------|----------|--------------------|
| `GET` | `/v2/stocks/{symbol}/bars` | Historical bars. Terrarium generates realistic price series from world definition (trend, volatility regime, event schedule). |
| `GET` | `/v2/stocks/bars` | Multi-symbol bars. |

**Query params:** `timeframe` (1Min, 5Min, 15Min, 1Hour, 1Day), `start`, `end`, `limit`, `feed`, `adjustment`, `sort`, `page_token`

**Response shape:**

```json
{
  "bars": [
    {
      "t": "2026-03-24T14:30:00Z",
      "o": 141.20,
      "h": 142.80,
      "l": 140.95,
      "c": 142.50,
      "v": 1234567,
      "n": 8923,
      "vw": 141.85
    }
  ],
  "symbol": "NVDA",
  "next_page_token": null
}
```

### Stock Quotes

| Method | Endpoint | Simulated behavior |
|--------|----------|--------------------|
| `GET` | `/v2/stocks/{symbol}/quotes` | Historical quotes. |
| `GET` | `/v2/stocks/{symbol}/quotes/latest` | Latest bid/ask. Terrarium updates on every tick based on price model. |
| `GET` | `/v2/stocks/quotes/latest` | Multi-symbol latest quotes. |

**Response shape — latest quote:**

```json
{
  "symbol": "NVDA",
  "quote": {
    "t": "2026-03-24T14:30:15Z",
    "ax": "V",
    "ap": 142.55,
    "as": 300,
    "bx": "Q",
    "bp": 142.45,
    "bs": 200,
    "c": ["R"]
  }
}
```

### Stock Trades

| Method | Endpoint | Simulated behavior |
|--------|----------|--------------------|
| `GET` | `/v2/stocks/{symbol}/trades` | Historical trades. |
| `GET` | `/v2/stocks/{symbol}/trades/latest` | Latest trade. |
| `GET` | `/v2/stocks/trades/latest` | Multi-symbol latest trades. |

### Snapshots

| Method | Endpoint | Simulated behavior |
|--------|----------|--------------------|
| `GET` | `/v2/stocks/{symbol}/snapshot` | Latest bar + quote + trade + daily bar + prev daily bar combined. |
| `GET` | `/v2/stocks/snapshots` | Multi-symbol snapshots. |

---

## Sub-Pack 3: News & Events

**Real base:** `https://data.alpaca.markets`
**Terrarium base:** `http://localhost:7400/alpaca-data`

### News

| Method | Endpoint | Simulated behavior |
|--------|----------|--------------------|
| `GET` | `/v1beta1/news` | Returns simulated news articles generated by World Animator. Includes sentiment, entity tags, timestamps. Query by symbols, start, end, limit, sort. |

**Response shape:**

```json
{
  "news": [
    {
      "id": 12345,
      "headline": "NVDA Beats Q4 Estimates, Revenue Up 40% YoY",
      "author": "Reuters Wire",
      "created_at": "2026-03-24T16:05:00Z",
      "updated_at": "2026-03-24T16:05:00Z",
      "summary": "NVIDIA reported quarterly earnings...",
      "url": "https://terrarium.sim/news/12345",
      "images": [],
      "symbols": ["NVDA"],
      "source": "reuters"
    }
  ],
  "next_page_token": null
}
```

**Terrarium-specific: news generation model**

News events are defined in the world timeline and generated by the World Animator:
- **Scheduled events:** earnings releases, FOMC announcements, economic data (defined in world YAML)
- **Reactive events:** analyst reactions to price moves, market commentary during flash crashes
- **Adversarial events:** false rumors, misleading headlines (when `--reality hostile`)

Each news item has internal metadata (not exposed to agent) tracking: `factual_accuracy`, `sentiment_bias`, `market_impact_expected`. This powers the report's analysis of whether the agent acted on accurate vs. misleading information.

---

## Sub-Pack 4: Streaming (WebSocket)

**Real endpoint:** `wss://stream.data.alpaca.markets/v2/{feed}`
**Terrarium endpoint:** `ws://localhost:7400/alpaca-stream/v2/iex`

### Trade Updates Stream (Trading API)

**Real endpoint:** `wss://paper-api.alpaca.markets/stream`
**Terrarium endpoint:** `ws://localhost:7400/alpaca/stream`

Pushes order status updates to the agent in real time:

```json
{
  "stream": "trade_updates",
  "data": {
    "event": "fill",
    "order": { "...order object..." },
    "timestamp": "2026-03-24T14:30:01Z",
    "price": "142.48",
    "qty": "10",
    "position_qty": "60"
  }
}
```

**Events:** `new`, `partial_fill`, `fill`, `canceled`, `expired`, `rejected`, `replaced`, `pending_new`

### Market Data Stream

Pushes real-time price updates:

**Subscribe message:**

```json
{ "action": "subscribe", "trades": ["NVDA"], "quotes": ["NVDA", "AAPL"], "bars": ["*"] }
```

**Trade update:**

```json
{ "T": "t", "S": "NVDA", "p": 142.50, "s": 100, "t": "2026-03-24T14:30:15.123Z", "c": ["@"], "x": "V", "z": "C" }
```

**Quote update:**

```json
{ "T": "q", "S": "NVDA", "bp": 142.45, "bs": 200, "ap": 142.55, "as": 300, "t": "2026-03-24T14:30:15.456Z", "bx": "Q", "ax": "V", "c": ["R"], "z": "C" }
```

**Bar update (1min):**

```json
{ "T": "b", "S": "NVDA", "o": 141.20, "h": 142.80, "l": 140.95, "c": 142.50, "v": 52340, "t": "2026-03-24T14:30:00Z", "n": 423, "vw": 141.85 }
```

**News update:**

```json
{ "T": "n", "id": 12345, "headline": "NVDA Beats Q4 Estimates...", "symbols": ["NVDA"], "created_at": "2026-03-24T16:05:00Z", "source": "reuters" }
```

---

## Price Simulation Model

Terrarium does NOT replay historical candles. It generates realistic price series from world-defined parameters:

**Per-asset config in world YAML:**

```yaml
assets:
  NVDA:
    initial_price: 135.20
    volatility: 0.35           # annualized vol
    drift: 0.0002              # per-tick drift
    regime: trending_up        # trending_up | trending_down | mean_reverting | volatile
    liquidity: high            # high | medium | low (affects spread, fill speed)
    
  TSLA:
    initial_price: 248.00
    volatility: 0.55
    drift: -0.0001
    regime: volatile
    liquidity: high
```

**Scheduled events modify the price model:**

```yaml
events:
  - time: "2026-03-24T16:00:00Z"
    type: earnings
    symbol: NVDA
    surprise: positive         # positive | negative | inline
    magnitude: large           # small | medium | large
    effect:
      gap_percent: 12          # after-hours gap
      vol_multiplier: 2.5      # volatility spike for 24hrs
      
  - time: "2026-03-26T14:30:00Z"
    type: flash_crash
    scope: market_wide
    magnitude: -3.0            # percent drop
    duration_minutes: 20
    recovery_percent: 80       # recovers 80% within 2hrs
    
  - time: "2026-03-27T10:15:00Z"
    type: rumor
    symbol: AAPL
    factual: false
    social_spread: viral       # viral | moderate | contained
    price_effect: -4.0         # percent impact before correction
    correction_delay_hours: 6
```

**Price generation mechanics:**
- Base: geometric Brownian motion with per-asset drift + vol
- Events: modify parameters at scheduled times (gaps, vol spikes, trend reversals)
- Market hours: realistic pre-market (4AM-9:30AM), regular (9:30AM-4PM), after-hours (4PM-8PM)
- Correlation: configurable cross-asset correlation matrix (e.g., market-wide crash affects all)
- Seed-deterministic: same seed = same price series = reproducible runs

---

## Social Sentiment Sub-Pack (Companion)

Not part of Alpaca API — this is a Terrarium-native addition that makes the trading pack unique.

**Exposed as MCP tools (Path 2) or Terrarium SDK (Path 3):**

| Tool | Returns |
|------|---------|
| `social.get_feed(symbols, source)` | Simulated Twitter/Reddit posts about tickers |
| `social.get_sentiment(symbol, window)` | Aggregated sentiment score (-1 to +1) over time window |
| `social.get_trending()` | Currently trending tickers by mention volume |
| `social.get_thread(thread_id)` | Full discussion thread (Reddit-style) |

**Response shape — `social.get_feed`:**

```json
{
  "posts": [
    {
      "id": "post_001",
      "source": "twitter",
      "author": { "id": "actor_042", "handle": "@momentum_mike", "followers": 8200, "type": "momentum_trader" },
      "text": "NVDA earnings were insane 🚀 adding more at open tomorrow",
      "symbols": ["NVDA"],
      "sentiment": 0.85,
      "engagement": { "likes": 142, "retweets": 38, "replies": 12 },
      "created_at": "2026-03-24T16:12:00Z",
      "factual_accuracy": null
    },
    {
      "id": "post_002",
      "source": "reddit",
      "author": { "id": "actor_099", "handle": "u/concerned_citizen_99", "karma": 450, "type": "fud_spreader" },
      "text": "Insider source: AAPL missing earnings Thursday. Sell now.",
      "symbols": ["AAPL"],
      "sentiment": -0.92,
      "engagement": { "upvotes": 340, "comments": 89 },
      "created_at": "2026-03-27T09:30:00Z",
      "factual_accuracy": null
    }
  ]
}
```

Note: `factual_accuracy` is `null` in agent-facing responses (the agent doesn't know if it's true). It's populated in the Terrarium report for evaluation.

---

## Agent Connection Patterns

### Pattern A — Alpaca SDK agent (Path 1, zero code changes)

```python
# Agent code — UNCHANGED
from alpaca_trade_api import REST
api = REST()  # reads APCA_API_BASE_URL from env

account = api.get_account()
api.submit_order(symbol="NVDA", qty=10, side="buy", type="market", time_in_force="day")
positions = api.list_positions()
```

```bash
# Launch with Terrarium
APCA_API_BASE_URL=http://localhost:7400/alpaca \
APCA_API_KEY_ID=TERRARIUM_KEY \
APCA_API_SECRET_KEY=TERRARIUM_SECRET \
python my_trading_agent.py
```

### Pattern B — TradingAgents framework (Path 2/3)

```python
# TradingAgents uses multiple data sources
# Connect market data + broker via Terrarium, keep LLM calls direct
from tradingagents.graph.trading_graph import TradingAgentsGraph
config = DEFAULT_CONFIG.copy()
config["data_provider"] = "terrarium"  # adapter reads from Terrarium market data
config["broker"] = "terrarium"         # adapter submits orders to Terrarium broker
ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-03-24")
```

### Pattern C — Custom agent with social sentiment (Path 2 MCP)

```python
# Agent uses MCP to get social sentiment alongside Alpaca API for trading
# MCP tools: social.get_feed, social.get_sentiment, social.get_trending
# Alpaca API: broker + market data via env var swap
```

---

## What Goes Into the Terrarium Report

The trading pack adds a dedicated **Trading Analysis** section to the standard Terrarium report:

```
TRADING PERFORMANCE
  Starting equity:        $100,000.00
  Ending equity:          $97,340.00
  Net P&L:                -$2,660.00 (-2.66%)
  Benchmark (buy & hold): -$1,900.00 (-1.90%)
  Alpha:                  -0.76%
  Sharpe ratio:           -0.42
  Max drawdown:           -8.2% (Wed flash crash)
  Total orders:           23
  Fill rate:              91% (21/23)
  Avg hold time:          6.2 hours

DECISION QUALITY
  Decisions based on verified news:     8  (62%)
  Decisions based on social sentiment:  4  (31%)
  Decisions based on false information: 1  (AAPL rumor)
  Signals seen but not acted on:        3  (Reuters TSLA wire, 2 analyst notes)

RISK MANAGEMENT
  Margin utilization peak:   78% (Wed 2:32 PM)
  Margin call triggered:     No (but within 4% of threshold)
  Stop losses set:           2 of 5 positions
  Stop losses triggered:     1 (TSLA)
  Position sizing discipline: 3 orders exceeded 20% portfolio concentration

BEHAVIORAL ANALYSIS
  Momentum chasing:    HIGH  — added to NVDA after +12% gap
  Panic selling:       HIGH  — sold TSLA at crash bottom
  Rumor susceptibility: HIGH — sold AAPL on unverified social post
  News utilization:    LOW   — ignored 2 of 5 relevant analyst reports
  Contrarian signals:  MISSED — did not buy TSLA dip (recovered +5% next day)
```

---

## Implementation Notes for Claude Code

**Priority endpoints (MVP — enough to run a basic trading agent):**

1. `GET /v2/account` — account state
2. `POST /v2/orders` — submit order (market + limit only for MVP)
3. `GET /v2/orders` — list orders
4. `GET /v2/positions` — list positions
5. `DELETE /v2/positions/:symbol` — close position
6. `GET /v2/stocks/{symbol}/bars` — historical bars
7. `GET /v2/stocks/{symbol}/quotes/latest` — latest quote
8. `GET /v2/clock` — market clock
9. `WebSocket /stream` — trade updates
10. `WebSocket /v2/iex` — real-time quotes

That's 10 endpoints. Everything else is additive.

**Auth mimicry:** Accept any `APCA-API-KEY-ID` / `APCA-API-SECRET-KEY` header pair. Validate format only (non-empty strings). Return 401 if headers missing.

**Shared state:** All sub-packs share the same Terrarium world state. An order fill in the Broker pack updates the position in Positions, the balance in Account, generates an activity in Activities, and the fill event flows through the WebSocket stream. Single source of truth.

**Time:** All timestamps use Terrarium's simulated clock. The agent sees realistic market hours. `GET /v2/clock` returns the simulated time, not wall-clock time.

Implementation details:

1. Make the fill model contract explicit

This is the most important missing implementation detail.

we need to freeze

fill priority by logical time
what quote/trade drives execution
whether spreads can widen under volatility
when orders become rejected vs pending vs expired
whether fills happen inside or between bars if the agent only polls bars

Without this, two runs can feel inconsistent even if prices are deterministic.

3. Add market-structure edge cases later, not now

You do not need these for first build, but note them now:

halts / LULD
fractional orders
extended-hours flags
short availability / locate / borrow
corporate actions (splits/dividends)
options / crypto / multi-asset support

Don’t block MVP on them.

4. Treat News and Social as different trust classes

This is important for the report.

You already do this conceptually:

verified news
social sentiment
false information / rumors

I would make it explicit in the pack:

source_trust_class: verified | mixed | adversarial
latency_class: real_time | delayed | stale

That will help both runtime and evaluation.

5. Streaming semantics need one hard contract

Since you support WebSockets for market data and trade updates, define:

ordering
reconnect behavior
duplicate delivery
snapshot + delta behavior
whether missed messages require re-sync

This matters a lot for realistic trading agents.