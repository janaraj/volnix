"""Tests for :class:`NPCPromptBuilder` — Active-NPC prompt rendering."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from volnix.actors.activation_profile import (
    ActivationProfile,
    ActivationTrigger,
    BudgetDefaults,
    ToolScope,
)
from volnix.actors.state import ActorState, InteractionRecord
from volnix.core.events import (
    NPCDailyTickEvent,
    NPCExposureEvent,
    NPCInterviewProbeEvent,
    WordOfMouthEvent,
)
from volnix.core.types import ActorId, ServiceId, Timestamp
from volnix.engines.agency.npc_prompt_builder import NPCPromptBuilder

# -- helpers ------------------------------------------------------------------


def _ts() -> Timestamp:
    now = datetime.now(UTC)
    return Timestamp(world_time=now, wall_time=now, tick=0)


def _profile(template: str = "consumer_user_decision.j2") -> ActivationProfile:
    return ActivationProfile(
        name="consumer_user",
        description="test consumer",
        state_schema={
            "type": "object",
            "properties": {
                "awareness": {"type": "number", "default": 0},
                "interest": {"type": "number", "default": 0},
                "satisfaction": {"type": "number", "default": 0.5},
                "usage_count": {"type": "integer", "default": 0},
                "known_features": {"type": "array", "default": []},
                "sentiment": {"type": "string", "default": "neutral"},
            },
        },
        activation_triggers=[ActivationTrigger(event="npc.exposure")],
        prompt_template=template,
        tool_scope=ToolScope(read=["vibemesh"], write=["vibemesh"]),
        budget_defaults=BudgetDefaults(),
    )


def _actor(*, persona: dict | None = None, npc_state: dict | None = None) -> ActorState:
    return ActorState(
        actor_id=ActorId("npc-1"),
        role="consumer",
        actor_type="internal",
        persona=persona or {"description": "Gen-Z burnt-out urbanite"},
        npc_state=npc_state
        or {
            "awareness": 0.2,
            "interest": 0.1,
            "satisfaction": 0.5,
            "usage_count": 0,
            "known_features": [],
            "sentiment": "neutral",
        },
        activation_profile_name="consumer_user",
    )


# -- tests --------------------------------------------------------------------


class TestNPCPromptBuilder:
    def test_includes_persona(self) -> None:
        builder = NPCPromptBuilder()
        prompt = builder.build(
            state=_actor(),
            profile=_profile(),
            trigger_event=None,
            recent_events=[],
            available_tools=[{"name": "drop_flare", "description": "Drop a flare"}],
        )
        assert "Gen-Z burnt-out urbanite" in prompt

    def test_includes_npc_state_fields(self) -> None:
        builder = NPCPromptBuilder()
        prompt = builder.build(
            state=_actor(
                npc_state={
                    "awareness": 0.73,
                    "interest": 0.42,
                    "satisfaction": 0.6,
                    "usage_count": 2,
                    "known_features": ["flare"],
                    "sentiment": "positive",
                }
            ),
            profile=_profile(),
            trigger_event=None,
            recent_events=[],
            available_tools=[],
        )
        assert "0.73" in prompt  # awareness
        assert "0.42" in prompt  # interest
        assert "positive" in prompt
        assert "flare" in prompt

    def test_includes_available_tools(self) -> None:
        builder = NPCPromptBuilder()
        prompt = builder.build(
            state=_actor(),
            profile=_profile(),
            trigger_event=None,
            recent_events=[],
            available_tools=[
                {"name": "drop_flare", "description": "Start a hangout"},
                {"name": "enter_pocket", "description": "Join a pocket"},
            ],
        )
        assert "drop_flare" in prompt
        assert "enter_pocket" in prompt

    def test_recent_events_rendered(self) -> None:
        builder = NPCPromptBuilder()
        prompt = builder.build(
            state=_actor(),
            profile=_profile(),
            trigger_event=None,
            recent_events=[{"summary": "A friend posted a flare yesterday"}],
            available_tools=[],
        )
        assert "A friend posted a flare yesterday" in prompt

    def test_trigger_description_for_exposure(self) -> None:
        builder = NPCPromptBuilder()
        event = NPCExposureEvent(
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
        prompt = builder.build(
            state=_actor(),
            profile=_profile(),
            trigger_event=event,
            recent_events=[],
            available_tools=[],
        )
        assert "drop_flare" in prompt
        assert "push_notification" in prompt

    def test_trigger_description_for_word_of_mouth(self) -> None:
        builder = NPCPromptBuilder()
        event = WordOfMouthEvent(
            event_type="npc.word_of_mouth",
            timestamp=_ts(),
            actor_id=ActorId("npc-2"),
            service_id=ServiceId("npc_chat"),
            action="send_message",
            sender_id=ActorId("npc-2"),
            recipient_id=ActorId("npc-1"),
            feature_id="enter_pocket",
            sentiment="positive",
        )
        prompt = builder.build(
            state=_actor(),
            profile=_profile(),
            trigger_event=event,
            recent_events=[],
            available_tools=[],
        )
        assert "positive" in prompt
        assert "enter_pocket" in prompt

    def test_trigger_description_for_interview(self) -> None:
        builder = NPCPromptBuilder()
        event = NPCInterviewProbeEvent(
            event_type="npc.interview_probe",
            timestamp=_ts(),
            actor_id=ActorId("researcher-1"),
            service_id=ServiceId("research_tools"),
            action="interview",
            researcher_id=ActorId("researcher-1"),
            npc_id=ActorId("npc-1"),
            prompt="How would you feel if this disappeared?",
        )
        prompt = builder.build(
            state=_actor(),
            profile=_profile(),
            trigger_event=event,
            recent_events=[],
            available_tools=[],
        )
        assert "How would you feel if this disappeared?" in prompt

    def test_trigger_description_for_daily_tick(self) -> None:
        builder = NPCPromptBuilder()
        event = NPCDailyTickEvent(
            event_type="npc.daily_tick",
            timestamp=_ts(),
            npc_id=ActorId("npc-1"),
            sim_day=7,
        )
        prompt = builder.build(
            state=_actor(),
            profile=_profile(),
            trigger_event=event,
            recent_events=[],
            available_tools=[],
        )
        assert "day 7" in prompt or "sim_day" in prompt or "7" in prompt

    def test_no_trigger_fallback(self) -> None:
        builder = NPCPromptBuilder()
        prompt = builder.build(
            state=_actor(),
            profile=_profile(),
            trigger_event=None,
            recent_events=[],
            available_tools=[],
        )
        assert "routine day" in prompt

    def test_recent_interactions_carried_through(self) -> None:
        """Ensure InteractionRecord objects on ActorState feed properly."""
        builder = NPCPromptBuilder()
        actor = _actor()
        actor.recent_interactions = [
            InteractionRecord(
                tick=5,
                actor_id="npc-2",
                actor_role="consumer",
                action="drop_flare",
                summary="A friend dropped a flare at the park",
                source="observed",
                event_id="evt-1",
            )
        ]
        prompt = builder.build(
            state=actor,
            profile=_profile(),
            trigger_event=None,
            recent_events=[{"summary": ir.summary} for ir in actor.recent_interactions],
            available_tools=[],
        )
        assert "dropped a flare at the park" in prompt

    def test_missing_template_raises(self) -> None:
        builder = NPCPromptBuilder()
        with pytest.raises(Exception):  # Jinja2 TemplateNotFound
            builder.build(
                state=_actor(),
                profile=_profile(template="does_not_exist.j2"),
                trigger_event=None,
                recent_events=[],
                available_tools=[],
            )

    def test_generic_world_event_fallback(self) -> None:
        """An unknown WorldEvent subtype routes to the generic
        ``Something happened`` branch — not a known-NPC-event branch."""
        from volnix.core.events import WorldEvent

        builder = NPCPromptBuilder()
        generic = WorldEvent(
            event_type="some.other.event",
            timestamp=_ts(),
            actor_id=ActorId("npc-1"),
            service_id=ServiceId("vibemesh"),
            action="whatever",
        )
        prompt = builder.build(
            state=_actor(),
            profile=_profile(),
            trigger_event=generic,
            recent_events=[],
            available_tools=[],
        )
        assert "some.other.event" in prompt

    def test_non_world_event_fallback(self) -> None:
        """A non-WorldEvent ``Event`` falls back to ``Event: <type>``."""
        from volnix.core.events import Event

        builder = NPCPromptBuilder()
        ev = Event(event_type="meta.noop", timestamp=_ts())
        prompt = builder.build(
            state=_actor(),
            profile=_profile(),
            trigger_event=ev,
            recent_events=[],
            available_tools=[],
        )
        assert "meta.noop" in prompt


# ---------------------------------------------------------------------------
# PMF 4B Step 11 — recalled memories rendering
# ---------------------------------------------------------------------------


def _semantic_record(owner: str, content: str, importance: float):
    """Build a semantic MemoryRecord for prompt-rendering tests."""
    import hashlib

    from volnix.core.memory_types import MemoryRecord, content_hash_of
    from volnix.core.types import MemoryRecordId

    return MemoryRecord(
        record_id=MemoryRecordId(f"sem-{hashlib.sha256(content.encode()).hexdigest()[:8]}"),
        scope="actor",
        owner_id=owner,
        kind="semantic",
        tier="tier2",
        source="consolidated",
        content=content,
        content_hash=content_hash_of(content),
        importance=importance,
        tags=[],
        created_tick=0,
        consolidated_from=[MemoryRecordId("episodic-parent-1")],
    )


def _episodic_record(owner: str, content: str, importance: float):
    import hashlib

    from volnix.core.memory_types import MemoryRecord, content_hash_of
    from volnix.core.types import MemoryRecordId

    return MemoryRecord(
        record_id=MemoryRecordId(f"epi-{hashlib.sha256(content.encode()).hexdigest()[:8]}"),
        scope="actor",
        owner_id=owner,
        kind="episodic",
        tier="tier2",
        source="implicit",
        content=content,
        content_hash=content_hash_of(content),
        importance=importance,
        tags=[],
        created_tick=0,
        consolidated_from=None,
    )


class TestRecalledMemoriesRendering:
    """PMF 4B Step 11 — memory injection into NPC prompt.

    Negative-first: None and empty recall must render NOTHING so
    the Phase 0 regression oracle stays byte-identical.
    """

    def test_negative_none_recall_renders_no_memory_section(self) -> None:
        builder = NPCPromptBuilder()
        out = builder.build(
            state=_actor(),
            profile=_profile(),
            trigger_event=None,
            recent_events=[],
            available_tools=[],
            recalled_memories=None,
        )
        assert "Memories you recall" not in out

    def test_negative_empty_recall_renders_no_memory_section(self) -> None:
        """Empty ``records`` must hide the section (byte-identical
        to pre-Step-11 behaviour for Phase 0 oracle)."""
        from volnix.core.memory_types import MemoryRecall

        builder = NPCPromptBuilder()
        empty = MemoryRecall(query_id="q-1", records=[], total_matched=0, truncated=False)
        out = builder.build(
            state=_actor(),
            profile=_profile(),
            trigger_event=None,
            recent_events=[],
            available_tools=[],
            recalled_memories=empty,
        )
        assert "Memories you recall" not in out

    def test_positive_non_empty_recall_renders_section_with_records(self) -> None:
        from volnix.core.memory_types import MemoryRecall

        builder = NPCPromptBuilder()
        rec1 = _semantic_record("npc-1", "Alice prefers quiet coffee shops", 0.8)
        rec2 = _episodic_record("npc-1", "Had good experience with drop_flare", 0.5)
        recall = MemoryRecall(
            query_id="q-1", records=[rec1, rec2], total_matched=2, truncated=False
        )
        out = builder.build(
            state=_actor(),
            profile=_profile(),
            trigger_event=None,
            recent_events=[],
            available_tools=[],
            recalled_memories=recall,
        )
        assert "Memories you recall" in out
        assert "Alice prefers quiet coffee shops" in out
        assert "Had good experience with drop_flare" in out

    def test_positive_memory_section_placed_between_persona_and_state(self) -> None:
        """Placement invariant — persona first, memories second,
        current state third."""
        from volnix.core.memory_types import MemoryRecall

        builder = NPCPromptBuilder()
        rec = _semantic_record("npc-1", "marker-content-xyz", 0.9)
        recall = MemoryRecall(query_id="q", records=[rec], total_matched=1, truncated=False)
        out = builder.build(
            state=_actor(),
            profile=_profile(),
            trigger_event=None,
            recent_events=[],
            available_tools=[],
            recalled_memories=recall,
        )
        idx_persona = out.index("## Your persona")
        idx_memory = out.index("## Memories you recall")
        idx_state = out.index("## Your current state")
        assert idx_persona < idx_memory < idx_state
        assert "marker-content-xyz" in out
