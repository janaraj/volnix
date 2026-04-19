"""NPC prompt builder — renders Active-NPC decision prompts from Jinja2 templates.

Sibling to :mod:`volnix.engines.agency.prompt_builder` but narrow in
scope. An Active NPC's prompt is persona-driven, not task-driven: it
reflects the NPC's current state (awareness/interest/satisfaction), the
triggering event, and the tool scope declared in the activation
profile. We deliberately don't share code with ``ActorPromptBuilder``
— agent prompts cover delegation, synthesis, and multi-phase lifecycles
that are irrelevant here, and coupling the two paths would make both
harder to evolve.

Templates live under
``volnix/actors/npc_profiles/prompts/`` and are referenced by name in
each activation profile. The builder is stateless; one instance can
serve any number of profiles.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from volnix.actors.activation_profile import ActivationProfile
from volnix.actors.state import ActorState
from volnix.core.events import Event, WorldEvent

logger = logging.getLogger(__name__)


# Templates are colocated with profiles so a profile + its template move together.
_TEMPLATE_DIR = (
    Path(__file__).resolve().parent.parent.parent / "actors" / "npc_profiles" / "prompts"
)


class NPCPromptBuilder:
    """Renders persona-driven activation prompts for Active NPCs."""

    def __init__(self, template_dir: Path | None = None) -> None:
        self._template_dir = template_dir or _TEMPLATE_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(self._template_dir)),
            autoescape=select_autoescape([]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def build(
        self,
        *,
        state: ActorState,
        profile: ActivationProfile,
        trigger_event: Event | None,
        recent_events: list[dict[str, Any]],
        available_tools: list[dict[str, Any]],
        recalled_memories: Any = None,
    ) -> str:
        """Render the decision prompt for this NPC activation.

        Args:
            state: The NPC's current mutable state. ``state.persona`` is
                read as a dict (may be empty); ``state.npc_state``
                carries the per-profile awareness/interest/etc.
            profile: The activation profile (selected via
                ``state.activation_profile_name``).
            trigger_event: The event that woke the NPC, if any.
            recent_events: Short list of dicts describing recent events
                the NPC is aware of. Each item has at least a
                ``summary`` key.
            available_tools: Tool descriptors scoped by
                ``profile.tool_scope``. Each dict has ``name`` and
                ``description``.
            recalled_memories: PMF 4B Step 11 — optional
                :class:`volnix.core.memory_types.MemoryRecall`. When
                ``None`` or empty (``records == []``), the memory
                section renders as nothing so the pre-Step-11 output
                stays byte-identical. When non-empty, each record's
                content is listed under the "Memories you recall"
                heading between persona and current state.

        Returns:
            The rendered prompt string, ready to send to the LLM.
        """
        tmpl = self._env.get_template(profile.prompt_template)
        persona_text = ""
        if state.persona:
            # Persona is a Pydantic dump — use the description field if
            # present, else fall back to a flat string representation so
            # the LLM sees the full picture either way.
            persona_text = state.persona.get("description") or str(state.persona)
        return tmpl.render(
            persona=persona_text,
            npc_state=state.npc_state or {},
            trigger_description=self._describe(trigger_event),
            recent_events=recent_events,
            available_tools=available_tools,
            recalled_memories=recalled_memories,
        )

    @staticmethod
    def _describe(event: Event | None) -> str:
        """Translate a trigger event into a one-line natural-language summary.

        Known NPC-trigger events get tailored phrasing. Anything else
        falls back to the event type so the template always has content.
        """
        if event is None:
            return "(no specific trigger — routine day)"

        etype = getattr(event, "event_type", "")

        # WorldEvent metadata / direct attrs for NPC-trigger events.
        if etype == "npc.exposure":
            medium = getattr(event, "medium", None) or "an unspecified channel"
            feature = getattr(event, "feature_id", "a product")
            return f"You encountered {feature} via {medium}."
        if etype == "npc.word_of_mouth":
            sender = getattr(event, "sender_id", "someone")
            feature = getattr(event, "feature_id", "a product")
            sentiment = getattr(event, "sentiment", "neutral")
            return f"A friend ({sender}) mentioned {feature} to you — their tone was {sentiment}."
        if etype == "npc.interview_probe":
            prompt = getattr(event, "prompt", "")
            return f"A researcher asks: {prompt}"
        if etype == "npc.daily_tick":
            sim_day = getattr(event, "sim_day", "?")
            return f"A new simulated day has begun (day {sim_day})."

        # Generic fallback for other events a subscription may route here.
        if isinstance(event, WorldEvent):
            return (
                f"Something happened in the world: {etype} from {getattr(event, 'actor_id', '?')}."
            )
        return f"Event: {etype or 'unknown'}"
