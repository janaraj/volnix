"""Tests for :class:`volnix.actors.queued_event.QueuedEvent`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from volnix.actors.queued_event import QueuedEvent
from volnix.core.events import NPCExposureEvent
from volnix.core.types import ActorId, EventId, ServiceId, Timestamp


def _ts() -> Timestamp:
    now = datetime.now(UTC)
    return Timestamp(world_time=now, wall_time=now, tick=0)


def _event() -> NPCExposureEvent:
    return NPCExposureEvent(
        event_id=EventId("e1"),
        event_type="npc.exposure",
        timestamp=_ts(),
        actor_id=ActorId("animator"),
        service_id=ServiceId("npc_system"),
        action="expose",
        npc_id=ActorId("npc-1"),
        feature_id="drop_flare",
        source="seed",
    )


def test_construct() -> None:
    q = QueuedEvent(event=_event(), queued_tick=5, reason="defer_inactive")
    assert q.queued_tick == 5
    assert q.reason == "defer_inactive"
    assert q.event_type == "npc.exposure"


def test_frozen() -> None:
    q = QueuedEvent(event=_event(), queued_tick=1, reason="r")
    with pytest.raises(Exception):  # Pydantic frozen validation
        q.reason = "mutated"  # type: ignore[misc]


def test_event_type_proxy_matches_underlying() -> None:
    q = QueuedEvent(event=_event(), queued_tick=0, reason="r")
    assert q.event_type == q.event.event_type
