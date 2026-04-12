"""Unit tests for tests/evals/supply_chain_eval.py.

Tests the metric computation logic against synthetic event streams.
No network, no actual run — pure function tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Import the eval script — it lives in the same directory, not as a package
sys.path.insert(0, str(Path(__file__).parent))

from supply_chain_eval import (  # noqa: E402
    ActorMetrics,
    RunMetrics,
    _extract_negotiate_terms,
    _is_world_read,
    _query_targets_opponent_private,
    _query_targets_own_private,
    _terms_delta,
    check_thresholds,
    compute_metrics,
)

# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


def _notion_read(
    actor_id: str,
    action: str = "databases.query",
    database_id: str = "ports_db",
) -> dict:
    return {
        "event_type": f"world.{action}",
        "actor_id": actor_id,
        "service_id": "notion",
        "action": action,
        "input_data": {"database_id": database_id},
    }


def _negotiate_propose(
    actor_id: str,
    unit_price: float = 25.0,
    freight_mode: str = "sea",
    delivery: int = 7,
) -> dict:
    return {
        "event_type": "world.negotiate_propose",
        "actor_id": actor_id,
        "service_id": "game",
        "action": "negotiate_propose",
        "input_data": {
            "deal_id": "deal-pwr7a-2026q2",
            "unit_price": unit_price,
            "quantity_units": 20000,
            "delivery_lead_days": delivery,
            "payment_terms_days": 45,
            "freight_mode": freight_mode,
            "late_penalty_pct": 2.0,
        },
    }


def _accept(actor_id: str) -> dict:
    return {
        "event_type": "world.negotiate_accept",
        "actor_id": actor_id,
        "service_id": "game",
        "action": "negotiate_accept",
        "input_data": {"deal_id": "deal-pwr7a-2026q2"},
    }


def _terminated(winner: str | None = None, reason: str = "deal_closed") -> dict:
    """NF5: ``game.terminated`` is the event-driven replacement for
    the pre-Cycle-B ``game.completed`` event. Carries the same
    winner + reason fields that the eval script reads.
    """
    return {
        "event_type": "game.terminated",
        "actor_id": "",
        "winner": winner,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# _is_world_read
# ---------------------------------------------------------------------------


def test_is_world_read_accepts_notion_query():
    assert _is_world_read(_notion_read("nimbus_buyer_1"))


def test_is_world_read_rejects_chat_post():
    ev = {
        "event_type": "world.chat.postMessage",
        "actor_id": "nimbus_buyer_1",
        "service_id": "slack",
        "action": "chat.postMessage",
    }
    assert not _is_world_read(ev)


def test_is_world_read_rejects_negotiate_move():
    assert not _is_world_read(_negotiate_propose("nimbus_buyer_1"))


def test_is_world_read_rejects_write_action():
    ev = {
        "event_type": "world.notion.pages.create",
        "actor_id": "nimbus_buyer_1",
        "service_id": "notion",
        "action": "pages.create",
        "input_data": {},
    }
    assert not _is_world_read(ev)


def test_is_world_read_accepts_twitter_search():
    ev = {
        "event_type": "world.twitter.search_recent",
        "actor_id": "nimbus_buyer_1",
        "service_id": "twitter",
        "action": "search_recent",
        "input_data": {"q": "typhoon"},
    }
    assert _is_world_read(ev)


# ---------------------------------------------------------------------------
# Private query detection
# ---------------------------------------------------------------------------


def test_buyer_own_private_query():
    ev = _notion_read("nimbus_buyer_1", database_id="cfo_authority_db")
    assert _query_targets_own_private("nimbus_buyer_1", ev)
    assert not _query_targets_opponent_private("nimbus_buyer_1", ev)


def test_buyer_tries_supplier_private():
    """If the buyer tries to read haiphong_inventory it's a leak attempt."""
    ev = _notion_read("nimbus_buyer_1", database_id="haiphong_inventory_db")
    assert _query_targets_opponent_private("nimbus_buyer_1", ev)
    assert not _query_targets_own_private("nimbus_buyer_1", ev)


