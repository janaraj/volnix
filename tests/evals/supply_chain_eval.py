"""Post-run evaluation script for the Supply Chain Disruption scenario.

Reads a completed run's events via the HTTP API and computes the
behavioral metrics declared in the Clean Rewrite plan (Phase P6.2):

- ``world_queries_per_move``: did each agent actually read the world,
  or did they anchor to persona numbers? (NF5: ``per_move`` replaces
  the pre-Cycle-B ``per_turn`` metric.)
- ``unique_services_queried``: more than just slack?
- ``response_to_animator_events``: did the agent's proposal shift
  meaningfully after a scheduled animator beat (e.g. the port closure)?
- ``private_queries`` + ``opponent_private_queries``: hard permission
  separation is working if ``opponent_private_queries == 0``.
- ``final_terms_match_state``: does the accepted deal reflect the
  actual world state at the moment of acceptance?

Usage (after a live run):

    python tests/evals/supply_chain_eval.py <run_id> \
        [--api-base http://localhost:8080] \
        [--json]  # machine-readable output

Exit code is 0 if all threshold gates pass, 1 otherwise. This lets
the script run as part of CI or a manual demo-readiness check.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.request import Request, urlopen

# Terms that are NEVER read (they're the negotiate_* structured tool
# calls, not world reads). We filter them out when counting "world
# queries per move".
_NEGOTIATE_ACTIONS: frozenset[str] = frozenset(
    {
        "negotiate_propose",
        "negotiate_counter",
        "negotiate_accept",
        "negotiate_reject",
    }
)

# Services that don't count as "world reads" for the metric (they're
# communication, not state queries).
_COMMUNICATION_SERVICES: frozenset[str] = frozenset({"slack", "game"})

# Minimum thresholds that a "passing" run must meet.
_THRESHOLD_WORLD_QUERIES_PER_MOVE: float = 2.0
_THRESHOLD_UNIQUE_SERVICES: int = 3
_THRESHOLD_CORRELATION: float = 0.5


@dataclass
class ActorMetrics:
    """Per-actor behavioral evaluation metrics.

    NF5 (B-cleanup.5): ``turns_taken`` was renamed to
    ``game_moves_made`` because Cycle B's event-driven model does not
    have rounds or turns. A game "move" is any committed
    ``world.negotiate_*`` event by this actor.
    """

    actor_id: str
    game_moves_made: int = 0
    world_queries_total: int = 0
    world_queries_per_move: float = 0.0
    unique_services_queried: int = 0
    unique_entity_types_touched: int = 0
    private_queries: int = 0  # own-private database queries
    opponent_private_queries: int = 0  # MUST be 0
    response_to_animator_events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RunMetrics:
    """Whole-run behavioral evaluation metrics.

    NF5 (B-cleanup.5): ``rounds_played`` was replaced with
    ``total_game_events`` — total committed ``world.negotiate_*``
    events across all players. The round concept doesn't exist in
    Cycle B's event-driven model; the equivalent duration metric is
    the number of committed game moves.
    """

    run_id: str
    total_game_events: int = 0
    deal_closed: bool = False
    winner: str | None = None
    final_terms: dict[str, Any] | None = None
    final_terms_match_state: float = 0.0
    actor_metrics: dict[str, ActorMetrics] = field(default_factory=dict)
    animator_event_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Render to JSON-serializable dict."""
        return {
            "run_id": self.run_id,
            "total_game_events": self.total_game_events,
            "deal_closed": self.deal_closed,
            "winner": self.winner,
            "final_terms": self.final_terms,
            "final_terms_match_state": self.final_terms_match_state,
            "animator_event_count": self.animator_event_count,
            "actor_metrics": {aid: asdict(m) for aid, m in self.actor_metrics.items()},
        }


def _fetch_events(run_id: str, api_base: str) -> list[dict[str, Any]]:
    """GET /api/v1/runs/{run_id}/events?limit=500&sort=asc."""
    url = f"{api_base}/api/v1/runs/{run_id}/events?limit=500&sort=asc"
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    return body.get("events", [])


def _is_world_read(event: dict[str, Any]) -> bool:
    """True if the event is an agent's read against a world service.

    Excludes chat posts, game moves, and internal pipeline events.
    """
    et = event.get("event_type", "")
    if not et.startswith("world."):
        return False
    service = event.get("service_id", "")
    if service in _COMMUNICATION_SERVICES:
        return False
    action = event.get("action", "")
    if action in _NEGOTIATE_ACTIONS:
        return False
    # Reads are typically list/query/retrieve/search — writes
    # (create/update/delete/post/send) shouldn't count as reads.
    # Actions can be dotted (e.g. "pages.create") — check the LAST
    # segment against write-verb prefixes.
    last_segment = action.rsplit(".", 1)[-1] if "." in action else action
    for write_prefix in ("create", "update", "delete", "post", "send", "append"):
        if last_segment.startswith(write_prefix):
            return False
    return True


