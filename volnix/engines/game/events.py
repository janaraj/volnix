"""Game-specific event types published by :class:`GameOrchestrator`.

Every event is a frozen Pydantic model inheriting from
:class:`volnix.core.events.Event`. Subscribers (reporter, CLI,
policy gate) read these off the bus.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from volnix.core.events import Event
from volnix.core.types import ActorId


class GameScoreUpdatedEvent(Event):
    """Published after each committed game event for every player.

    The orchestrator publishes one event per player per committed
    game tool call so subscribers can track incremental score changes
    without polling. Value is the player's current ``total_score``.
    """

    actor_id: ActorId
    metric: str = ""
    value: float = 0.0


class GameEliminationEvent(Event):
    """Published when a player is eliminated (budget exhausted or policy)."""

    actor_id: ActorId
    reason: str = ""
    event_number: int = 0


# ---------------------------------------------------------------------------
# Lifecycle events (published by GameOrchestrator)
# ---------------------------------------------------------------------------


class GameKickstartEvent(Event):
    """Published by GameOrchestrator after kickstart completes.

    Announces that the game is now active, the first mover has been
    activated, and any subscriber watching for game start can begin
    doing its thing (e.g. the animator starts its tick schedule).

    Fields:
        run_id: The run this game belongs to.
        first_mover: Role or actor_id of the player that was kickstarted.
            Empty string if ``activation_mode == "parallel"`` (all players
            activated at once).
        num_players: Total number of game players.
    """

    run_id: str = ""
    first_mover: str = ""
    num_players: int = 0


class GameTimeoutEvent(Event):
    """Published by orchestrator's failsafe timers. Drives Path B termination.

    The orchestrator has 4 failsafe sources that all publish this event:

    - wall_clock: ``max_wall_clock_seconds`` elapsed
    - stalemate: no committed game events for ``stalemate_timeout_seconds``
    - max_events: committed event counter reached ``max_events``
    - all_budgets: every player's ``world_actions`` budget exhausted

    All four converge on the same settlement pipeline:
    orchestrator.``_handle_timeout`` → ``scorer.settle(open_deals)`` →
    ``GameTerminatedEvent`` publication.

    Fields:
        reason: One of ``"wall_clock"``, ``"stalemate"``, ``"max_events"``,
            ``"all_budgets"``.
        event_number: The orchestrator's event counter at the time of
            timeout. Zero for wall_clock/stalemate timers that fire
            without an event number; non-zero for max_events.
    """

    reason: str = ""
    event_number: int = 0


class GameActiveStateChangedEvent(Event):
    """Flips the ``game_active`` flag for GameActivePolicy.

    Published by the orchestrator at two points:

    - ``active=True`` at game start (during ``_on_start`` kickstart)
    - ``active=False`` at termination (both Path A natural win and
      Path B timeout)

    GameActivePolicy subscribes to this event and flips its gate.
    After termination, any late ``negotiate_*`` tool call from an
    agent mid-activation is rejected with policy deny.

    Fields:
        active: New state of the flag (``True`` = game running,
            ``False`` = game terminated / not started).
        run_id: The run this event applies to.
    """

    active: bool = False
    run_id: str = ""


class GameTerminatedEvent(Event):
    """Final event of a game. Published by orchestrator on both termination paths.

    Path A (natural win, e.g. ``deal_closed``): ``reason`` is the
    win-condition's reason string. ``winner`` is set (competitive
    mode) or ``None`` (behavioral mode).

    Path B (timeout with settlement): ``reason`` is the timeout
    reason (``wall_clock``, ``stalemate``, ``max_events``,
    ``all_budgets``). ``winner`` is ``None`` in almost all cases
    unless the scorer's settle() produces a clear winner.

    The CLI's ``volnix run`` blocks on an asyncio.Future that the
    orchestrator resolves when this event is published. See
    ``GameOrchestrator.await_result``.

    Fields:
        winner: Winning actor (competitive mode + natural win only).
        reason: Why the game ended.
        final_standings: Ordered standings list (competitive).
        behavior_scores: Per-actor behavior metrics (behavioral mode).
        total_events: Total committed game-tool events in this game.
        wall_clock_seconds: Wall-clock duration from game start.
        scoring_mode: ``"behavioral"`` or ``"competitive"``.
    """

    winner: ActorId | None = None
    reason: str = ""
    final_standings: list[dict[str, Any]] = Field(default_factory=list)
    behavior_scores: dict[str, dict[str, float]] = Field(default_factory=dict)
    total_events: int = 0
    wall_clock_seconds: float = 0.0
    scoring_mode: str = "behavioral"


class GameEngineErrorEvent(Event):
    """Published when the orchestrator's scorer / win evaluator / settlement raises.

    The game continues on failure (a single scorer hiccup shouldn't kill
    an entire run), but subscribers (reporter, CLI progress UI, alerting)
    need a bus signal to react to. This is the observability companion
    for the broad ``except Exception`` guards in the orchestrator that
    would otherwise only emit a ``logger.exception`` stack trace.

    Fields:
        source: Which orchestrator operation raised. One of
            ``"score_event"``, ``"win_check"``, ``"settle"``,
            ``"state_query"``, ``"state_summary"``.
        event_number: The orchestrator's event counter at the time of
            failure. Zero for failures outside per-event handling.
        message: Human-readable error string (the exception's ``str()``).
        exception_type: Fully-qualified exception class name.
        run_id: The run this applies to.
    """

    source: str = ""
    event_number: int = 0
    message: str = ""
    exception_type: str = ""
    run_id: str = ""