def test_supplier_own_private_query():
    ev = _notion_read("haiphong_supplier_1", database_id="order_book_db")
    assert _query_targets_own_private("haiphong_supplier_1", ev)
    assert not _query_targets_opponent_private("haiphong_supplier_1", ev)


def test_supplier_tries_buyer_private():
    ev = _notion_read("haiphong_supplier_1", database_id="production_schedule_db")
    assert _query_targets_opponent_private("haiphong_supplier_1", ev)


def test_public_query_is_neither_own_nor_opponent_private():
    ev = _notion_read("nimbus_buyer_1", database_id="ports_db")
    assert not _query_targets_own_private("nimbus_buyer_1", ev)
    assert not _query_targets_opponent_private("nimbus_buyer_1", ev)


# ---------------------------------------------------------------------------
# Terms extraction and delta
# ---------------------------------------------------------------------------


def test_extract_negotiate_terms():
    ev = _negotiate_propose("nimbus_buyer_1", unit_price=26.5, freight_mode="air")
    terms = _extract_negotiate_terms(ev)
    assert terms is not None
    assert terms["unit_price"] == 26.5
    assert terms["freight_mode"] == "air"


def test_extract_terms_returns_none_for_non_move():
    ev = _notion_read("nimbus_buyer_1")
    assert _extract_negotiate_terms(ev) is None


def test_terms_delta_detects_price_shift():
    before = {"unit_price": 25.0, "freight_mode": "sea"}
    after = {"unit_price": 28.0, "freight_mode": "sea"}
    delta = _terms_delta(before, after)
    assert "unit_price" in delta
    assert delta["unit_price"]["relative_delta"] == 0.12  # (28-25)/25
    assert "freight_mode" not in delta  # unchanged


def test_terms_delta_handles_enum_shift():
    before = {"freight_mode": "sea"}
    after = {"freight_mode": "air"}
    delta = _terms_delta(before, after)
    assert "freight_mode" in delta
    assert delta["freight_mode"]["before"] == "sea"
    assert delta["freight_mode"]["after"] == "air"


def test_terms_delta_empty_when_no_change():
    before = {"unit_price": 25.0}
    after = {"unit_price": 25.0}
    assert _terms_delta(before, after) == {}


# ---------------------------------------------------------------------------
# compute_metrics — end-to-end
# ---------------------------------------------------------------------------


def test_compute_metrics_counts_game_moves_made():
    """NF5: replaces ``rounds_played`` / ``turns_taken`` with
    ``total_game_events`` / ``game_moves_made``. Each committed
    ``world.negotiate_*`` event counts as a game move.
    """
    events = [
        _negotiate_propose("nimbus_buyer_1", unit_price=25.0),
        _negotiate_propose("haiphong_supplier_1", unit_price=30.0),
        _negotiate_propose("nimbus_buyer_1", unit_price=26.0),
        _negotiate_propose("haiphong_supplier_1", unit_price=28.0),
    ]
    metrics = compute_metrics("run-1", events)
    assert metrics.total_game_events == 4
    assert metrics.actor_metrics["nimbus_buyer_1"].game_moves_made == 2
    assert metrics.actor_metrics["haiphong_supplier_1"].game_moves_made == 2


def test_compute_metrics_world_queries_per_move():
    """Dana makes 4 world queries across 2 game moves → 2.0 queries/move."""
    events = [
        _negotiate_propose("nimbus_buyer_1"),
        _notion_read("nimbus_buyer_1", database_id="cfo_authority_db"),
        _notion_read("nimbus_buyer_1", database_id="ports_db"),
        _negotiate_propose("nimbus_buyer_1"),
        _notion_read("nimbus_buyer_1", database_id="weather_alerts_db"),
        {
            "event_type": "world.twitter.search_recent",
            "actor_id": "nimbus_buyer_1",
            "service_id": "twitter",
            "action": "search_recent",
            "input_data": {"q": "typhoon"},
        },
    ]
    metrics = compute_metrics("run-2", events)
    dana = metrics.actor_metrics["nimbus_buyer_1"]
    assert dana.world_queries_total == 4
    assert dana.world_queries_per_move == 2.0
    assert dana.unique_services_queried == 2  # notion + twitter