def _query_targets_opponent_private(
    actor_id: str,
    event: dict[str, Any],
) -> bool:
    """Did this event attempt to read the opponent's private data?

    Heuristic: if the action is a notion read and the query parameters
    reference a database/page id containing the opponent's role name,
    it's an attempted cross-boundary query.

    In the visibility-rule pattern the permission engine will return
    empty results, but we still detect the ATTEMPT as a policy signal.
    """
    service = event.get("service_id", "")
    if service != "notion":
        return False
    action = event.get("action", "")
    if not action.startswith(("databases.", "pages.")):
        return False

    input_data = event.get("input_data") or {}
    input_str = json.dumps(input_data, default=str).lower()

    # Dana tries supplier-only refs
    if actor_id.startswith("nimbus") or actor_id.startswith("buyer"):
        forbidden = ("haiphong_inventory", "order_book", "haiphong_supplier")
    # Linh tries buyer-only refs
    elif actor_id.startswith("haiphong") or actor_id.startswith("supplier"):
        forbidden = (
            "production_schedule",
            "nimbus_inventory",
            "cfo_authority",
            "nimbus_buyer",
        )
    else:
        return False

    return any(f in input_str for f in forbidden)


def _query_targets_own_private(
    actor_id: str,
    event: dict[str, Any],
) -> bool:
    """Did this event read the actor's OWN private data?"""
    service = event.get("service_id", "")
    if service != "notion":
        return False

    input_data = event.get("input_data") or {}
    input_str = json.dumps(input_data, default=str).lower()

    if actor_id.startswith("nimbus") or actor_id.startswith("buyer"):
        own = ("production_schedule", "nimbus_inventory", "cfo_authority")
    elif actor_id.startswith("haiphong") or actor_id.startswith("supplier"):
        own = ("haiphong_inventory", "order_book")
    else:
        return False

    return any(o in input_str for o in own)


def _extract_negotiate_terms(event: dict[str, Any]) -> dict[str, Any] | None:
    """Pull the declared negotiation terms from a negotiate_* event."""
    action = event.get("action", "")
    if action not in ("negotiate_propose", "negotiate_counter"):
        return None
    payload = event.get("input_data") or {}
    # Extract only the known negotiation fields
    term_keys = (
        "unit_price",
        "quantity_units",
        "delivery_lead_days",
        "payment_terms_days",
        "freight_mode",
        "late_penalty_pct",
    )
    return {k: payload[k] for k in term_keys if k in payload}


