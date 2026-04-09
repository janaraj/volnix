"""Escalation handler -- subscribes to policy.escalate events and posts notifications.

Routes escalation notices to team communication channels via the standard
pipeline.  Not an engine -- a bus subscriber wired during app startup.
"""

from __future__ import annotations

import logging
from typing import Any

from volnix.core.events import PolicyEscalateEvent
from volnix.core.types import ActorId, ServiceId

logger = logging.getLogger(__name__)


class EscalationHandler:
    """Subscribes to policy.escalate events and posts notifications."""

    def __init__(self, app: Any, bus: Any, state_engine: Any = None) -> None:
        self._app = app
        self._bus = bus
        self._state_engine = state_engine

    async def start(self) -> None:
        """Subscribe to escalation events on the bus."""
        if self._bus is not None:
            await self._bus.subscribe("policy.escalate", self._handle_escalation)

    async def _handle_escalation(self, event: PolicyEscalateEvent) -> None:
        """Post escalation notice to team channel."""
        # Prevent recursive escalations — system actors don't trigger escalation handling
        if str(event.actor_id).startswith("system-"):
            logger.debug("Skipping escalation for system actor %s", event.actor_id)
            return

        channel = await self._find_team_channel()
        if channel is None:
            logger.warning(
                "No communication channel for escalation %s (target_role=%s)",
                event.event_id,
                event.target_role,
            )
            return

        message = (
            f"[ESCALATION] Action '{event.action}' by {event.actor_id} "
            f"escalated to {event.target_role}. Policy: {event.policy_id}"
        )

        try:
            await self._app.handle_action(
                actor_id=ActorId("system-escalation"),
                service_id=ServiceId(channel["service_id"]),
                action=channel["post_action"],
                input_data={"channel": channel["channel_id"], "text": message},
            )
        except Exception as exc:
            logger.warning("Escalation notification failed: %s", exc)

    async def _find_team_channel(self) -> dict[str, str] | None:
        """Find team communication channel from state."""
        if self._state_engine is None:
            return None
        try:
            entities = await self._state_engine.query_entities(
                entity_type="channel",
            )
            if entities:
                first = entities[0]
                service_id = first.get("service_id", "")
                channel_id = first.get("id", first.get("entity_id", ""))
                if not service_id or not channel_id:
                    logger.warning("Channel entity missing service_id or id: %s", first)
                    return None
                return {
                    "service_id": service_id,
                    "post_action": "chat_postMessage",
                    "channel_id": channel_id,
                }
        except (KeyError, AttributeError, TypeError) as exc:
            logger.debug("Channel lookup failed: %s", exc)
        return None