def test_compute_metrics_detects_private_queries():
    events = [
        _negotiate_propose("nimbus_buyer_1"),
        _notion_read("nimbus_buyer_1", database_id="cfo_authority_db"),
        _notion_read("nimbus_buyer_1", database_id="production_schedule_db"),
        _notion_read("nimbus_buyer_1", database_id="ports_db"),
    ]
    metrics = compute_metrics("run-3", events)
    dana = metrics.actor_metrics["nimbus_buyer_1"]
    assert dana.private_queries == 2  # cfo_authority + production_schedule
    assert dana.opponent_private_queries == 0


def test_compute_metrics_flags_opponent_private_leak():
    """If a buyer queries supplier's private db, the eval flags it."""
    events = [
        _negotiate_propose("nimbus_buyer_1"),
        _notion_read("nimbus_buyer_1", database_id="haiphong_inventory_db"),
    ]
    metrics = compute_metrics("run-leak", events)
    dana = metrics.actor_metrics["nimbus_buyer_1"]
    assert dana.opponent_private_queries == 1

    passed, failures = check_thresholds(metrics)
    assert not passed
    assert any("permission leak" in f for f in failures)


def test_compute_metrics_deal_closed_with_final_terms():
    """NF5: uses ``game.terminated`` (event-driven) instead of
    pre-Cycle-B ``game.completed``.
    """
    events = [
        _negotiate_propose("nimbus_buyer_1", unit_price=26.0, freight_mode="sea"),
        _accept("haiphong_supplier_1"),
        _terminated(winner="nimbus_buyer_1", reason="deal_closed"),
    ]
    metrics = compute_metrics("run-closed", events)
    assert metrics.deal_closed is True
    assert metrics.winner == "nimbus_buyer_1"
    assert metrics.final_terms is not None
    assert metrics.final_terms["unit_price"] == 26.0


def test_compute_metrics_deal_not_closed_on_timeout():
    """NF5 regression: termination with reason!=deal_closed → deal_closed=False."""
    events = [
        _negotiate_propose("nimbus_buyer_1"),
        _terminated(winner=None, reason="wall_clock"),
    ]
    metrics = compute_metrics("run-timeout", events)
    assert metrics.deal_closed is False
    assert metrics.winner is None


def test_check_thresholds_passing_run():
    """A run meeting all thresholds returns passed=True with empty failures."""
    metrics = RunMetrics(run_id="run-good")
    metrics.deal_closed = True
    metrics.final_terms = {"unit_price": 26.0, "freight_mode": "sea"}
    metrics.final_terms_match_state = 0.7
    metrics.actor_metrics["nimbus_buyer_1"] = ActorMetrics(
        actor_id="nimbus_buyer_1",
        game_moves_made=3,
        world_queries_total=9,
        world_queries_per_move=3.0,
        unique_services_queried=3,
        private_queries=3,
        opponent_private_queries=0,
    )
    metrics.actor_metrics["haiphong_supplier_1"] = ActorMetrics(
        actor_id="haiphong_supplier_1",
        game_moves_made=3,
        world_queries_total=6,
        world_queries_per_move=2.0,
        unique_services_queried=3,
        private_queries=2,
        opponent_private_queries=0,
    )

    passed, failures = check_thresholds(metrics)
    assert passed
    assert failures == []


def test_check_thresholds_failing_run_insufficient_queries():
    metrics = RunMetrics(run_id="run-thin")
    metrics.actor_metrics["nimbus_buyer_1"] = ActorMetrics(
        actor_id="nimbus_buyer_1",
        game_moves_made=3,
        world_queries_total=3,
        world_queries_per_move=1.0,  # below threshold of 2.0
        unique_services_queried=2,  # below threshold of 3
        private_queries=0,
        opponent_private_queries=0,
    )

    passed, failures = check_thresholds(metrics)
    assert not passed
    assert len(failures) >= 2
