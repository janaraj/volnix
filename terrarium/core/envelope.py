"""ActionEnvelope -- universal action shape for all actions in the world.

Every action (external agent, internal actor, environment) is wrapped in
an ActionEnvelope before entering the EventQueue.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from terrarium.core.types import (
    ActionSource,
    ActorId,
    EnvelopeId,
    EnvelopePriority,
    EventId,
    ServiceId,
)


def _generate_envelope_id() -> EnvelopeId:
    """Generate a globally unique envelope identifier."""
    return EnvelopeId(f"env-{uuid.uuid4().hex[:12]}")


class ActionEnvelope(BaseModel, frozen=True):
    """Universal action shape. Every action in the world is an ActionEnvelope."""

    envelope_id: EnvelopeId = Field(default_factory=_generate_envelope_id)
    actor_id: ActorId
    source: ActionSource
    action_type: str  # service-specific action name
    target_service: ServiceId | None = None  # which service (None for meta-actions)
    payload: dict[str, Any] = Field(default_factory=dict)
    logical_time: float = 0.0  # ordering key
    priority: EnvelopePriority = EnvelopePriority.INTERNAL
    parent_event_ids: list[EventId] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
