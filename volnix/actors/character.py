"""CharacterDefinition — declarative YAML-loadable actor catalog
entry (PMF Plan Phase 4C Step 11).

Product repos (e.g. Rehearse) ship a directory of ``*.yaml``
character files; ``CharacterLoader.load_directory`` reads them
into a ``dict[str, CharacterDefinition]``. The platform stays
domain-neutral — it doesn't care whether a character is an
interviewer, a skeptic, or a family member; that's the product's
vocabulary inside ``metadata``.

``CharacterDefinition`` maps 1:1 onto the ``actor_specs`` dict
shape already consumed by the world compiler, so a product that
wants catalog characters in its world plan calls
``character.to_actor_spec()`` at plan-build time.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CharacterDefinition(BaseModel):
    """One entry in a character catalog.

    Attributes:
        id: Unique identifier within the catalog directory.
            Matched against ``WorldPlan.characters`` references.
        name: Human-readable display name.
        role: Free-form role label (product vocabulary — "mentor",
            "skeptic", "panelist", etc.).
        persona: Short persona description that downstream prompt
            builders can feed to the LLM (product-side — platform
            doesn't interpret).
        activation_profile: Optional NPC activation profile
            (matches ``ActorDefinition.activation_profile``).
            Default ``None`` = passive.
        metadata: Free-form product-scoped bag. Platform does NOT
            parse; product consumers layer their schema on top.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    name: str = ""
    role: str = ""
    persona: str = ""
    activation_profile: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_actor_spec(self) -> dict[str, Any]:
        """Produce the dict shape the world compiler's
        ``actor_specs`` list expects. Consumers call this at plan-
        build time to dereference a ``WorldPlan.characters``
        reference into an actor spec.
        """
        spec: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "persona": self.persona,
        }
        if self.activation_profile is not None:
            spec["activation_profile"] = self.activation_profile
        if self.metadata:
            spec["metadata"] = dict(self.metadata)
        return spec
