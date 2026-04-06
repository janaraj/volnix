"""State machine definitions for trading service entities.

Defines valid status transitions for orders and assets following
the Alpaca Markets lifecycle conventions.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Order lifecycle
# ---------------------------------------------------------------------------

ORDER_STATES: list[str] = [
    "new",
    "accepted",
    "partially_filled",
    "filled",
    "cancelled",
    "expired",
    "rejected",
]

ORDER_TRANSITIONS: dict[str, list[str]] = {
    "new": ["accepted", "rejected"],
    "accepted": ["partially_filled", "filled", "cancelled", "expired"],
    "partially_filled": ["filled", "cancelled"],
    "filled": [],  # terminal
    "cancelled": [],  # terminal
    "expired": [],  # terminal
    "rejected": [],  # terminal
}

# ---------------------------------------------------------------------------
# Asset status
# ---------------------------------------------------------------------------

ASSET_STATES: list[str] = ["active", "inactive"]

ASSET_TRANSITIONS: dict[str, list[str]] = {
    "active": ["inactive"],
    "inactive": ["active"],
}
