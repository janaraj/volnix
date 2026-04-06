"""Optional utility for generating deterministic price series.

NOT called by any engine or the compilation pipeline. The standard path
is: WorldDataGenerator asks LLM to generate bar/quote entities, same
as every other pack.

This utility is for advanced users who want mathematically precise
GBM-based prices instead of LLM-generated ones. Call it from a custom
script or test to produce bar entities that can be loaded into state.

Usage::

    from volnix.packs.verified.alpaca.price_model import (
        generate_price_series,
        generate_quote_from_price,
        generate_initial_account,
    )

    bars = generate_price_series("NVDA", initial_price=135.20,
                                 volatility=0.35, drift=0.0002,
                                 num_bars=100, timeframe_minutes=60,
                                 seed=42)
"""

from __future__ import annotations

import math
import random
import uuid
from datetime import UTC, datetime, timedelta


def generate_price_series(
    symbol: str,
    initial_price: float,
    volatility: float,
    drift: float,
    num_bars: int,
    timeframe_minutes: int,
    seed: int,
    start_time: datetime | None = None,
    events: list[dict] | None = None,
) -> list[dict]:
    """Generate deterministic OHLCV bars using geometric Brownian motion.

    Same seed + same params = same price series every time.

    Args:
        symbol: Stock symbol (e.g. "NVDA").
        initial_price: Starting price.
        volatility: Annualized volatility (e.g. 0.35 = 35%).
        drift: Per-tick drift (e.g. 0.0002 = slight uptrend).
        num_bars: Number of bars to generate.
        timeframe_minutes: Minutes per bar (1, 5, 15, 60, 1440).
        seed: Random seed for deterministic generation.
        start_time: Starting timestamp (defaults to now UTC).
        events: Optional list of event dicts that modify the model.
            Each: {"bar_index": int, "gap_percent": float, "vol_multiplier": float}

    Returns:
        List of bar entity dicts ready for State Engine population.
    """
    rng = random.Random(seed)
    dt = timeframe_minutes / (252 * 6.5 * 60)  # fraction of trading year
    price = initial_price
    base_time = start_time or datetime.now(UTC)
    event_map = {e["bar_index"]: e for e in (events or [])}
    timeframe_label = _timeframe_label(timeframe_minutes)

    bars: list[dict] = []
    for i in range(num_bars):
        # Check for scheduled events
        evt = event_map.get(i)
        local_vol = volatility
        if evt:
            gap_pct = evt.get("gap_percent", 0)
            price *= 1 + gap_pct / 100
            local_vol *= evt.get("vol_multiplier", 1.0)

        # GBM step
        z = rng.gauss(0, 1)
        r = drift * dt + local_vol * math.sqrt(dt) * z
        close = price * math.exp(r)

        # Generate OHLV from close
        intra_vol = abs(rng.gauss(0, 0.003))
        high = close * (1 + intra_vol)
        low = close * (1 - abs(rng.gauss(0, 0.003)))
        open_ = price * (1 + rng.gauss(0, 0.001))

        # Ensure OHLC consistency
        high = max(high, open_, close)
        low = min(low, open_, close)

        volume = max(100, int(rng.gauss(1_000_000, 200_000)))
        trade_count = max(10, int(volume / rng.randint(80, 150)))
        vwap = round((open_ + high + low + close) / 4, 4)

        ts = base_time + timedelta(minutes=i * timeframe_minutes)

        bars.append(
            {
                "id": f"bar_{symbol.lower()}_{i:04d}",
                "symbol": symbol,
                "timestamp": ts.isoformat(),
                "open": round(open_, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close, 4),
                "volume": volume,
                "trade_count": trade_count,
                "vwap": round(vwap, 4),
                "timeframe": timeframe_label,
            }
        )

        price = close

    return bars


def generate_quote_from_price(
    symbol: str,
    price: float,
    spread_bps: int = 10,
    seed: int = 42,
    timestamp: datetime | None = None,
) -> dict:
    """Generate a deterministic bid/ask quote from a reference price.

    Args:
        symbol: Stock symbol.
        price: Reference price (midpoint).
        spread_bps: Spread in basis points (10 = 0.1%).
        seed: Random seed.
        timestamp: Quote timestamp.

    Returns:
        Quote entity dict.
    """
    rng = random.Random(seed)
    half_spread = price * spread_bps / 20000
    bid = round(price - half_spread, 4)
    ask = round(price + half_spread, 4)
    ts = timestamp or datetime.now(UTC)

    return {
        "id": f"q_{symbol.lower()}_{uuid.uuid4().hex[:8]}",
        "symbol": symbol,
        "timestamp": ts.isoformat(),
        "bid_price": bid,
        "bid_size": rng.randint(100, 500),
        "bid_exchange": rng.choice(["Q", "N", "P"]),
        "ask_price": ask,
        "ask_size": rng.randint(100, 500),
        "ask_exchange": rng.choice(["V", "Q", "N"]),
        "conditions": ["R"],
    }


def generate_initial_account(
    account_id: str = "acc_terra_001",
    initial_cash: float = 100000.0,
    currency: str = "USD",
) -> dict:
    """Generate a fully populated Alpaca account entity.

    Args:
        account_id: Account entity ID.
        initial_cash: Starting cash balance.
        currency: Account currency.

    Returns:
        Account entity dict.
    """
    return {
        "id": account_id,
        "status": "ACTIVE",
        "currency": currency,
        "buying_power": initial_cash * 2,  # 2x for margin
        "cash": initial_cash,
        "portfolio_value": initial_cash,
        "equity": initial_cash,
        "last_equity": initial_cash,
        "long_market_value": 0,
        "short_market_value": 0,
        "initial_margin": 0,
        "maintenance_margin": 0,
        "daytrade_count": 0,
        "pattern_day_trader": False,
        "trading_blocked": False,
        "transfers_blocked": False,
        "account_blocked": False,
    }


def _timeframe_label(minutes: int) -> str:
    """Convert minutes to Alpaca timeframe label."""
    labels = {
        1: "1Min",
        5: "5Min",
        15: "15Min",
        60: "1Hour",
        1440: "1Day",
    }
    return labels.get(minutes, f"{minutes}Min")
