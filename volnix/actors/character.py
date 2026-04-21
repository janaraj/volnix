"""CharacterDefinition — declarative YAML-loadable actor catalog
entry (PMF Plan Phase 4C Step 11).

Product repos (e.g. Rehearse) ship a directory of ``*.yaml``
character files; ``CharacterLoader.load_directory`` reads them
into a ``dict[str, CharacterDefinition]``. The platform stays
domain-neutral — it doesn't care whether a character is an
interviewer, a skeptic, or a family member; that's the product's
vocabulary inside ``metadata``.

``CharacterDefinition.to_actor_spec()`` produces the dict shape
consumed by ``SimpleActorGenerator.generate_batch`` — emits
``personality`` (the key the generator reads), NOT ``persona``
(post-impl audit C1).
"""

from __future__ import annotations

import copy
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Post-impl audit H6: id validation. Length cap at 256 chars
# covers any realistic human-readable identifier and guards
# cache-by-id structures from unbounded growth. Allowed charset
# is the union of printable ASCII minus path separators and
# filesystem meta-characters; product repos can still use Unicode
# display names via ``CharacterDefinition.name`` without
# compromising the id.
_MAX_ID_LENGTH: int = 256
_ID_FORBIDDEN_RE: re.Pattern[str] = re.compile(r"[\s/\\\x00-\x1f\x7f]")


class CharacterDefinition(BaseModel):
    """One entry in a character catalog.

    Attributes:
        id: Unique identifier within the catalog directory.
            Matched against ``WorldPlan.characters`` references.
            Validated: non-empty, ≤256 chars, no whitespace /
            path separators / control characters, no ``..``
            segments (post-impl audit H6).
        name: Human-readable display name (Unicode OK).
        role: Free-form role label (product vocabulary — "mentor",
            "skeptic", "panelist", etc.).
        persona: Short persona description that downstream prompt
            builders can feed to the LLM (product-side — platform
            doesn't interpret). Emitted as ``personality`` on
            ``to_actor_spec()`` — that's the key
            ``SimpleActorGenerator`` reads.
        activation_profile: Optional NPC activation profile
            (matches ``ActorDefinition.activation_profile``).
            Default ``None`` = passive.
        metadata: Free-form product-scoped bag. Platform does NOT
            parse; product consumers layer their schema on top.
    """

    # Post-impl audit M2: reject unknown fields at the YAML author
    # boundary — a typo like ``nmae: Alice`` would silently swallow
    # under ``extra="ignore"`` and produce a nameless character.
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str = ""
    role: str = ""
    persona: str = ""
    activation_profile: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata", mode="before")
    @classmethod
    def _deepcopy_metadata(cls, v: Any) -> Any:
        """Step-11 cleanup sweep: deep-copy at construction so
        caller-side mutation of the source dict can't leak into
        the frozen model. Complements the ``to_actor_spec()``
        deep-copy which already protects the emitted dict."""
        if isinstance(v, dict):
            return copy.deepcopy(v)
        return v

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        """Post-impl audit H6: reject ids that would corrupt
        downstream filesystem paths, log scanning, or cache keys.
        """
        if not isinstance(v, str) or not v.strip():
            raise ValueError("CharacterDefinition.id must be a non-empty string")
        if len(v) > _MAX_ID_LENGTH:
            raise ValueError(
                f"CharacterDefinition.id length {len(v)} exceeds cap "
                f"{_MAX_ID_LENGTH} — catalog consumers cache by id "
                f"and unbounded length is a memory cliff."
            )
        if _ID_FORBIDDEN_RE.search(v):
            raise ValueError(
                f"CharacterDefinition.id {v!r} contains whitespace, "
                f"path separator, or control character. Character "
                f"ids must be a single token with no filesystem-meta "
                f"characters."
            )
        # Path-traversal guard — ``..`` as a path segment OR as a
        # prefix is rejected. ``foo..bar`` is fine (one token).
        if v == ".." or v.startswith("../") or "/.." in v:
            raise ValueError(
                f"CharacterDefinition.id {v!r} contains path-traversal "
                f"sequence. Use a simple identifier."
            )
        return v

    def to_actor_spec(self) -> dict[str, Any]:
        """Produce the dict shape consumed by
        ``SimpleActorGenerator.generate_batch``.

        Emits ``personality`` (the key
        ``SimpleActorGenerator`` reads at line 85 of
        ``simple_generator.py``) carrying the ``persona`` value.
        Also threads ``activation_profile`` as a first-class key
        so ``SimpleActorGenerator`` can wire it through to
        ``ActorDefinition.activation_profile`` (the generator's
        known-keys list gains this field in the same cleanup).

        Post-impl audit H2: ``metadata`` is ``deepcopy``-ed so
        downstream mutation of the emitted dict (including nested
        dicts) cannot alias back into the frozen
        ``CharacterDefinition``.
        """
        spec: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            # Post-impl audit C1: emit under ``personality`` (what
            # SimpleActorGenerator reads). Keeping the source field
            # named ``persona`` for authoring clarity — the mapping
            # happens here at the boundary.
            "personality": self.persona,
        }
        if self.activation_profile is not None:
            spec["activation_profile"] = self.activation_profile
        if self.metadata:
            spec["metadata"] = copy.deepcopy(self.metadata)
        return spec
