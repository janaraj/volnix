"""Game engine — manages game definitions, rounds, scoring, and win conditions.

The 11th engine in the Volnix framework. Tracks game state,
evaluates win conditions, and publishes game lifecycle events.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, ClassVar

from volnix.core import BaseEngine, Event
from volnix.core.types import ActorId, EntityId, Timestamp
from volnix.engines.game.config import GameConfig
from volnix.engines.game.definition import (
    GameDefinition,
    GameResult,
    PlayerScore,
    RoundState,
    WinResult,
)
from volnix.engines.game.events import (
    GameCompletedEvent,
    GameEliminationEvent,
    GameRoundEndedEvent,
    GameRoundStartedEvent,
    GameScoreUpdatedEvent,
    GameStartedEvent,
)
from volnix.engines.game.scorer import GameScorer
from volnix.engines.game.win_conditions import WinConditionEvaluator

logger = logging.getLogger(__name__)


def _now_ts() -> Timestamp:
    now = datetime.now(UTC)
    return Timestamp(world_time=now, wall_time=now, tick=0)


class GameEngine(BaseEngine):
    """Manages game definitions, rounds, scoring, and win conditions.

    The 11th engine in the Volnix framework. Subscribes to all world events
    to track game-relevant actions, delegates scoring to :class:`GameScorer`
    and win-condition evaluation to :class:`WinConditionEvaluator`.
    """

    engine_name: ClassVar[str] = "game"
    subscriptions: ClassVar[list[str]] = []  # events collected by GameRunner, not bus
    dependencies: ClassVar[list[str]] = ["state", "budget"]

    def __init__(self) -> None:
        super().__init__()
        self._game_config = GameConfig()
        self._definition: GameDefinition | None = None
        self._scorer: GameScorer | None = None
        self._win_evaluator: WinConditionEvaluator | None = None
        self._round_state: RoundState = RoundState()
        self._player_scores: dict[str, PlayerScore] = {}
        self._events_this_round: list[Event] = []
        self._cumulative_events: list[Any] = []
        self._game_active: bool = False
        self._run_id: str | None = None
        self._resolved_entity_types: dict[str, str] = {}  # metric entity_type → actual DB type

    # -- BaseEngine lifecycle --------------------------------------------------

    async def _on_initialize(self) -> None:
        """Load GameConfig from engine config dict."""
        if self._config:
            self._game_config = GameConfig(
                **{k: v for k, v in self._config.items() if k in GameConfig.model_fields}
            )

    # -- Game configuration ----------------------------------------------------

    async def configure(
        self, definition: GameDefinition, players: list[str], run_id: str | None = None
    ) -> None:
        """Configure game from blueprint definition.

        Args:
            definition: The game definition parsed from blueprint YAML.
            players: List of player/actor IDs participating in the game.
            run_id: Optional run identifier for event correlation.
        """
        self._definition = definition
        self._scorer = GameScorer(definition.scoring)
        self._win_evaluator = WinConditionEvaluator(definition.win_conditions)
        self._round_state = RoundState(
            current_round=0,
            total_rounds=definition.rounds.count,
            phase="not_started",
        )
        self._player_scores = {pid: PlayerScore(actor_id=pid) for pid in players}
        self._events_this_round = []
        self._game_active = True
        self._run_id = run_id
        self._resolved_entity_types = {}
        await self._assign_entity_ownership()
        logger.info(
            "Game configured: mode=%s, rounds=%d, players=%d",
            definition.mode,
            definition.rounds.count,
            len(players),
        )

    async def _assign_entity_ownership(self) -> None:
        """Assign game_owner_id on scored entities via state engine.

        For each state-sourced metric, assigns first N entities (N = player
        count) to players by setting ``game_owner_id`` field. This is a
        one-time state mutation at game start — generic for any game type.
        """
        state = self._dependencies.get("state")
        if not state or not self._definition:
            return

        player_ids = list(self._player_scores.keys())
        if not player_ids:
            return

        seen_types: set[str] = set()
        for metric in self._definition.scoring.metrics:
            if metric.source != "state" or metric.entity_type in seen_types:
                continue
            seen_types.add(metric.entity_type)

            try:
                entities = await state.query_entities(entity_type=metric.entity_type)
            except Exception as exc:
                logger.warning("Failed to query entities for ownership: %s", exc)
                continue

            resolved_type = metric.entity_type
            if not entities:
                # Try pack-prefixed variants (e.g., "account" → "alpaca_account")
                try:
                    all_types = await state.list_entity_types()
                    for et in all_types:
                        if et.endswith(f"_{metric.entity_type}"):
                            entities = await state.query_entities(entity_type=et)
                            if entities:
                                resolved_type = et
                                logger.info(
                                    "Resolved entity_type '%s' → '%s' (%d entities)",
                                    metric.entity_type,
                                    et,
                                    len(entities),
                                )
                                break
                except Exception as exc:
                    logger.debug("Entity type fallback failed: %s", exc)

            if not entities:
                logger.warning(
                    "Scoring metric '%s' references entity_type '%s' but 0 entities found",
                    metric.name,
                    metric.entity_type,
                )
                continue

            self._resolved_entity_types[metric.entity_type] = resolved_type

            # Assign first N entities to N players (1:1)
            store = getattr(state, "_store", None)
            if not store:
                logger.warning("State engine has no _store — cannot assign ownership")
                continue

            assigned = 0
            for i, player_id in enumerate(player_ids):
                if i >= len(entities):
                    break
                eid = entities[i].get("id", "")
                if eid:
                    try:
                        await store.update(
                            resolved_type,
                            EntityId(eid),
                            {"game_owner_id": player_id},
                        )
                        assigned += 1
                    except Exception as exc:
                        logger.warning("Failed to assign ownership for %s: %s", eid, exc)

            logger.info(
                "Assigned game_owner_id on %d '%s' entities for %d players",
                assigned,
                resolved_type,
                len(player_ids),
            )

    # -- Game lifecycle --------------------------------------------------------

    async def start_game(self) -> None:
        """Emit game started event."""
        if self._definition is None:
            raise RuntimeError("Game not configured. Call configure() first.")
        event = GameStartedEvent(
            event_type="game.started",
            timestamp=_now_ts(),
            game_mode=self._definition.mode,
            player_ids=list(self._player_scores.keys()),
            total_rounds=self._definition.rounds.count,
            run_id=self._run_id,
        )
        await self.publish(event)

    async def start_round(self) -> None:
        """Advance to next round."""
        if self._definition is None:
            raise RuntimeError("Game not configured. Call configure() first.")
        self._round_state = self._round_state.advance()
        self._events_this_round = []
        event = GameRoundStartedEvent(
            event_type="game.round_started",
            timestamp=_now_ts(),
            round_number=self._round_state.current_round,
            total_rounds=self._round_state.total_rounds,
            run_id=self._run_id,
        )
        await self.publish(event)
        logger.info(
            "Round %d/%d started",
            self._round_state.current_round,
            self._round_state.total_rounds,
        )

    async def end_round(self, round_events: list[Any] | None = None) -> list[dict[str, Any]]:
        """End current round, compute scores, return standings.

        Args:
            round_events: Events collected by the GameRunner during this round.
                         Falls back to ``_events_this_round`` (bus-delivered) if None.
        """
        if self._definition is None:
            raise RuntimeError("Game not configured. Call configure() first.")
        if not self._scorer:
            return []

        state_engine = self._dependencies.get("state")
        player_ids = [pid for pid, s in self._player_scores.items() if not s.eliminated]

        round_events_list = round_events if round_events is not None else self._events_this_round
        self._cumulative_events.extend(round_events_list)
        logger.info(
            "Scoring round %d: %d round events, %d cumulative, %d active players",
            self._round_state.current_round,
            len(round_events_list),
            len(self._cumulative_events),
            len(player_ids),
        )
        raw_scores = await self._scorer.compute_scores(
            player_ids,
            state_engine,
            self._cumulative_events,
            resolved_entity_types=self._resolved_entity_types,
        )

        # Update player scores and publish score events
        for pid, metrics in raw_scores.items():
            if pid in self._player_scores:
                self._player_scores[pid].update_metrics(metrics, self._scorer.weights)
            for metric_name, value in metrics.items():
                event = GameScoreUpdatedEvent(
                    event_type="game.score_updated",
                    timestamp=_now_ts(),
                    actor_id=ActorId(pid),
                    metric=metric_name,
                    value=value,
                    round_number=self._round_state.current_round,
                    run_id=self._run_id,
                )
                await self.publish(event)

        standings = self._build_standings()

        event = GameRoundEndedEvent(
            event_type="game.round_ended",
            timestamp=_now_ts(),
            round_number=self._round_state.current_round,
            standings=standings,
            run_id=self._run_id,
        )
        await self.publish(event)

        self._round_state = self._round_state.end_round()
        logger.info(
            "Round %d ended. Leader: %s",
            self._round_state.current_round,
            standings[0]["actor_id"] if standings else "none",
        )
        return standings

    async def check_win_conditions(self) -> WinResult | None:
        """Evaluate all win conditions."""
        if self._definition is None:
            raise RuntimeError("Game not configured. Call configure() first.")
        if not self._win_evaluator:
            return None
        result = self._win_evaluator.evaluate(self._player_scores, self._round_state)
        if result is not None:
            # Check for eliminations
            for pid, score in self._player_scores.items():
                if score.eliminated and score.elimination_round == self._round_state.current_round:
                    elim_event = GameEliminationEvent(
                        event_type="game.elimination",
                        timestamp=_now_ts(),
                        actor_id=ActorId(pid),
                        reason="below_threshold",
                        round_number=self._round_state.current_round,
                        run_id=self._run_id,
                    )
                    await self.publish(elim_event)
        return result

    async def complete_game(self, result: WinResult | None = None) -> GameResult:
        """Finalize game, emit completion event.

        Args:
            result: Optional win result from condition evaluation.

        Returns:
            The final :class:`GameResult` with winner, standings, and reason.
        """
        self._game_active = False
        self._round_state = self._round_state.complete()

        standings = self._build_standings()
        winner = result.winner if result else (standings[0]["actor_id"] if standings else None)
        reason = result.reason if result else "rounds_complete"

        event = GameCompletedEvent(
            event_type="game.completed",
            timestamp=_now_ts(),
            winner=winner,
            final_standings=standings,
            reason=reason,
            total_rounds_played=self._round_state.current_round,
            run_id=self._run_id,
        )
        await self.publish(event)

        logger.info(
            "Game completed: winner=%s, reason=%s, rounds=%d",
            winner,
            reason,
            self._round_state.current_round,
        )

        return GameResult(
            winner=winner,
            reason=reason,
            total_rounds_played=self._round_state.current_round,
            final_standings=standings,
            game_mode=self._definition.mode if self._definition else "competition",
        )

    # -- Query -----------------------------------------------------------------

    async def get_standings(self) -> list[dict[str, Any]]:
        """Current leaderboard."""
        return self._build_standings()

    @property
    def is_active(self) -> bool:
        """Whether a game is currently in progress."""
        return self._game_active

    @property
    def round_state(self) -> RoundState:
        """Current round state snapshot."""
        return self._round_state

    @property
    def definition(self) -> GameDefinition | None:
        """The active game definition, or None if not configured."""
        return self._definition

    @property
    def player_scores(self) -> dict[str, PlayerScore]:
        """Copy of current player scores."""
        return dict(self._player_scores)

    @property
    def run_id(self) -> str | None:
        """The active run identifier."""
        return self._run_id

    async def publish_event(self, event: Event) -> None:
        """Publish a game event via the engine's bus connection."""
        await self.publish(event)

    # -- BaseEngine hook -------------------------------------------------------

    async def _handle_event(self, event: Event) -> None:
        """No-op — round events are collected by GameRunner, not via bus."""

    # -- Internal helpers ------------------------------------------------------

    def _build_standings(self) -> list[dict[str, Any]]:
        """Build sorted standings list."""
        ranking = "descending"
        if self._definition and self._definition.scoring:
            ranking = self._definition.scoring.ranking

        sorted_players = sorted(
            self._player_scores.values(),
            key=lambda s: s.total_score,
            reverse=(ranking == "descending"),
        )
        return [
            {
                "actor_id": s.actor_id,
                "total_score": s.total_score,
                "metrics": dict(s.metrics),
                "eliminated": s.eliminated,
                "rank": i + 1,
            }
            for i, s in enumerate(sorted_players)
        ]
