"""BehavioralSignature — first-class schema for actor behavioral
axes (PMF Plan Phase 4C Step 12).

A ``BehavioralSignature`` is the deterministic, numeric-only
characterization of an actor's behavior. Five core axes ship on
the platform; products layer additional axes via the
``extensions: dict[str, float]`` bag — no core schema change
required for vertical-specific vocabulary.

Why a bag and not a generic / typed-union: product vocabularies
evolve frequently (a downstream vertical might add
``emotional_volatility``; a negotiation harness might add
``batna_strength``). A strict typed union forces a Volnix minor
release per new axis. A plain ``extra="allow"`` would silently
accept typo'd axis names. A numeric dict bag gives validated
float values with product-scoped keys — caller-supplied semantics
without core churn.

``ActorBehaviorTraits`` is kept as a type alias to
``BehavioralSignature`` during the 0.2.x transition; it is
removed in 0.3.0. Consumers constructing via
``ActorBehaviorTraits(...)`` keep working without change.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Core axis bounds. Values outside [0.0, 1.0] are a caller bug,
# not a legitimate product extension — extensions that want
# wider ranges should rescale into [0, 1].
_AXIS_MIN: float = 0.0
_AXIS_MAX: float = 1.0


class BehavioralSignature(BaseModel):
    """Normalized behavioral signature for an actor.

    Attributes:
        cooperation_level: 0.0 = hostile, 1.0 = fully cooperative.
        deception_risk: 0.0 = honest, 1.0 = highly deceptive.
        authority_level: 0.0 = no authority, 1.0 = full authority.
        stakes_level: 0.0 = trivial, 1.0 = critical.
        ambient_activity_rate: 0.0 = never initiates, 1.0 = constantly active.
        extensions: Product-scoped axis bag. Keys are opaque to
            the platform; values must be floats in [0.0, 1.0].

            Validator rejects (Step 12 audit M2):
            - Non-float values: strings, ``None``, objects.
            - Bool values: ``True`` / ``False`` — they're technically
              int subclasses in Python but a typo like
              ``{"flag": True}`` coercing to 1.0 would silently
              corrupt numeric axes, so we reject explicitly.
            - Out-of-range: values outside ``[0.0, 1.0]``.
            - Empty keys / non-string keys.

            Integers ARE accepted and normalized to float at
            construction (``{"axis": 1}`` → stored as ``1.0``).
            This means serialization round-trip via
            ``model_dump(mode="python")`` returns ``{"axis": 1.0}``
            — consumers computing hashes over the source dict vs
            the stored dict see different representations. Use
            ``model_dump(mode="json")`` for a stable wire shape.
    """

    model_config = ConfigDict(frozen=True)

    cooperation_level: float = Field(default=0.5, ge=_AXIS_MIN, le=_AXIS_MAX)
    deception_risk: float = Field(default=0.0, ge=_AXIS_MIN, le=_AXIS_MAX)
    authority_level: float = Field(default=0.0, ge=_AXIS_MIN, le=_AXIS_MAX)
    stakes_level: float = Field(default=0.3, ge=_AXIS_MIN, le=_AXIS_MAX)
    ambient_activity_rate: float = Field(default=0.1, ge=_AXIS_MIN, le=_AXIS_MAX)
    extensions: dict[str, float] = Field(default_factory=dict)

    @field_validator("extensions", mode="before")
    @classmethod
    def _validate_extensions(cls, v: Any) -> dict[str, float]:
        """Enforce: keys are strings, values are floats in [0, 1].
        Reject None, strings, and out-of-range values loudly at
        construction so product axis typos don't lurk as runtime
        surprises.
        """
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError(
                f"BehavioralSignature.extensions must be a dict, got {type(v).__name__}"
            )
        out: dict[str, float] = {}
        for k, raw in v.items():
            if not isinstance(k, str) or not k:
                raise ValueError(
                    f"BehavioralSignature.extensions keys must be non-empty strings; got {k!r}"
                )
            # bool is a subclass of int in Python — reject explicitly
            # so an accidental ``{"flag": True}`` doesn't coerce to 1.0.
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError(
                    f"BehavioralSignature.extensions[{k!r}] must be a "
                    f"float; got {type(raw).__name__}"
                )
            value = float(raw)
            if not (_AXIS_MIN <= value <= _AXIS_MAX):
                raise ValueError(
                    f"BehavioralSignature.extensions[{k!r}] = {value} "
                    f"must be in [{_AXIS_MIN}, {_AXIS_MAX}]"
                )
            out[k] = value
        return out


# Backwards-compatible plain alias. Removed in volnix 0.3.0.
#
# Kept as a simple binding (NOT a subclass) so
# ``isinstance(extractor_output, ActorBehaviorTraits)`` continues
# to work — every pre-Step-12 consumer's identity check survives
# the 0.2.x migration window. ``is`` identity holds:
# ``ActorBehaviorTraits is BehavioralSignature``.
#
# Deprecation is documented, not runtime-signalled. A
# ``DeprecationWarning`` at every internal import site (state.py,
# trait_extractor.py, volnix/__init__.py, test modules) produces
# too much noise for an alias that 0.2.x explicitly supports.
# Post-impl audit H2: CHANGELOG/release notes for 0.2.0 and
# 0.3.0-pre must call out the rename; a future minor release
# (0.2.9) MAY add a runtime warning if consumer migration lags.
ActorBehaviorTraits = BehavioralSignature


__all__ = ["BehavioralSignature", "ActorBehaviorTraits"]
