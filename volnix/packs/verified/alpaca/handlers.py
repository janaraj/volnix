"""Action handlers for the trading service pack.

Handlers import ONLY from volnix.core (types, context). They NEVER
import from persistence/, engines/, or bus/.

Simulates the Alpaca Markets API surface. 22 handlers:
- 8 broker, 4 market data, 2 reference, 1 news, 3 social sentiment
- 4 Animator tools (update_quote, create_bar, create_news, update_sentiment)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from volnix.core.context import ResponseProposal
from volnix.core.types import EntityId, StateDelta

SLIPPAGE_BPS = 10  # 0.1% = 10 basis points, deterministic


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _alpaca_error(code: int, message: str) -> dict[str, Any]:
    return {"code": code, "message": message}


def _find_entity(entities: list[dict], eid: str) -> dict | None:
    for e in entities:
        if e.get("id") == eid:
            return e
    return None


def _find_by_symbol(entities: list[dict], symbol: str) -> dict | None:
    for e in entities:
        if e.get("symbol") == symbol:
            return e
    return None


def _compute_total_position_value(
    positions: list[dict],
    quotes: list[dict],
    exclude_symbol: str | None = None,
) -> float:
    """Sum market_value across all positions using live quotes.

    Args:
        positions: All position entities from state.
        quotes: All quote entities from state.
        exclude_symbol: Optionally exclude one symbol (for close_position).

    Returns:
        Total market value across all positions.
    """
    total = 0.0
    for pos in positions:
        sym = pos.get("symbol", "")
        if exclude_symbol and sym == exclude_symbol:
            continue
        q = _find_by_symbol(quotes, sym)
        if q:
            cp = float(q.get("ask_price", 0))
        else:
            cp = float(pos.get("current_price", 0))
        total += cp * float(pos.get("qty", 0))
    return round(total, 2)


def _compute_fill_price(
    quote: dict,
    side: str,
    order_type: str,
    limit_price: float | None,
    stop_price: float | None,
) -> tuple[float | None, str]:
    """Deterministic fill logic. Returns (fill_price, new_status) or (None, "accepted")."""
    ask = float(quote.get("ask_price", 0))
    bid = float(quote.get("bid_price", 0))
    slippage = SLIPPAGE_BPS / 10000

    if order_type == "market":
        if side == "buy":
            return round(ask * (1 + slippage), 4), "filled"
        else:
            return round(bid * (1 - slippage), 4), "filled"

    elif order_type == "limit":
        if side == "buy" and limit_price is not None and ask <= limit_price:
            return round(min(ask, limit_price), 4), "filled"
        elif side == "sell" and limit_price is not None and bid >= limit_price:
            return round(max(bid, limit_price), 4), "filled"
        return None, "accepted"  # conditions not met, order waits

    elif order_type == "stop":
        if side == "buy" and stop_price is not None and ask >= stop_price:
            return round(ask * (1 + slippage), 4), "filled"
        elif side == "sell" and stop_price is not None and bid <= stop_price:
            return round(bid * (1 - slippage), 4), "filled"
        return None, "accepted"

    elif order_type == "stop_limit":
        triggered = False
        if side == "buy" and stop_price is not None and ask >= stop_price:
            triggered = True
        elif side == "sell" and stop_price is not None and bid <= stop_price:
            triggered = True
        if triggered and limit_price is not None:
            if side == "buy" and ask <= limit_price:
                return round(min(ask, limit_price), 4), "filled"
            elif side == "sell" and bid >= limit_price:
                return round(max(bid, limit_price), 4), "filled"
        return None, "accepted"

    return None, "rejected"


def _build_position_delta(
    existing_pos: dict | None,
    symbol: str,
    asset_id: str,
    fill_price: float,
    fill_qty: float,
    side: str,
    quote: dict,
) -> tuple[StateDelta, dict]:
    """Build position create or update delta. Returns (delta, position_fields)."""
    current_price = float(quote.get("ask_price", fill_price))
    lastday_price = float(quote.get("bid_price", fill_price))

    if existing_pos is None:
        pos_id = _new_id("pos")
        cost_basis = round(fill_price * fill_qty, 2)
        market_value = round(current_price * fill_qty, 2)
        fields: dict[str, Any] = {
            "id": pos_id,
            "asset_id": asset_id,
            "symbol": symbol,
            "exchange": "NASDAQ",
            "asset_class": "us_equity",
            "avg_entry_price": fill_price,
            "qty": fill_qty,
            "side": "long" if side == "buy" else "short",
            "market_value": market_value,
            "cost_basis": cost_basis,
            "unrealized_pl": round(market_value - cost_basis, 2),
            "unrealized_plpc": (
                round((market_value - cost_basis) / cost_basis, 6) if cost_basis else 0
            ),
            "current_price": current_price,
            "lastday_price": lastday_price,
            "change_today": (
                round((current_price - lastday_price) / lastday_price, 6) if lastday_price else 0
            ),
        }
        return (
            StateDelta(
                entity_type="alpaca_position",
                entity_id=EntityId(pos_id),
                operation="create",
                fields=fields,
            ),
            fields,
        )
    else:
        # Update existing position -- weighted average entry price
        old_qty = float(existing_pos.get("qty", 0))
        old_avg = float(existing_pos.get("avg_entry_price", 0))
        if side == "buy" and existing_pos.get("side") == "long":
            new_qty = old_qty + fill_qty
            new_avg = round((old_avg * old_qty + fill_price * fill_qty) / new_qty, 4)
        elif side == "sell" and existing_pos.get("side") == "long":
            new_qty = old_qty - fill_qty
            new_avg = old_avg  # avg doesn't change on partial close
        else:
            new_qty = old_qty + fill_qty
            new_avg = round((old_avg * old_qty + fill_price * fill_qty) / new_qty, 4)

        # If qty reaches zero, DELETE the position instead of updating
        if new_qty <= 0:
            return (
                StateDelta(
                    entity_type="alpaca_position",
                    entity_id=EntityId(existing_pos["id"]),
                    operation="delete",
                    fields={"status": "closed"},
                    previous_fields={"qty": old_qty},
                ),
                {"market_value": 0, "qty": 0},
            )

        cost_basis = round(new_avg * new_qty, 2)
        market_value = round(current_price * new_qty, 2)
        update_fields: dict[str, Any] = {
            "avg_entry_price": new_avg,
            "qty": new_qty,
            "market_value": market_value,
            "cost_basis": cost_basis,
            "unrealized_pl": round(market_value - cost_basis, 2),
            "unrealized_plpc": (
                round((market_value - cost_basis) / cost_basis, 6) if cost_basis else 0
            ),
            "current_price": current_price,
        }
        return (
            StateDelta(
                entity_type="alpaca_position",
                entity_id=EntityId(existing_pos["id"]),
                operation="update",
                fields=update_fields,
                previous_fields={
                    "qty": old_qty,
                    "avg_entry_price": old_avg,
                },
            ),
            {**existing_pos, **update_fields},
        )


# ---------------------------------------------------------------------------
# Handler 1: GET /v2/account (READ)
# ---------------------------------------------------------------------------


async def handle_get_account(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    accounts = state.get("alpaca_accounts", [])
    if not accounts:
        return ResponseProposal(
            response_body=_alpaca_error(404, "Account not found"),
        )
    caller_id = state.get("_actor_id", "")
    account = next(
        (a for a in accounts if a.get("game_owner_id") == caller_id),
        accounts[0],
    )
    return ResponseProposal(response_body=account)


# ---------------------------------------------------------------------------
# Handler 2: POST /v2/orders (MUTATING -- up to 4 deltas)
# ---------------------------------------------------------------------------


async def handle_create_order(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    symbol = input_data["symbol"]
    qty = float(input_data["qty"])
    side = input_data["side"]
    order_type = input_data["type"]
    tif = input_data["time_in_force"]
    now = _now_iso()
    deltas: list[StateDelta] = []

    # Validate qty and prices
    if qty <= 0:
        return ResponseProposal(
            response_body=_alpaca_error(422, "qty must be greater than 0"),
        )
    raw_limit = input_data.get("limit_price")
    raw_stop = input_data.get("stop_price")
    if raw_limit is not None and float(raw_limit) < 0:
        return ResponseProposal(
            response_body=_alpaca_error(422, "limit_price must be >= 0"),
        )
    if raw_stop is not None and float(raw_stop) < 0:
        return ResponseProposal(
            response_body=_alpaca_error(422, "stop_price must be >= 0"),
        )

    # Validate asset
    asset = _find_by_symbol(state.get("alpaca_assets", []), symbol)
    if asset is None or not asset.get("tradable", False):
        return ResponseProposal(
            response_body=_alpaca_error(422, f"Asset '{symbol}' not tradable"),
        )

    # Validate account — prefer account owned by calling actor (game mode)
    accounts = state.get("alpaca_accounts", [])
    if not accounts:
        return ResponseProposal(
            response_body=_alpaca_error(403, "No account"),
        )
    caller_id = state.get("_actor_id", "")
    account = next(
        (a for a in accounts if a.get("game_owner_id") == caller_id),
        accounts[0],
    )
    if account.get("trading_blocked"):
        return ResponseProposal(
            response_body=_alpaca_error(403, "Trading blocked"),
        )

    # Look up quote
    quote = _find_by_symbol(state.get("alpaca_quotes", []), symbol)
    if quote is None:
        return ResponseProposal(
            response_body=_alpaca_error(422, f"No quote for '{symbol}'"),
        )

    # Check buying power for buys
    limit_price = input_data.get("limit_price")
    stop_price = input_data.get("stop_price")
    if side == "buy":
        est_cost = qty * float(quote.get("ask_price", 0))
        if est_cost > float(account.get("buying_power", 0)):
            return ResponseProposal(
                response_body=_alpaca_error(403, "Insufficient buying power"),
            )

    # Compute fill
    fill_price, new_status = _compute_fill_price(
        quote,
        side,
        order_type,
        float(limit_price) if limit_price else None,
        float(stop_price) if stop_price else None,
    )

    # Build order entity
    order_id = _new_id("ord")
    order_fields: dict[str, Any] = {
        "id": order_id,
        "client_order_id": input_data.get("client_order_id", order_id),
        "created_at": now,
        "submitted_at": now,
        "filled_at": now if new_status == "filled" else None,
        "asset_id": asset["id"],
        "symbol": symbol,
        "qty": qty,
        "filled_qty": qty if new_status == "filled" else 0,
        "filled_avg_price": fill_price,
        "type": order_type,
        "side": side,
        "time_in_force": tif,
        "limit_price": float(limit_price) if limit_price is not None else None,
        "stop_price": float(stop_price) if stop_price is not None else None,
        "trail_price": float(input_data["trail_price"])
        if input_data.get("trail_price") is not None
        else None,
        "trail_percent": float(input_data["trail_percent"])
        if input_data.get("trail_percent") is not None
        else None,
        "status": new_status,
        "order_class": "simple",
    }
    deltas.append(
        StateDelta(
            entity_type="alpaca_order",
            entity_id=EntityId(order_id),
            operation="create",
            fields=order_fields,
        ),
    )

    if new_status == "filled" and fill_price is not None:
        # Position delta
        existing_pos = _find_by_symbol(state.get("alpaca_positions", []), symbol)
        pos_delta, pos_fields = _build_position_delta(
            existing_pos, symbol, asset["id"], fill_price, qty, side, quote
        )
        deltas.append(pos_delta)

        # Account delta -- equity must include ALL positions
        cost = round(fill_price * qty, 2)
        old_cash = float(account.get("cash", 0))
        old_bp = float(account.get("buying_power", 0))
        if side == "buy":
            new_cash = round(old_cash - cost, 2)
            new_bp = round(old_bp - cost, 2)
        else:
            new_cash = round(old_cash + cost, 2)
            new_bp = round(old_bp + cost, 2)
        # Sum existing positions' market value (excluding the one we
        # just created/updated, since pos_fields has the fresh value)
        other_pos_value = _compute_total_position_value(
            state.get("alpaca_positions", []),
            state.get("alpaca_quotes", []),
            exclude_symbol=symbol,
        )
        new_position_value = float(pos_fields.get("market_value", 0))
        total_long_value = round(other_pos_value + new_position_value, 2)
        acct_fields: dict[str, Any] = {
            "cash": new_cash,
            "buying_power": new_bp,
            "equity": round(new_cash + total_long_value, 2),
            "portfolio_value": round(new_cash + total_long_value, 2),
            "long_market_value": total_long_value,
        }
        deltas.append(
            StateDelta(
                entity_type="alpaca_account",
                entity_id=EntityId(account["id"]),
                operation="update",
                fields=acct_fields,
                previous_fields={"cash": old_cash, "buying_power": old_bp},
            ),
        )

        # Activity delta
        activity_id = _new_id("act")
        deltas.append(
            StateDelta(
                entity_type="alpaca_activity",
                entity_id=EntityId(activity_id),
                operation="create",
                fields={
                    "id": activity_id,
                    "activity_type": "FILL",
                    "date": now,
                    "qty": qty,
                    "price": fill_price,
                    "symbol": symbol,
                    "side": side,
                    "order_id": order_id,
                    "cum_qty": qty,
                    "leaves_qty": 0,
                    "type": order_type,
                },
            ),
        )

    return ResponseProposal(response_body=order_fields, proposed_state_deltas=deltas)


# ---------------------------------------------------------------------------
# Handler 3: GET /v2/orders (READ with filters)
# ---------------------------------------------------------------------------


async def handle_list_orders(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    orders = list(state.get("alpaca_orders", []))
    status_filter = input_data.get("status")
    if status_filter:
        if status_filter == "open":
            orders = [
                o for o in orders if o.get("status") in ("new", "accepted", "partially_filled")
            ]
        elif status_filter == "closed":
            orders = [
                o
                for o in orders
                if o.get("status") in ("filled", "cancelled", "expired", "rejected")
            ]
        else:
            orders = [o for o in orders if o.get("status") == status_filter]
    direction = input_data.get("direction", "desc")
    orders.sort(
        key=lambda o: o.get("created_at", ""),
        reverse=(direction == "desc"),
    )
    limit = int(input_data.get("limit", 50))
    return ResponseProposal(response_body={"orders": orders[:limit]})


# ---------------------------------------------------------------------------
# Handler 4: GET /v2/orders/{id} (READ)
# ---------------------------------------------------------------------------


async def handle_get_order(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    order = _find_entity(state.get("alpaca_orders", []), input_data["id"])
    if order is None:
        return ResponseProposal(
            response_body=_alpaca_error(404, "Order not found"),
        )
    return ResponseProposal(response_body=order)


# ---------------------------------------------------------------------------
# Handler 5: DELETE /v2/orders/{id} (MUTATING)
# ---------------------------------------------------------------------------


async def handle_cancel_order(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    order = _find_entity(state.get("alpaca_orders", []), input_data["id"])
    if order is None:
        return ResponseProposal(
            response_body=_alpaca_error(404, "Order not found"),
        )
    # State machine: only "accepted" and "partially_filled" can be cancelled.
    # "new" orders transition to "accepted" or "rejected" first.
    if order.get("status") not in ("accepted", "partially_filled"):
        return ResponseProposal(
            response_body=_alpaca_error(
                422,
                f"Cannot cancel order in '{order.get('status')}' status",
            ),
        )
    delta = StateDelta(
        entity_type="alpaca_order",
        entity_id=EntityId(order["id"]),
        operation="update",
        fields={"status": "cancelled", "canceled_at": _now_iso()},
        previous_fields={"status": order.get("status")},
    )
    return ResponseProposal(response_body={}, proposed_state_deltas=[delta])


# ---------------------------------------------------------------------------
# Handler 6: GET /v2/positions (READ -- enriches with live P&L from quotes)
# ---------------------------------------------------------------------------


async def handle_list_positions(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    positions = list(state.get("alpaca_positions", []))
    quotes = state.get("alpaca_quotes", [])
    enriched: list[dict[str, Any]] = []
    for pos in positions:
        q = _find_by_symbol(quotes, pos.get("symbol", ""))
        if q:
            cp = float(q.get("ask_price", pos.get("current_price", 0)))
            qty = float(pos.get("qty", 0))
            avg = float(pos.get("avg_entry_price", 0))
            mv = round(cp * qty, 2)
            cb = round(avg * qty, 2)
            pos = {
                **pos,
                "current_price": cp,
                "market_value": mv,
                "cost_basis": cb,
                "unrealized_pl": round(mv - cb, 2),
                "unrealized_plpc": round((mv - cb) / cb, 6) if cb else 0,
            }
        enriched.append(pos)
    return ResponseProposal(response_body={"positions": enriched})


# ---------------------------------------------------------------------------
# Handler 7: GET /v2/positions/{symbol} (READ -- enriches with live P&L)
# ---------------------------------------------------------------------------


async def handle_get_position(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    pos = _find_by_symbol(state.get("alpaca_positions", []), input_data["symbol"])
    if pos is None:
        return ResponseProposal(
            response_body=_alpaca_error(
                404,
                f"Position not found for '{input_data['symbol']}'",
            ),
        )
    # Enrich with live quote (same as list_positions)
    q = _find_by_symbol(state.get("alpaca_quotes", []), pos.get("symbol", ""))
    if q:
        cp = float(q.get("ask_price", 0))
        qty = float(pos.get("qty", 0))
        avg = float(pos.get("avg_entry_price", 0))
        mv = round(cp * qty, 2)
        cb = round(avg * qty, 2)
        pos = {
            **pos,
            "current_price": cp,
            "market_value": mv,
            "cost_basis": cb,
            "unrealized_pl": round(mv - cb, 2),
            "unrealized_plpc": round((mv - cb) / cb, 6) if cb else 0,
        }
    return ResponseProposal(response_body=pos)


# ---------------------------------------------------------------------------
# Handler 8: DELETE /v2/positions/{symbol} (MUTATING)
# ---------------------------------------------------------------------------


async def handle_close_position(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    symbol = input_data["symbol"]
    pos = _find_by_symbol(state.get("alpaca_positions", []), symbol)
    if pos is None:
        return ResponseProposal(
            response_body=_alpaca_error(404, f"No position for '{symbol}'"),
        )
    quote = _find_by_symbol(state.get("alpaca_quotes", []), symbol)
    if quote is None:
        return ResponseProposal(
            response_body=_alpaca_error(422, f"No quote for '{symbol}'"),
        )
    accounts = state.get("alpaca_accounts", [])
    if not accounts:
        return ResponseProposal(
            response_body=_alpaca_error(403, "No account"),
        )
    account = accounts[0]
    qty = float(pos.get("qty", 0))
    close_side = "sell" if pos.get("side") == "long" else "buy"
    # Market fill
    fill_price, _ = _compute_fill_price(quote, close_side, "market", None, None)
    now = _now_iso()
    deltas: list[StateDelta] = []

    # Order
    order_id = _new_id("ord")
    order_fields: dict[str, Any] = {
        "id": order_id,
        "symbol": symbol,
        "qty": qty,
        "side": close_side,
        "type": "market",
        "status": "filled",
        "filled_qty": qty,
        "filled_avg_price": fill_price,
        "filled_at": now,
        "created_at": now,
        "submitted_at": now,
        "time_in_force": "day",
        "order_class": "simple",
        "asset_id": pos.get("asset_id", ""),
    }
    deltas.append(
        StateDelta(
            entity_type="alpaca_order",
            entity_id=EntityId(order_id),
            operation="create",
            fields=order_fields,
        ),
    )

    # Delete position
    deltas.append(
        StateDelta(
            entity_type="alpaca_position",
            entity_id=EntityId(pos["id"]),
            operation="delete",
            fields={"status": "closed"},
        ),
    )

    # Update account -- equity must reflect position being closed
    proceeds = round(fill_price * qty, 2) if fill_price else 0.0
    old_cash = float(account.get("cash", 0))
    new_cash = (
        round(old_cash + proceeds, 2) if close_side == "sell" else round(old_cash - proceeds, 2)
    )
    # Remaining positions' value (excluding the one being closed)
    remaining_pos_value = _compute_total_position_value(
        state.get("alpaca_positions", []),
        state.get("alpaca_quotes", []),
        exclude_symbol=symbol,
    )
    deltas.append(
        StateDelta(
            entity_type="alpaca_account",
            entity_id=EntityId(account["id"]),
            operation="update",
            fields={
                "cash": new_cash,
                "buying_power": new_cash,
                "equity": round(new_cash + remaining_pos_value, 2),
                "portfolio_value": round(new_cash + remaining_pos_value, 2),
                "long_market_value": remaining_pos_value,
            },
            previous_fields={"cash": old_cash},
        ),
    )

    # Activity
    act_id = _new_id("act")
    deltas.append(
        StateDelta(
            entity_type="alpaca_activity",
            entity_id=EntityId(act_id),
            operation="create",
            fields={
                "id": act_id,
                "activity_type": "FILL",
                "date": now,
                "qty": qty,
                "price": fill_price,
                "symbol": symbol,
                "side": close_side,
                "order_id": order_id,
            },
        ),
    )

    return ResponseProposal(response_body=order_fields, proposed_state_deltas=deltas)


# ---------------------------------------------------------------------------
# Handler 9: GET /v2/stocks/{symbol}/bars (READ with pagination)
# ---------------------------------------------------------------------------


async def handle_get_bars(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    symbol = input_data["symbol"]
    bars = [b for b in state.get("alpaca_bars", []) if b.get("symbol") == symbol]
    timeframe = input_data.get("timeframe")
    if timeframe:
        bars = [b for b in bars if b.get("timeframe") == timeframe]
    start = input_data.get("start")
    end = input_data.get("end")
    if start:
        bars = [b for b in bars if b.get("timestamp", "") >= start]
    if end:
        bars = [b for b in bars if b.get("timestamp", "") <= end]
    bars.sort(key=lambda b: b.get("timestamp", ""))
    limit = int(input_data.get("limit", 1000))
    paginated = bars[:limit]
    next_token = bars[limit].get("id") if len(bars) > limit else None
    # Alpaca bar format: {t, o, h, l, c, v, n, vw}
    formatted = [
        {
            "t": b.get("timestamp"),
            "o": b.get("open"),
            "h": b.get("high"),
            "l": b.get("low"),
            "c": b.get("close"),
            "v": b.get("volume"),
            "n": b.get("trade_count", 0),
            "vw": b.get("vwap", 0),
        }
        for b in paginated
    ]
    return ResponseProposal(
        response_body={
            "bars": formatted,
            "symbol": symbol,
            "next_page_token": next_token,
        },
    )


# ---------------------------------------------------------------------------
# Handler 10: GET /v2/stocks/{symbol}/quotes/latest (READ)
# ---------------------------------------------------------------------------


async def handle_get_latest_quote(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    quote = _find_by_symbol(state.get("alpaca_quotes", []), input_data["symbol"])
    if quote is None:
        return ResponseProposal(
            response_body=_alpaca_error(404, f"No quote for '{input_data['symbol']}'"),
        )
    formatted = {
        "t": quote.get("timestamp"),
        "bp": quote.get("bid_price"),
        "bs": quote.get("bid_size"),
        "bx": quote.get("bid_exchange", "Q"),
        "ap": quote.get("ask_price"),
        "as": quote.get("ask_size"),
        "ax": quote.get("ask_exchange", "V"),
        "c": quote.get("conditions", ["R"]),
    }
    return ResponseProposal(
        response_body={
            "symbol": input_data["symbol"],
            "quote": formatted,
        },
    )


# ---------------------------------------------------------------------------
# Handler 11: GET /v2/stocks/{symbol}/trades/latest (READ)
# ---------------------------------------------------------------------------


async def handle_get_latest_trade(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    quote = _find_by_symbol(state.get("alpaca_quotes", []), input_data["symbol"])
    if quote is None:
        return ResponseProposal(
            response_body=_alpaca_error(404, f"No trade for '{input_data['symbol']}'"),
        )
    mid = round(
        (float(quote.get("bid_price", 0)) + float(quote.get("ask_price", 0))) / 2,
        4,
    )
    formatted = {
        "t": quote.get("timestamp"),
        "p": mid,
        "s": min(
            int(quote.get("bid_size", 100)),
            int(quote.get("ask_size", 100)),
        ),
        "x": quote.get("ask_exchange", "V"),
        "c": ["@"],
        "z": "C",
    }
    return ResponseProposal(
        response_body={
            "symbol": input_data["symbol"],
            "trade": formatted,
        },
    )


# ---------------------------------------------------------------------------
# Handler 12: GET /v2/stocks/{symbol}/snapshot (READ)
# ---------------------------------------------------------------------------


async def handle_get_snapshot(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    symbol = input_data["symbol"]
    quote = _find_by_symbol(state.get("alpaca_quotes", []), symbol)
    bars = [b for b in state.get("alpaca_bars", []) if b.get("symbol") == symbol]
    bars.sort(key=lambda b: b.get("timestamp", ""), reverse=True)
    latest_bar = bars[0] if bars else None
    prev_bar = bars[1] if len(bars) > 1 else None
    return ResponseProposal(
        response_body={
            "latestQuote": quote,
            "latestTrade": None,
            "minuteBar": latest_bar,
            "dailyBar": latest_bar,
            "prevDailyBar": prev_bar,
        },
    )


# ---------------------------------------------------------------------------
# Handler 13: GET /v2/clock (READ)
# ---------------------------------------------------------------------------


async def handle_get_clock(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    clocks = state.get("alpaca_clocks", [])
    if not clocks:
        return ResponseProposal(
            response_body={
                "timestamp": _now_iso(),
                "is_open": True,
                "next_open": None,
                "next_close": None,
            },
        )
    return ResponseProposal(response_body=clocks[0])


# ---------------------------------------------------------------------------
# Handler 14: GET /v2/assets (READ with filters)
# ---------------------------------------------------------------------------


async def handle_list_assets(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    assets = list(state.get("alpaca_assets", []))
    status_filter = input_data.get("status")
    if status_filter:
        assets = [a for a in assets if a.get("status") == status_filter]
    class_filter = input_data.get("asset_class")
    if class_filter:
        assets = [a for a in assets if a.get("asset_class") == class_filter]
    return ResponseProposal(response_body={"assets": assets})


# ---------------------------------------------------------------------------
# Handler 15: GET /v1beta1/news (READ -- strips internal fields)
# ---------------------------------------------------------------------------

INTERNAL_NEWS_FIELDS = {
    "factual_accuracy",
    "sentiment_bias",
    "market_impact_expected",
}


async def handle_get_news(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    # "alpaca_news" ends with "s", so _pluralize produces "alpaca_newses"
    news = list(state.get("alpaca_newses", []))
    symbols_filter = input_data.get("symbols")
    if symbols_filter:
        symbol_list = [s.strip() for s in symbols_filter.split(",")]
        news = [n for n in news if any(s in n.get("symbols", []) for s in symbol_list)]
    start = input_data.get("start")
    end = input_data.get("end")
    if start:
        news = [n for n in news if n.get("created_at", "") >= start]
    if end:
        news = [n for n in news if n.get("created_at", "") <= end]
    news.sort(key=lambda n: n.get("created_at", ""), reverse=True)
    limit = int(input_data.get("limit", 10))
    paginated = news[:limit]
    # Strip internal metadata -- agent never sees factual_accuracy etc.
    sanitized = [{k: v for k, v in n.items() if k not in INTERNAL_NEWS_FIELDS} for n in paginated]
    next_token = news[limit].get("id") if len(news) > limit else None
    return ResponseProposal(
        response_body={"news": sanitized, "next_page_token": next_token},
    )


# ---------------------------------------------------------------------------
# Handler 16: GET /volnix/social/feed (READ)
# ---------------------------------------------------------------------------


async def handle_social_get_feed(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    # Read from pre-generated social entities (NOT from Reddit/Twitter packs)
    posts = list(state.get("social_sentiments", []))
    symbol = input_data.get("symbol")
    if symbol:
        posts = [p for p in posts if p.get("symbol") == symbol]
    source = input_data.get("source")
    if source:
        posts = [p for p in posts if p.get("source") == source]
    limit = int(input_data.get("limit", 20))
    return ResponseProposal(
        response_body={
            "posts": posts[:limit],
            "count": len(posts[:limit]),
        },
    )


# ---------------------------------------------------------------------------
# Handler 17: GET /volnix/social/sentiment (READ)
# ---------------------------------------------------------------------------


async def handle_social_get_sentiment(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    symbol = input_data["symbol"]
    source = input_data.get("source", "all")
    sentiments = state.get("social_sentiments", [])
    match = None
    for s in sentiments:
        if s.get("symbol") == symbol and s.get("source") == source:
            match = s
            break
    if match is None:
        return ResponseProposal(
            response_body={
                "symbol": symbol,
                "source": source,
                "score": 0.0,
                "post_count": 0,
            },
        )
    return ResponseProposal(response_body=match)


# ---------------------------------------------------------------------------
# Handler 18: GET /volnix/social/trending (READ)
# ---------------------------------------------------------------------------


async def handle_social_get_trending(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    sentiments = list(state.get("social_sentiments", []))
    # Sort by trending_rank (lower = more trending), filter nulls
    ranked = [s for s in sentiments if s.get("trending_rank") is not None]
    ranked.sort(key=lambda s: s.get("trending_rank", 999))
    limit = int(input_data.get("limit", 10))
    return ResponseProposal(
        response_body={
            "trending": ranked[:limit],
            "count": len(ranked[:limit]),
        },
    )


# ---------------------------------------------------------------------------
# Handler 19: PUT /volnix/market/quote (MUTATING -- Animator tool)
# ---------------------------------------------------------------------------


async def handle_update_quote(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    symbol = input_data.get("symbol", "")
    quote = _find_by_symbol(state.get("alpaca_quotes", []), symbol)
    if quote is None:
        return ResponseProposal(
            response_body=_alpaca_error(404, f"No existing quote for '{symbol}'"),
        )
    now = _now_iso()
    update_fields: dict[str, Any] = {"timestamp": now}
    previous_fields: dict[str, Any] = {}
    for field in (
        "bid_price",
        "bid_size",
        "bid_exchange",
        "ask_price",
        "ask_size",
        "ask_exchange",
        "conditions",
    ):
        if field in input_data:
            previous_fields[field] = quote.get(field)
            update_fields[field] = input_data[field]
    delta = StateDelta(
        entity_type="alpaca_quote",
        entity_id=EntityId(quote["id"]),
        operation="update",
        fields=update_fields,
        previous_fields=previous_fields,
    )
    updated = {**quote, **update_fields}
    return ResponseProposal(response_body=updated, proposed_state_deltas=[delta])


# ---------------------------------------------------------------------------
# Handler 20: POST /volnix/market/bar (MUTATING -- Animator tool)
# ---------------------------------------------------------------------------


async def handle_create_bar(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    bar_id = _new_id("bar")
    now = _now_iso()
    bar_fields: dict[str, Any] = {
        "id": bar_id,
        "symbol": input_data.get("symbol", ""),
        "timestamp": input_data.get("timestamp", now),
        "open": input_data.get("open", 0),
        "high": input_data.get("high", 0),
        "low": input_data.get("low", 0),
        "close": input_data.get("close", 0),
        "volume": input_data.get("volume", 0),
        "trade_count": input_data.get("trade_count", 0),
        "vwap": input_data.get("vwap", 0),
        "timeframe": input_data.get("timeframe", "1Min"),
    }
    delta = StateDelta(
        entity_type="alpaca_bar",
        entity_id=EntityId(bar_id),
        operation="create",
        fields=bar_fields,
    )
    return ResponseProposal(response_body=bar_fields, proposed_state_deltas=[delta])


# ---------------------------------------------------------------------------
# Handler 21: POST /volnix/news (MUTATING -- Animator tool)
# ---------------------------------------------------------------------------


async def handle_create_news(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    news_id = _new_id("news")
    now = _now_iso()
    news_fields: dict[str, Any] = {
        "id": news_id,
        "headline": input_data.get("headline", ""),
        "author": input_data.get("author", "Volnix News Wire"),
        "created_at": input_data.get("created_at", now),
        "updated_at": input_data.get("updated_at", now),
        "summary": input_data.get("summary", ""),
        "url": input_data.get("url", ""),
        "symbols": input_data.get("symbols", []),
        "source": input_data.get("source", "volnix"),
        "images": input_data.get("images", []),
        # Internal fields (stripped by handle_get_news before serving)
        "factual_accuracy": input_data.get("factual_accuracy", 1.0),
        "sentiment_bias": input_data.get("sentiment_bias", 0.0),
        "market_impact_expected": float(input_data["market_impact_expected"])
        if input_data.get("market_impact_expected") is not None
        else 0.0,
    }
    delta = StateDelta(
        entity_type="alpaca_news",
        entity_id=EntityId(news_id),
        operation="create",
        fields=news_fields,
    )
    return ResponseProposal(response_body=news_fields, proposed_state_deltas=[delta])


# ---------------------------------------------------------------------------
# Handler 22: PUT /volnix/social/sentiment (MUTATING -- Animator tool)
# ---------------------------------------------------------------------------


async def handle_social_update_sentiment(
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> ResponseProposal:
    symbol = input_data.get("symbol", "")
    source = input_data.get("source", "all")
    sentiments = state.get("social_sentiments", [])
    existing = None
    for s in sentiments:
        if s.get("symbol") == symbol and s.get("source") == source:
            existing = s
            break

    now = _now_iso()
    if existing is None:
        # Create new sentiment entity
        sent_id = _new_id("sent")
        sent_fields: dict[str, Any] = {
            "id": sent_id,
            "symbol": symbol,
            "source": source,
            "window": input_data.get("window", "24h"),
            "score": input_data.get("score", 0.0),
            "post_count": input_data.get("post_count", 0),
            "positive_count": input_data.get("positive_count", 0),
            "negative_count": input_data.get("negative_count", 0),
            "neutral_count": input_data.get("neutral_count", 0),
            "trending_rank": input_data.get("trending_rank"),
            "computed_at": now,
        }
        delta = StateDelta(
            entity_type="social_sentiment",
            entity_id=EntityId(sent_id),
            operation="create",
            fields=sent_fields,
        )
        return ResponseProposal(response_body=sent_fields, proposed_state_deltas=[delta])
    else:
        # Update existing sentiment
        update_fields: dict[str, Any] = {"computed_at": now}
        previous_fields: dict[str, Any] = {}
        for field in (
            "score",
            "post_count",
            "positive_count",
            "negative_count",
            "neutral_count",
            "trending_rank",
            "window",
        ):
            if field in input_data:
                previous_fields[field] = existing.get(field)
                update_fields[field] = input_data[field]
        delta = StateDelta(
            entity_type="social_sentiment",
            entity_id=EntityId(existing["id"]),
            operation="update",
            fields=update_fields,
            previous_fields=previous_fields,
        )
        updated = {**existing, **update_fields}
        return ResponseProposal(response_body=updated, proposed_state_deltas=[delta])
