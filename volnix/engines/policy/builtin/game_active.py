"""GameActivePolicy — blocks negotiate_* tool calls when the game is not active.

This is a built-in policy gate that runs inside the ``policy`` pipeline
step. Its gate flag is driven by :class:`GameActiveStateChangedEvent`
published by :class:`GameOrchestrator` (flipped to ``True`` at game
start and ``False`` at termination).

Wiring (done in the composition root, Cycle B.9):

1. Create the gate instance::

       game_active_gate = GameActivePolicy()

2. Subscribe ``game_active_gate.on_event`` to ``game.active_state_changed``
   on the bus::

       await bus.subscribe(
           "game.active_state_changed",
           game_active_gate.on_event,
       )

3. Register it on the policy engine::

       policy_engine.register_gate(game_active_gate)

After termination, any late ``negotiate_*`` tool call from a
mid-activation agent is rejected with a ``DENY`` verdict.

Why a gate and not a YAML policy?
    YAML policies read from ``input`` / ``actor`` / ``action`` /
    ``service`` — none of which carry the game_active flag. The gate
    holds the flag in local state, populated from a bus event, so the
    policy engine doesn't need to grow a domain-specific eval context.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import ClassVar

from volnix.core.context import ActionContext, StepResult
from volnix.core.events import Event, PolicyBlockEvent
from volnix.core.types import PolicyId, StepVerdict, Timestamp

logger = logging.getLogger(__name__)


# The set of actions gated by the game_active flag. Any action whose
# canonical ``action`` string starts with ``"negotiate_"`` is considered
# a game move; the gate blocks these after termination so agents can't
# race past the finish line on a stale tool call.
NEGOTIATE_ACTION_PREFIX = "negotiate_"


class GameActivePolicy:
    """Built-in policy gate keyed on the ``game_active`` flag.

    The gate starts in the ``inactive`` state (``game_active = False``).
    When the orchestrator publishes
    :class:`GameActiveStateChangedEvent`, :meth:`on_event` flips the
    flag. :meth:`evaluate` blocks ``negotiate_*`` actions whenever the
    flag is ``False``.

    Thread-safety: all reads and writes happen on the event loop (no
    threading), so no lock is required.
    """

    NAME: ClassVar[str] = "game_active"
    STEP_NAME: ClassVar[str] = "policy.game_active"

    def __init__(self) -> None:
        self._game_active: bool = False

    # ------------------------------------------------------------------
    # State mutation
    # ------------------------------------------------------------------

    def set_active(self, active: bool) -> None:
        """Directly flip the ``game_active`` flag.

        Useful for tests and for any composition-root wiring that
        prefers direct injection over bus subscriptions.
        """
        self._game_active = bool(active)
        logger.debug("GameActivePolicy: game_active set to %s", self._game_active)

    @property
    def is_active(self) -> bool:
        """Return the current ``game_active`` flag."""
        return self._game_active

    # ------------------------------------------------------------------
    # Bus subscription callback
    # ------------------------------------------------------------------

    async def on_event(self, event: Event) -> None:
        """Handle a bus event. Only ``game.active_state_changed`` is recognized.

        The subscription is registered by the composition root. This
        method tolerates any event type (silently ignores non-matching
        events) so subscribers can be mounted with wildcard-safe
        subscription patterns.
        """
        if getattr(event, "event_type", "") != "game.active_state_changed":
            return
        new_state = bool(getattr(event, "active", False))
        if new_state != self._game_active:
            logger.info(
                "GameActivePolicy: game_active flipping %s -> %s via bus event",
                self._game_active,
                new_state,
            )
        self._game_active = new_state

    # ------------------------------------------------------------------
    # Policy gate interface (called by PolicyEngine.execute)
    # ------------------------------------------------------------------

    async def evaluate(self, ctx: ActionContext) -> StepResult:
        """Return ``DENY`` for gated actions when the game is not active.

        Non-negotiate actions always return ``ALLOW``. Negotiate actions
        return ``ALLOW`` while the game is active, and ``DENY`` with a
        :class:`PolicyBlockEvent` when the game has ended or hasn't
        started yet.
        """
        if not self._is_game_action(ctx.action):
            return StepResult(step_name=self.STEP_NAME, verdict=StepVerdict.ALLOW)

        if self._game_active:
            return StepResult(step_name=self.STEP_NAME, verdict=StepVerdict.ALLOW)

        reason = (
            f"GameActivePolicy: game is not active — action '{ctx.action}' "
            f"rejected (actor={ctx.actor_id})"
        )
        now = datetime.now(UTC)
        block_event = PolicyBlockEvent(
            event_type="policy.block",
            timestamp=Timestamp(world_time=now, wall_time=now, tick=0),
            policy_id=PolicyId(self.NAME),
            actor_id=ctx.actor_id,
            action=ctx.action,
            reason=reason,
            run_id=str(ctx.run_id) if ctx.run_id else None,
        )
        return StepResult(
            step_name=self.STEP_NAME,
            verdict=StepVerdict.DENY,
            events=[block_event],
            message=reason,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_game_action(action: str) -> bool:
        """Return True if the action is gated by ``game_active``."""
        if not action:
            return False
        # Match either a bare negotiate action ("negotiate_propose") or
        # a service-qualified form ("game.negotiate_propose").
        if action.startswith(NEGOTIATE_ACTION_PREFIX):
            return True
        if "." in action:
            _, local = action.rsplit(".", 1)
            return local.startswith(NEGOTIATE_ACTION_PREFIX)
        return False
