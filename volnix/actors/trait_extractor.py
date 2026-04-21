"""Deterministic trait extraction from ActorDefinition to ActorBehaviorTraits.

No LLM calls. Maps friction_profile, permissions, personality, and metadata
into normalized numeric traits used for tier classification routing.

PMF Plan Phase 4C Step 12: the bundled ``extract_behavior_traits``
is the DEFAULT extractor. Products can override via
``VolnixConfig.trait_extractor_hook = "mypackage.module:my_fn"``
— the composition root resolves the hook via
:func:`resolve_extractor_hook` at engine-wiring time.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING

from volnix.actors.behavioral_signature import BehavioralSignature
from volnix.actors.state import ActorBehaviorTraits
from volnix.core.errors import VolnixError

if TYPE_CHECKING:
    from volnix.actors.definition import ActorDefinition


# Callable signature for a trait extractor. Defining the alias
# here (rather than inline in consumer code) means a hook provider
# can import it for type-hinting their own implementation.
TraitExtractor = Callable[["ActorDefinition"], BehavioralSignature]


class TraitExtractorHookError(VolnixError):
    """Raised when a ``trait_extractor_hook`` config string cannot
    be resolved to a callable. Surfaces AT RESOLVE TIME so the
    misconfiguration fails at boot rather than silently falling
    back to the default (post-impl audit-fold — products that
    set a hook expect it to be honored).

    Subclass of ``VolnixError`` per the error-hierarchy lock.
    """


def resolve_extractor_hook(hook: str | None) -> TraitExtractor:
    """Resolve a dotted-path hook string to the underlying
    callable. ``None`` returns the bundled default.

    Format: ``"package.module:callable_name"`` (Python entry-point
    convention — colon separator between module path and attribute).

    Raises:
        TraitExtractorHookError: on missing colon, invalid module,
            missing attribute, or non-callable resolved target.
    """
    if hook is None or not hook.strip():
        return extract_behavior_traits
    raw = hook.strip()
    if ":" not in raw:
        raise TraitExtractorHookError(
            f"trait_extractor_hook {raw!r}: expected "
            f"'package.module:callable_name' (colon separator)."
        )
    module_path, _, attr = raw.partition(":")
    if not module_path or not attr:
        raise TraitExtractorHookError(
            f"trait_extractor_hook {raw!r}: module path and callable name must both be non-empty."
        )
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise TraitExtractorHookError(
            f"trait_extractor_hook {raw!r}: import failed: {exc}"
        ) from exc
    try:
        resolved = getattr(module, attr)
    except AttributeError as exc:
        raise TraitExtractorHookError(
            f"trait_extractor_hook {raw!r}: module {module_path!r} has no attribute {attr!r}"
        ) from exc
    if not callable(resolved):
        raise TraitExtractorHookError(
            f"trait_extractor_hook {raw!r}: resolved target is not "
            f"callable (got {type(resolved).__name__})."
        )
    return resolved


# Friction category -> cooperation / deception mappings
_FRICTION_COOPERATION: dict[str, float] = {
    "uncooperative": 0.3,
    "deceptive": 0.2,
    "hostile": 0.1,
}

_FRICTION_DECEPTION: dict[str, float] = {
    "uncooperative": 0.1,
    "deceptive": 0.7,
    "hostile": 0.4,
}


def extract_behavior_traits(actor_def: ActorDefinition) -> ActorBehaviorTraits:
    """Extract normalized traits from ActorDefinition. Deterministic, no LLM.

    Mapping rules:
    - friction_profile.category -> cooperation_level, deception_risk
    - friction_profile.intensity -> scales cooperation/deception
    - permissions (write: all) -> authority_level
    - personality_hint keywords -> ambient_activity_rate, stakes_level
    - metadata.stakes -> stakes_level override

    Args:
        actor_def: The frozen actor definition from the world compiler.

    Returns:
        An ActorBehaviorTraits with normalized float fields (0.0-1.0).
    """
    cooperation = 0.5
    deception = 0.0
    authority = 0.0
    stakes = 0.3
    ambient_activity = 0.1

    # -- Friction profile -> cooperation & deception --
    fp = actor_def.friction_profile
    if fp is not None:
        category = fp.category
        cooperation = _FRICTION_COOPERATION.get(category, 0.5)
        deception = _FRICTION_DECEPTION.get(category, 0.0)

        # Intensity (0-100) scales the effect
        intensity_factor = fp.intensity / 100.0
        cooperation = max(0.0, cooperation - (intensity_factor * 0.2))
        deception = min(1.0, deception + (intensity_factor * 0.2))

    # -- Permissions -> authority --
    perms = actor_def.permissions
    if perms:
        if perms.get("write") == "all" and perms.get("read") == "all":
            authority = 0.9
        elif perms.get("write") == "all":
            authority = 0.7
        elif perms.get("read") == "all":
            authority = 0.4
        elif perms.get("write"):
            authority = 0.3

    # -- Personality -> ambient activity --
    personality = actor_def.personality
    if personality is not None:
        traits = personality.traits or {}
        if traits.get("proactive") or traits.get("initiative"):
            ambient_activity = 0.5
        if traits.get("passive") or traits.get("reactive_only"):
            ambient_activity = 0.05

        # Style hints
        if personality.style in ("aggressive", "demanding"):
            ambient_activity = max(ambient_activity, 0.4)
            cooperation = max(0.0, cooperation - 0.1)
        elif personality.style in ("passive", "accommodating"):
            ambient_activity = min(ambient_activity, 0.1)
            cooperation = min(1.0, cooperation + 0.1)

    # -- Role-based authority heuristic (domain-agnostic) --
    _authority_roles = {
        "supervisor",
        "manager",
        "admin",
        "moderator",
        "lead",
        "director",
    }
    role_lower = actor_def.role.lower()
    for _auth_role in _authority_roles:
        if _auth_role in role_lower:
            authority = max(authority, 0.7)
            stakes = max(stakes, 0.6)
            break

    # -- personality_hint keywords --
    hint = actor_def.personality_hint.lower()
    if hint:
        if any(w in hint for w in ("proactive", "active", "busy", "aggressive")):
            ambient_activity = max(ambient_activity, 0.4)
        if any(w in hint for w in ("passive", "quiet", "patient", "laid-back")):
            ambient_activity = min(ambient_activity, 0.1)
        if any(w in hint for w in ("critical", "urgent", "high-stakes", "important")):
            stakes = max(stakes, 0.7)
        if any(w in hint for w in ("manager", "director", "executive", "authority")):
            authority = max(authority, 0.6)

        # Authority indicators in personality_hint
        _authority_hints = {"approve", "review", "escalat", "authoriz", "decision"}
        for _kw in _authority_hints:
            if _kw in hint:
                authority = max(authority, 0.6)
                break

    # -- Metadata overrides --
    meta = actor_def.metadata
    if meta.get("stakes"):
        try:
            stakes = float(meta["stakes"])
        except (ValueError, TypeError):
            pass
    if meta.get("authority_level"):
        try:
            authority = float(meta["authority_level"])
        except (ValueError, TypeError):
            pass

    # Platform internals construct ``BehavioralSignature`` directly
    # (the ``ActorBehaviorTraits`` alias is kept for external
    # backwards-compat and fires a DeprecationWarning on use).
    return BehavioralSignature(
        cooperation_level=_clamp(cooperation),
        deception_risk=_clamp(deception),
        authority_level=_clamp(authority),
        stakes_level=_clamp(stakes),
        ambient_activity_rate=_clamp(ambient_activity),
    )


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp a value to [lo, hi]."""
    return max(lo, min(hi, value))
