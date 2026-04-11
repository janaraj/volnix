"""BehavioralScorer — per-agent behavior metrics, no leaderboard.

Reads events + state_engine to compute:

- ``world_queries_total``: count of world-read actions (notion.retrieve,
  twitter.search, etc.) per actor
- ``unique_services_queried``: number of distinct services the actor
  queried
- ``reactions_to_animator``: count of game moves within N events of
  an animator/environment event (responsiveness to world changes)
- ``policy_blocks``: count of actions blocked by policy
- ``permission_denials``: count of actions denied by permission engine
- ``policy_compliance_pct``: 100 - (blocks+denials)/events * 100

**Critical invariant (MF3)**: BehavioralScorer NEVER reads
``term_weights``, ``batna_score``, ``ideal_terms``, or ``term_ranges``.
Those fields live exclusively in ``negotiation_target_terms`` entities
which are not materialized in behavioral mode.
"""

from __future__ import annotations

import logging
from typing import Any

from volnix.engines.game.definition import PlayerScore
from volnix.engines.game.scorers.base import GameScorer, ScorerContext

logger = logging.getLogger(__name__)


class BehavioralScorer(GameScorer):
    """Behavioral evaluation scorer.

    Maintains per-actor running counters in memory (reset on each
    game start via orchestrator's configure()). Writes aggregated
    metrics into ``player_score.behavior_metrics`` on every
    ``score_event`` call.
    """

    def __init__(self) -> None:
        self._world_queries: dict[str, int] = {}
        self._unique_services: dict[str, set[str]] = {}
        self._last_animator_event_at: int | None = None
        self._reactions_to_animator: dict[str, int] = {}
        self._policy_blocks: dict[str, int] = {}
        self._permission_denials: dict[str, int] = {}

    async def score_event(self, ctx: ScorerContext) -> None:
        """Update per-actor behavior metrics from this event."""
        event = ctx.event
        actor_id = str(event.actor_id)

        # Track animator-like events BEFORE filtering out non-player actors —
        # they reset the reactivity window for everyone.
        service = str(event.service_id)
        actor_str_lower = actor_id.lower()
        if "animator" in actor_str_lower or "environment" in actor_str_lower:
            self._last_animator_event_at = ctx.event_number

        # Skip events from non-players for the remaining per-player metrics
        if actor_id not in ctx.player_scores:
            return

        ps = ctx.player_scores[actor_id]
        action = str(event.action)
        is_game_move = action.startswith("negotiate_")
        is_query = self._is_world_query(action)

        # 1. World query counting
        if is_query and service not in ("slack", "game"):
            self._world_queries[actor_id] = self._world_queries.get(actor_id, 0) + 1
            bucket = self._unique_services.setdefault(actor_id, set())
            bucket.add(service)

        # 2. Policy / permission compliance
        outcome = str(event.outcome)
        if outcome == "blocked":
            self._policy_blocks[actor_id] = self._policy_blocks.get(actor_id, 0) + 1
        elif outcome == "denied":
            self._permission_denials[actor_id] = self._permission_denials.get(actor_id, 0) + 1

        # 3. Reactivity: game moves within N events of an animator event.
        # Window size comes from FlowConfig.reactivity_window_events so
        # tick-heavy scenarios can tune it per blueprint. Falls back to a
        # safe default of 5 if definition is absent in tests.
        reactivity_window = 5
        definition = getattr(ctx, "definition", None)
        flow = getattr(definition, "flow", None)
        if flow is not None:
            reactivity_window = getattr(flow, "reactivity_window_events", 5)
        if is_game_move and self._last_animator_event_at is not None:
            delta = ctx.event_number - self._last_animator_event_at
            if 0 < delta <= reactivity_window:
                self._reactions_to_animator[actor_id] = (
                    self._reactions_to_animator.get(actor_id, 0) + 1
                )

        # 4. Write aggregated metrics into player_score.behavior_metrics
        total_events = max(1, ctx.event_number)
        blocks_plus_denials = self._policy_blocks.get(actor_id, 0) + self._permission_denials.get(
            actor_id, 0
        )
        ps.behavior_metrics = {
            "world_queries_total": float(self._world_queries.get(actor_id, 0)),
            "unique_services_queried": float(len(self._unique_services.get(actor_id, set()))),
            "reactions_to_animator": float(self._reactions_to_animator.get(actor_id, 0)),
            "policy_blocks": float(self._policy_blocks.get(actor_id, 0)),
            "permission_denials": float(self._permission_denials.get(actor_id, 0)),
            "policy_compliance_pct": max(0.0, 100.0 - blocks_plus_denials * 100.0 / total_events),
        }
        # Behavioral mode has no leaderboard — total_score stays at 0.
        ps.total_score = 0.0

    @staticmethod
    def _is_world_query(action: str) -> bool:
        """Heuristic: does this action READ the world (vs write to it)?

        Reads have names like ``pages.retrieve``, ``databases.query``,
        ``users.list``, ``search``, ``conversations.history``. Writes
        have names like ``pages.create``, ``chat.postMessage``,
        ``create_tweet``, ``blocks.children.append``.
        """
        if not action:
            return False
        last_segment = action.rsplit(".", 1)[-1].lower()
        write_prefixes = (
            "create",
            "update",
            "delete",
            "append",
            "send",
            "post",
            "ack",
            "chat",
            "reply",
        )
        for pfx in write_prefixes:
            if last_segment.startswith(pfx):
                return False
        return True

    async def settle(
        self,
        open_deals: list[dict[str, Any]],
        state_engine: Any,
        player_scores: dict[str, PlayerScore],
        definition: Any,
    ) -> None:
        """Behavioral mode settle: no-op.

        Behavioral mode never applies BATNA or re-scores at termination
        — the running metrics (``world_queries_total``, ``reactivity``,
        ``policy_compliance_pct``) already reflect player behavior up to
        the final event. Scenario-specific consistency checks (e.g.
        "final terms vs current port status") live in the per-scenario
        evaluation script (``tests/evals/*_eval.py``), not here, so
        the scorer stays scenario-agnostic.
        """
        logger.info(
            "BehavioralScorer.settle: noop (metrics already finalized for %d players)",
            len(player_scores),
        )