def _terms_delta(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compute which term fields changed and by how much (relative)."""
    if before is None or after is None:
        return {}
    changed: dict[str, Any] = {}
    for k in set(before.keys()) | set(after.keys()):
        b = before.get(k)
        a = after.get(k)
        if b == a:
            continue
        if isinstance(b, (int, float)) and isinstance(a, (int, float)) and b:
            relative_delta = abs((a - b) / b)
            changed[k] = {"before": b, "after": a, "relative_delta": relative_delta}
        else:
            changed[k] = {"before": b, "after": a}
    return changed


def compute_metrics(run_id: str, events: list[dict[str, Any]]) -> RunMetrics:
    """Compute behavioral metrics from a list of committed run events."""
    metrics = RunMetrics(run_id=run_id)

    # Per-actor bookkeeping
    actor_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in events:
        actor = ev.get("actor_id") or ""
        if actor:
            actor_events[actor].append(ev)

    # Count animator events (source == "animator" or actor is a bot)
    for ev in events:
        source = ev.get("source") or ev.get("sub_type") or ""
        if source == "animator" or ev.get("actor_id") in (
            "weather_service",
            "port_authority",
            "news_bot",
            "sales_ops",
            "market_feed",
        ):
            metrics.animator_event_count += 1

    # NF5 (B-cleanup.5): total_game_events is the count of committed
    # ``world.negotiate_*`` events. This replaces the pre-Cycle-B
    # ``rounds_played`` metric that searched for ``game.round_started``
    # events (no longer emitted in the event-driven model).
    _GAME_MOVE_EVENT_TYPES = (
        "world.negotiate_propose",
        "world.negotiate_counter",
        "world.negotiate_accept",
        "world.negotiate_reject",
    )
    game_move_events = [ev for ev in events if ev.get("event_type") in _GAME_MOVE_EVENT_TYPES]
    metrics.total_game_events = len(game_move_events)

    # Deal closed + winner (from game.terminated). The pre-Cycle-B
    # ``game.completed`` event type was replaced by ``game.terminated``
    # in B.5, which carries the same winner + reason fields.
    terminated = [ev for ev in events if ev.get("event_type") == "game.terminated"]
    if terminated:
        term = terminated[0]
        metrics.winner = term.get("winner")
        # The deal was genuinely closed if the termination reason is
        # ``deal_closed`` AND at least one negotiate_accept was committed.
        accepts = [ev for ev in events if ev.get("event_type") == "world.negotiate_accept"]
        metrics.deal_closed = bool(accepts) and term.get("reason") == "deal_closed"
        # Final terms = last committed propose/counter before acceptance
        propose_or_counter = [
            _extract_negotiate_terms(ev)
            for ev in events
            if ev.get("event_type") in ("world.negotiate_propose", "world.negotiate_counter")
        ]
        propose_or_counter = [t for t in propose_or_counter if t]
        if propose_or_counter:
            metrics.final_terms = propose_or_counter[-1]

    # Per-actor metrics
    for actor_id, actor_ev_list in actor_events.items():
        # Skip non-player actors (animator bots, system, etc.)
        if actor_id in (
            "weather_service",
            "port_authority",
            "news_bot",
            "sales_ops",
            "market_feed",
            "system",
        ) or actor_id.startswith("system-"):
            continue
        if not (
            actor_id.startswith("nimbus")
            or actor_id.startswith("haiphong")
            or actor_id.startswith("buyer")
            or actor_id.startswith("supplier")
        ):
            continue

        am = ActorMetrics(actor_id=actor_id)

        # NF5: game moves made — count committed negotiate_* events by
        # this actor. Replaces the legacy ``turns_taken`` which counted
        # ``game.turn`` events (no longer emitted in the event-driven
        # model).
        am.game_moves_made = sum(
            1 for ev in actor_ev_list if ev.get("event_type") in _GAME_MOVE_EVENT_TYPES
        )

        # World queries — reads against non-comm services
        world_reads = [ev for ev in actor_ev_list if _is_world_read(ev)]
        am.world_queries_total = len(world_reads)
        if am.game_moves_made > 0:
            am.world_queries_per_move = am.world_queries_total / am.game_moves_made

        services = {ev.get("service_id", "") for ev in world_reads if ev.get("service_id")}
        am.unique_services_queried = len(services)

        entity_types_touched: set[str] = set()
        for ev in world_reads:
            # Parse entity type from action or input_data
            input_data = ev.get("input_data") or {}
            for k in ("entity_type", "database_id", "page_id"):
                if k in input_data:
                    entity_types_touched.add(str(input_data[k]))
        am.unique_entity_types_touched = len(entity_types_touched)

        # Private query audit
        for ev in actor_ev_list:
            if _query_targets_own_private(actor_id, ev):
                am.private_queries += 1
            if _query_targets_opponent_private(actor_id, ev):
                am.opponent_private_queries += 1

        metrics.actor_metrics[actor_id] = am

    # Response-to-animator-events metric: for each animator event,
    # find the next same-actor propose/counter and compute term delta.
    # A "response" is registered when at least one term shifted
    # by more than 5% relative.
    animator_event_times: list[tuple[int, dict[str, Any]]] = []
    for i, ev in enumerate(events):
        actor = ev.get("actor_id") or ""
        if actor in ("weather_service", "port_authority", "news_bot", "sales_ops"):
            animator_event_times.append((i, ev))

    # For each player, track propose/counter events in order
    player_moves: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for i, ev in enumerate(events):
        if ev.get("event_type") in (
            "world.negotiate_propose",
            "world.negotiate_counter",
        ):
            player_moves[ev.get("actor_id", "")].append((i, ev))

    for actor_id, moves in player_moves.items():
        if actor_id not in metrics.actor_metrics:
            continue
        am = metrics.actor_metrics[actor_id]
        for ai, animator_ev in animator_event_times:
            # Find the last move before the animator event
            before_moves = [m for m in moves if m[0] < ai]
            after_moves = [m for m in moves if m[0] > ai]
            if not before_moves or not after_moves:
                continue
            before_terms = _extract_negotiate_terms(before_moves[-1][1])
            after_terms = _extract_negotiate_terms(after_moves[0][1])
            delta = _terms_delta(before_terms, after_terms)
            # Count as a response if any term shifted >5%
            significant = [
                k
                for k, v in delta.items()
                if isinstance(v, dict) and v.get("relative_delta", 0) > 0.05
            ]
            if significant:
                am.response_to_animator_events.append(
                    {
                        "animator_action": animator_ev.get("action"),
                        "animator_actor": animator_ev.get("actor_id"),
                        "shifted_terms": significant,
                    }
                )

    # Final terms vs final state correlation (heuristic):
    # - If port was closed at acceptance AND freight_mode == "air",
    #   that's a +0.5 correlation point.
    # - If port was open at acceptance AND freight_mode == "sea",
    #   that's a +0.5 correlation point.
    # - If unit_price is within the market_comps range observed in
    #   the run, that's a +0.5 correlation point.
    # Total out of 1.0.
    if metrics.final_terms:
        correlation = 0.0
        # Port status at the moment of acceptance (find the last
        # port.update event BEFORE the accept)
        accept_idx = next(
            (i for i, ev in enumerate(events) if ev.get("event_type") == "world.negotiate_accept"),
            None,
        )
        if accept_idx is not None:
            port_updates = [
                ev
                for i, ev in enumerate(events)
                if i < accept_idx and (ev.get("input_data") or {}).get("page_id") == "port_haiphong"
            ]
            port_status = "open"  # default
            for ev in port_updates:
                props = (ev.get("input_data") or {}).get("properties", {})
                if "status" in props:
                    port_status = props["status"]

            freight_mode = metrics.final_terms.get("freight_mode", "sea")
            if port_status == "closed" and freight_mode == "air":
                correlation += 0.5
            elif port_status == "open" and freight_mode == "sea":
                correlation += 0.5

        unit_price = metrics.final_terms.get("unit_price", 0)
        # Market comps range: $24-28 (from the blueprint seeds)
        if 22 <= unit_price <= 32:
            correlation += 0.5

        metrics.final_terms_match_state = correlation

    return metrics


def check_thresholds(metrics: RunMetrics) -> tuple[bool, list[str]]:
    """Return (passed, failure_reasons)."""
    failures: list[str] = []

    if not metrics.actor_metrics:
        failures.append("No actor metrics computed — no player events found")

    for actor_id, am in metrics.actor_metrics.items():
        if am.world_queries_per_move < _THRESHOLD_WORLD_QUERIES_PER_MOVE:
            failures.append(
                f"{actor_id}: world_queries_per_move={am.world_queries_per_move:.2f} "
                f"< threshold {_THRESHOLD_WORLD_QUERIES_PER_MOVE}"
            )
        if am.unique_services_queried < _THRESHOLD_UNIQUE_SERVICES:
            failures.append(
                f"{actor_id}: unique_services_queried={am.unique_services_queried} "
                f"< threshold {_THRESHOLD_UNIQUE_SERVICES}"
            )
        if am.opponent_private_queries > 0:
            failures.append(
                f"{actor_id}: opponent_private_queries={am.opponent_private_queries} "
                f"> 0 (permission leak detected)"
            )

    if metrics.deal_closed and metrics.final_terms_match_state < _THRESHOLD_CORRELATION:
        failures.append(
            f"Deal closed but final_terms_match_state={metrics.final_terms_match_state:.2f} "
            f"< threshold {_THRESHOLD_CORRELATION} — deal doesn't reflect world state"
        )

    return (len(failures) == 0), failures


def _render_table(metrics: RunMetrics) -> str:
    """Human-readable summary table."""
    lines = [
        f"=== Run {metrics.run_id} ===",
        f"  Total game events: {metrics.total_game_events}",
        f"  Deal closed: {metrics.deal_closed}",
        f"  Winner: {metrics.winner or '(none)'}",
        f"  Final terms: {metrics.final_terms or '(none)'}",
        f"  Final terms match state: {metrics.final_terms_match_state:.2f}",
        f"  Animator events: {metrics.animator_event_count}",
        "",
        "=== Per-actor metrics ===",
    ]
    for actor_id, am in metrics.actor_metrics.items():
        lines.append(f"  {actor_id}:")
        lines.append(f"    game_moves_made: {am.game_moves_made}")
        lines.append(
            f"    world_queries_per_move: {am.world_queries_per_move:.2f}"
            f" (total {am.world_queries_total})"
        )
        lines.append(f"    unique_services_queried: {am.unique_services_queried}")
        lines.append(f"    unique_entity_types_touched: {am.unique_entity_types_touched}")
        lines.append(f"    private_queries: {am.private_queries}")
        lines.append(f"    opponent_private_queries: {am.opponent_private_queries} (MUST be 0)")
        lines.append(f"    response_to_animator_events: {len(am.response_to_animator_events)}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Supply chain run evaluator")
    parser.add_argument("run_id", help="Run ID to evaluate")
    parser.add_argument(
        "--api-base",
        default="http://localhost:8080",
        help="API base URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON instead of the human summary",
    )
    args = parser.parse_args()

    events = _fetch_events(args.run_id, args.api_base)
    if not events:
        print(f"No events found for run {args.run_id}", file=sys.stderr)
        return 1

    metrics = compute_metrics(args.run_id, events)
    passed, failures = check_thresholds(metrics)

    if args.json:
        result = {
            "metrics": metrics.to_dict(),
            "passed": passed,
            "failures": failures,
        }
        print(json.dumps(result, indent=2, default=str))
    else:
        print(_render_table(metrics))
        print()
        if passed:
            print("RESULT: PASS — all threshold gates met.")
        else:
            print("RESULT: FAIL")
            for f in failures:
                print(f"  - {f}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
