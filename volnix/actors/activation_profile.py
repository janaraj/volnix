"""ActivationProfile — opt-in LLM-activation spec for HUMAN actors.

An ``ActivationProfile`` is a frozen, reusable description of how an
LLM-activated HUMAN actor (a.k.a. an "Active NPC") behaves: what events
wake it up, what persistent state it carries, which tools it may use,
and which Jinja2 prompt template renders its decision context.

Passive NPCs (HUMAN actors without an ``activation_profile`` on their
``ActorDefinition``) are unaffected by this module — they continue to
receive events generated on their behalf by the Animator and are never
registered as ``ActorState`` objects. See
``tests/integration/test_passive_npc_regression.py`` for the
compile-time oracle that locks that contract.

One profile may be referenced by many actors. Profiles are loaded from
YAML files under ``volnix/actors/npc_profiles/`` via
:func:`volnix.actors.npc_profiles.load_activation_profile`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class ActivationTrigger(BaseModel, frozen=True):
    """One thing that wakes up an Active NPC.

    Exactly one of ``event`` or ``scheduled`` must be set. This is
    enforced by the validator below, not at the call site, so that a
    malformed profile YAML fails loudly at load time.
    """

    event: str | None = None
    scheduled: str | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> ActivationTrigger:
        has_event = self.event is not None
        has_scheduled = self.scheduled is not None
        if has_event == has_scheduled:
            raise ValueError(
                "ActivationTrigger: exactly one of 'event' or 'scheduled' must be set "
                f"(got event={self.event!r}, scheduled={self.scheduled!r})"
            )
        return self


class ToolScope(BaseModel, frozen=True):
    """Allow-lists governing which services a profile may read/write.

    The scope is evaluated in Phase 2 when the profile is used to build
    the tool surface for an Active NPC activation. Absent lists mean
    "nothing allowed."
    """

    read: list[str] = Field(default_factory=list)
    write: list[str] = Field(default_factory=list)


class BudgetDefaults(BaseModel, frozen=True):
    """Default per-activation budget for Active NPCs using this profile.

    Can be overridden by explicit ``budget`` on an ``ActorDefinition``.
    """

    api_calls: int = 20
    llm_spend: float = 0.50


class ActivationProfile(BaseModel, frozen=True):
    """Complete description of an Active-NPC archetype.

    Attributes:
        name: Profile identifier (matches the YAML filename stem).
        description: Human-readable summary for registries and UIs.
        state_schema: JSON Schema for the per-NPC ``npc_state`` dict.
            Used to validate initial state and any mutation committed
            through the State Engine.
        activation_triggers: Ordered list of what wakes this kind of
            NPC. Phase 2 wires each to a bus subscription or scheduler.
        prompt_template: Filename (relative to
            ``volnix/actors/npc_profiles/prompts/``) of the Jinja2
            template that renders the NPC's decision prompt.
        tool_scope: Read/write service allow-lists.
        budget_defaults: Default per-activation budget.
    """

    name: str
    description: str
    state_schema: dict[str, Any]
    activation_triggers: list[ActivationTrigger]
    prompt_template: str
    tool_scope: ToolScope
    budget_defaults: BudgetDefaults = Field(default_factory=BudgetDefaults)
