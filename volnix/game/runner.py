"""Game runner — round-based game loop orchestrator.

Controls the game flow: round progression, turn order, between-round hooks,
resource regeneration, win condition checking. Uses GameEngine for game logic
and the existing pipeline/agency/animator for action execution.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from volnix.core.types import ActorId, Timestamp
from volnix.engines.game.definition import GameDefinition, GameResult, WinResult
from volnix.engines.game.events import GameTurnEvent
from volnix.game.turn_manager import TurnManager, TurnOrder

logger = logging.getLogger(__name__)


class GameRunner:
    """Round-based game loop orchestrator."""

    def __init__(
        self,
        game_engine: Any,  # GameEngine
        agency_engine: Any,  # AgencyEngine
        animator: Any | None,  # AnimatorEngine
        budget_engine: Any | None,  # BudgetEngine
        pipeline_executor: Callable[..., Any],
        app: Any | None = None,  # VolnixApp (for handle_action)
    ) -> None:
        self._game = game_engine
        self._agency = agency_engine
        self._animator = animator
        self._budget = budget_engine
        self._pipeline_executor = pipeline_executor
        self._app = app
        self._turn_manager: TurnManager | None = None
        self._stopped = False
        self._round_events: list[Any] = []
        self._team_channel: str | None = None
        self.deliverable_produced: bool = False
        self.deliverable_content: dict[str, Any] | None = None

    async def run(self) -> GameResult:
        """Main game loop."""
        definition = self._game.definition
        if definition is None:
            logger.error("GameRunner.run(): no game definition — returning immediately")
            return GameResult(reason="no_game_definition")

        players = list(self._game.player_scores.keys())
        if not players:
            logger.error("GameRunner.run(): 0 players — game cannot start")
            return GameResult(reason="no_players")

        self._turn_manager = TurnManager(
            players=players,
            order=TurnOrder.ROUND_ROBIN,
            seed=42,
        )

        await self._game.start_game()
        await self._resolve_team_channel()
        logger.info(
            "Game started: %d players (%s), %d rounds, mode=%s",
            len(players),
            ", ".join(players),
            definition.rounds.count,
            definition.mode,
        )

        win_result: WinResult | None = None

        for round_num in range(1, definition.rounds.count + 1):
            if self._stopped:
                break

            # 1. Start round
            await self._game.start_round()
            self._round_events = []

            # 2. Resource regeneration
            await self._regenerate_resources(definition)

            # 3. Player turns
            if definition.rounds.simultaneous:
                await self._run_simultaneous_round(definition)
            else:
                await self._run_sequential_round(definition)

            # 4. Between-round hooks
            if definition.between_rounds.animator_tick and self._animator:
                try:
                    await self._animator.tick(datetime.now(UTC))
                except Exception as exc:
                    logger.warning("Animator tick failed in round %d: %s", round_num, exc)

            # 5. End round + score
            standings = await self._game.end_round(round_events=self._round_events)

            # 6. Announce standings
            if definition.between_rounds.announce_scores:
                await self._announce_standings(standings, round_num, definition.rounds.count)

            # 7. Check win conditions
            win_result = await self._game.check_win_conditions()
            if win_result is not None:
                # Handle eliminations in turn manager
                for pid, score in self._game.player_scores.items():
                    if (
                        score.eliminated
                        and self._turn_manager
                        and not self._turn_manager.is_eliminated(pid)
                    ):
                        self._turn_manager.eliminate(pid)
                if win_result.winner is not None:
                    break

        result = await self._game.complete_game(win_result)

        # Build deliverable from game result
        self.deliverable_content = self._build_deliverable(result)
        self.deliverable_produced = True

        return result

    def stop(self) -> None:
        """Signal the game to stop after current round."""
        self._stopped = True

    @staticmethod
    def _build_deliverable(result: GameResult) -> dict[str, Any]:
        """Build a flat, human-readable game summary as the run deliverable."""
        # Build standings as a readable string table
        standings_lines = []
        for s in result.final_standings or []:
            rank = s.get("rank", 0)
            actor = s.get("actor_id", "")
            score = s.get("total_score", 0.0)
            eliminated = s.get("eliminated", False)
            metrics = s.get("metrics", {})
            status = "ELIMINATED" if eliminated else f"#{rank}"
            metric_parts = [f"{k}: {v:,.0f}" for k, v in metrics.items()]
            standings_lines.append(
                f"{status} {actor} — score: {score:,.1f} ({', '.join(metric_parts)})"
            )

        deliverable: dict[str, Any] = {
            "title": f"Winner: {result.winner or 'No winner'}",
            "game_mode": result.game_mode,
            "rounds_played": result.total_rounds_played,
            "result": result.reason.replace("_", " ").title(),
        }

        # Add per-player standings as flat keys
        for s in result.final_standings or []:
            rank = s.get("rank", 0)
            actor = s.get("actor_id", "").split("-")[0]
            score = s.get("total_score", 0.0)
            metrics = s.get("metrics", {})
            metric_str = " | ".join(f"{k}: {v:,.0f}" for k, v in metrics.items())
            deliverable[f"#{rank} {actor}"] = f"Score: {score:,.1f} ({metric_str})"

        return deliverable

    async def _run_sequential_round(self, definition: GameDefinition) -> None:
        """Each player takes turns in order."""
        if self._turn_manager is None:
            return
        turn_order = self._turn_manager.get_order()
        for player_id in turn_order:
            if self._stopped:
                break
            if self._turn_manager.is_eliminated(player_id):
                continue
            await self._activate_player_turn(player_id, definition.rounds.actions_per_turn)

    async def _run_simultaneous_round(self, definition: GameDefinition) -> None:
        """All players act in parallel."""
        if self._turn_manager is None:
            return
        active_players = [
            pid
            for pid in self._turn_manager.get_order()
            if not self._turn_manager.is_eliminated(pid)
        ]
        tasks = [
            self._activate_player_turn(pid, definition.rounds.actions_per_turn)
            for pid in active_players
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _activate_player_turn(self, player_id: str, max_actions: int) -> None:
        """Activate a player for their turn via the agency engine.

        The agency engine's activate_for_game_turn() runs an LLM tool loop
        that already executes actions through the governance pipeline. The
        returned envelopes are already-committed results — do NOT re-execute.
        """
        if self._agency is None:
            logger.warning("No agency engine — skipping turn for %s", player_id)
            return
        try:
            round_num = self._game.round_state.current_round
            total_rounds = self._game.round_state.total_rounds
            standings_summary = self._format_standings_brief()
            logger.info("[GAME] Activating %s round %d/%d (max %d actions)", player_id, round_num, total_rounds, max_actions)
            envelopes = await self._agency.activate_for_game_turn(
                ActorId(player_id),
                round_number=round_num,
                total_rounds=total_rounds,
                standings_summary=standings_summary,
            )
            executed = len(envelopes) if envelopes else 0
            logger.info("[GAME] %s executed %d actions", player_id, executed)

            # Record all envelopes for scoring (already executed by agency)
            for env in envelopes or []:
                action_type = getattr(env, "action_type", "") or ""
                event_type = (
                    f"world.{action_type}"
                    if action_type and not action_type.startswith("world.")
                    else action_type
                )
                self._round_events.append(
                    SimpleNamespace(
                        event_type=event_type,
                        actor_id=str(getattr(env, "actor_id", "")),
                        input_data=getattr(env, "payload", {}),
                    )
                )

            turn_event = GameTurnEvent(
                event_type="game.turn",
                timestamp=Timestamp(
                    world_time=datetime.now(UTC), wall_time=datetime.now(UTC), tick=0
                ),
                round_number=self._game.round_state.current_round,
                actor_id=ActorId(player_id),
                actions_taken=executed,
                actions_remaining=max(0, max_actions - executed),
                run_id=self._game.run_id,
            )
            await self._game.publish_event(turn_event)
        except Exception as exc:
            logger.warning("Turn activation failed for %s: %s", player_id, exc)

    def _format_standings_brief(self) -> str:
        """One-line standings summary for agent prompt injection."""
        scores = self._game.player_scores
        if not scores:
            return ""
        ranked = sorted(scores.values(), key=lambda s: s.total_score, reverse=True)
        parts = [f"#{i+1} {s.actor_id.split('-')[0]}: {s.total_score:.0f}" for i, s in enumerate(ranked)]
        return " | ".join(parts)

    async def _regenerate_resources(self, definition: GameDefinition) -> None:
        """Refill player budgets per round config."""
        if self._budget is None:
            return
        reset = definition.resource_reset_per_round
        for player_id in self._game.player_scores:
            if reset.api_calls != 0:
                await self._budget.refill(ActorId(player_id), "api_calls", reset.api_calls)
            if reset.world_actions != 0:
                await self._budget.refill(ActorId(player_id), "world_actions", reset.world_actions)

    async def _resolve_team_channel(self) -> None:
        """Find the team Slack channel from state (same logic as app.py configure_agency)."""
        try:
            state = self._game._dependencies.get("state")
            if not state:
                return
            channels = await state.query_entities("channel")
            for ch in channels:
                name = ch.get("name", "").lower()
                if name in ("general", "team", "research"):
                    self._team_channel = ch.get("id")
                    break
            if not self._team_channel and channels:
                self._team_channel = channels[0].get("id")
        except Exception:
            pass

    async def _announce_standings(
        self, standings: list[dict[str, Any]], round_num: int, total_rounds: int
    ) -> None:
        """Post current standings to team channel."""
        if not self._app or not standings:
            return
        lines = [f"Round {round_num}/{total_rounds} standings:"]
        for s in standings[:10]:
            status = "X" if s.get("eliminated") else f"#{s['rank']}"
            lines.append(f"  {status} {s['actor_id']}: {s['total_score']:.1f}")
        text = "\n".join(lines)
        input_data: dict[str, Any] = {"text": text}
        if self._team_channel:
            input_data["channel_id"] = self._team_channel
        try:
            await self._app.handle_action(
                actor_id="system-game",
                service_id="slack",
                action="chat.postMessage",
                input_data=input_data,
            )
        except Exception:
            logger.debug("Standings announcement failed")
