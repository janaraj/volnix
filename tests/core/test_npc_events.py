"""Tests for the Active-NPC event types (Layer 1 scaffold).

No runtime wiring yet — these tests only verify the event models are
frozen, carry the right fields, and can be instantiated cleanly.
Subscription / pipeline integration lives in Phase 2.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from volnix.core.events import (
    NPCDailyTickEvent,
    NPCExposureEvent,
    NPCInterviewProbeEvent,
    NPCStateChangedEvent,
    WordOfMouthEvent,
)
from volnix.core.types import ActorId, ServiceId, Timestamp


def _ts() -> Timestamp:
    now = datetime.now(UTC)
    return Timestamp(world_time=now, wall_time=now, tick=0)


# -- NPCExposureEvent ---------------------------------------------------------


class TestNPCExposureEvent:
    def test_construct_required_fields(self) -> None:
        e = NPCExposureEvent(
            event_type="npc.exposure",
            timestamp=_ts(),
            actor_id=ActorId("npc-1"),
            service_id=ServiceId("vibemesh"),
            action="expose",
            npc_id=ActorId("npc-1"),
            feature_id="drop_flare",
            source="seed",
        )
        assert e.npc_id == ActorId("npc-1")
        assert e.feature_id == "drop_flare"
        assert e.source == "seed"
        assert e.medium is None

    def test_medium_optional(self) -> None:
        e = NPCExposureEvent(
            event_type="npc.exposure",
            timestamp=_ts(),
            actor_id=ActorId("npc-1"),
            service_id=ServiceId("vibemesh"),
            action="expose",
            npc_id=ActorId("npc-1"),
            feature_id="drop_flare",
            source="animator",
            medium="push_notification",
        )
        assert e.medium == "push_notification"

    def test_frozen(self) -> None:
        e = NPCExposureEvent(
            event_type="npc.exposure",
            timestamp=_ts(),
            actor_id=ActorId("npc-1"),
            service_id=ServiceId("s"),
            action="a",
            npc_id=ActorId("npc-1"),
            feature_id="f",
            source="seed",
        )
        with pytest.raises(Exception):
            e.feature_id = "mutated"  # type: ignore[misc]


# -- WordOfMouthEvent ---------------------------------------------------------


class TestWordOfMouthEvent:
    def test_construct(self) -> None:
        e = WordOfMouthEvent(
            event_type="npc.word_of_mouth",
            timestamp=_ts(),
            actor_id=ActorId("npc-A"),
            service_id=ServiceId("npc_chat"),
            action="send_message",
            sender_id=ActorId("npc-A"),
            recipient_id=ActorId("npc-B"),
            feature_id="drop_flare",
            sentiment="positive",
        )
        assert e.sender_id == ActorId("npc-A")
        assert e.recipient_id == ActorId("npc-B")
        assert e.sentiment == "positive"


# -- NPCInterviewProbeEvent ---------------------------------------------------


class TestNPCInterviewProbeEvent:
    def test_construct(self) -> None:
        e = NPCInterviewProbeEvent(
            event_type="npc.interview_probe",
            timestamp=_ts(),
            actor_id=ActorId("researcher-1"),
            service_id=ServiceId("research_tools"),
            action="interview",
            researcher_id=ActorId("researcher-1"),
            npc_id=ActorId("npc-3"),
            prompt="How would you feel if this disappeared?",
        )
        assert e.researcher_id == ActorId("researcher-1")
        assert e.npc_id == ActorId("npc-3")
        assert e.prompt.startswith("How would")
        assert e.context == {}

    def test_context_dict(self) -> None:
        e = NPCInterviewProbeEvent(
            event_type="npc.interview_probe",
            timestamp=_ts(),
            actor_id=ActorId("r"),
            service_id=ServiceId("research_tools"),
            action="interview",
            researcher_id=ActorId("r"),
            npc_id=ActorId("npc-3"),
            prompt="?",
            context={"probe_id": "p-1", "follow_up": True},
        )
        assert e.context["probe_id"] == "p-1"


# -- NPCStateChangedEvent -----------------------------------------------------


class TestNPCStateChangedEvent:
    def test_construct(self) -> None:
        e = NPCStateChangedEvent(
            event_type="npc.state_changed",
            timestamp=_ts(),
            npc_id=ActorId("npc-1"),
            before={"interest": 0.0},
            after={"interest": 0.4},
        )
        assert e.before == {"interest": 0.0}
        assert e.after == {"interest": 0.4}
        assert e.cause_event_id is None


# -- NPCDailyTickEvent --------------------------------------------------------


class TestNPCDailyTickEvent:
    def test_construct(self) -> None:
        e = NPCDailyTickEvent(
            event_type="npc.daily_tick",
            timestamp=_ts(),
            npc_id=ActorId("npc-1"),
            sim_day=3,
        )
        assert e.npc_id == ActorId("npc-1")
        assert e.sim_day == 3
