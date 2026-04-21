"""Phase 4C Step 12 — BehavioralSignature + extractor hook tests.

Locks:
- Schema: 5 core axes bounded [0, 1], extensions bag of validated
  floats, frozen model.
- ``ActorBehaviorTraits`` alias preserves pre-Step-12 constructor
  calls byte-identical.
- ``resolve_extractor_hook`` returns the default when ``None``,
  resolves a valid dotted path, raises on every malformed input
  variant (missing colon, bad module, missing attr, non-callable).
- Extensions value validation rejects non-float, bool, out-of-range.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from volnix.actors.behavioral_signature import (
    ActorBehaviorTraits,
    BehavioralSignature,
)
from volnix.actors.trait_extractor import (
    TraitExtractorHookError,
    extract_behavior_traits,
    resolve_extractor_hook,
)

# ─── BehavioralSignature schema ────────────────────────────────────


def test_positive_default_signature_has_all_five_core_axes() -> None:
    sig = BehavioralSignature()
    assert sig.cooperation_level == 0.5
    assert sig.deception_risk == 0.0
    assert sig.authority_level == 0.0
    assert sig.stakes_level == 0.3
    assert sig.ambient_activity_rate == 0.1
    assert sig.extensions == {}


def test_positive_signature_is_frozen() -> None:
    sig = BehavioralSignature()
    with pytest.raises(Exception):
        sig.cooperation_level = 0.9  # type: ignore[misc]


def test_negative_core_axis_above_1_rejected() -> None:
    with pytest.raises(ValidationError):
        BehavioralSignature(cooperation_level=1.5)


def test_negative_core_axis_below_0_rejected() -> None:
    with pytest.raises(ValidationError):
        BehavioralSignature(deception_risk=-0.1)


# ─── Extensions bag validation ─────────────────────────────────────


class TestExtensions:
    def test_positive_extensions_accept_float_values(self) -> None:
        sig = BehavioralSignature(extensions={"custom_axis": 0.42})
        assert sig.extensions == {"custom_axis": 0.42}

    def test_positive_int_coerced_to_float(self) -> None:
        sig = BehavioralSignature(extensions={"axis": 1})
        assert sig.extensions == {"axis": 1.0}
        assert isinstance(sig.extensions["axis"], float)

    def test_negative_bool_value_rejected(self) -> None:
        """``True`` is a subclass of ``int`` in Python; the
        validator explicitly rejects so a typo ``{"flag": True}``
        doesn't coerce to 1.0."""
        with pytest.raises(ValidationError):
            BehavioralSignature(extensions={"flag": True})

    def test_negative_string_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BehavioralSignature(extensions={"axis": "high"})  # type: ignore[dict-item]

    def test_negative_none_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BehavioralSignature(extensions={"axis": None})  # type: ignore[dict-item]

    def test_negative_value_above_1_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BehavioralSignature(extensions={"axis": 1.5})

    def test_negative_value_below_0_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BehavioralSignature(extensions={"axis": -0.1})

    def test_negative_empty_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BehavioralSignature(extensions={"": 0.5})

    def test_negative_non_dict_extensions_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BehavioralSignature(extensions=[("k", 0.5)])  # type: ignore[arg-type]


# ─── Alias compatibility ──────────────────────────────────────────


class TestActorBehaviorTraitsAlias:
    def test_positive_alias_is_same_class(self) -> None:
        """The alias is a plain binding so
        ``isinstance(extractor_output, ActorBehaviorTraits)`` keeps
        working — every pre-Step-12 identity check survives."""
        assert ActorBehaviorTraits is BehavioralSignature

    def test_positive_preserved_constructor_signature(self) -> None:
        """Pre-Step-12 callers used all five core axes only —
        must keep working without passing ``extensions``."""
        t = ActorBehaviorTraits(
            cooperation_level=0.8,
            deception_risk=0.1,
            authority_level=0.5,
            stakes_level=0.7,
            ambient_activity_rate=0.3,
        )
        assert t.cooperation_level == 0.8
        assert t.extensions == {}

    def test_positive_alias_isinstance_check_works(self) -> None:
        """Plain-alias identity means ``isinstance`` on extractor
        output keeps working — the pre-Step-12 identity check
        compatibility that the subclass variant would break."""
        from volnix.actors.definition import ActorDefinition
        from volnix.actors.trait_extractor import extract_behavior_traits
        from volnix.core.types import ActorId, ActorType

        actor = ActorDefinition(id=ActorId("alice"), type=ActorType.HUMAN, role="x")
        traits = extract_behavior_traits(actor)
        assert isinstance(traits, ActorBehaviorTraits)


# ─── Hook resolution ──────────────────────────────────────────────


class TestResolveExtractorHook:
    def test_positive_none_returns_default(self) -> None:
        resolved = resolve_extractor_hook(None)
        assert resolved is extract_behavior_traits

    def test_positive_empty_string_returns_default(self) -> None:
        resolved = resolve_extractor_hook("")
        assert resolved is extract_behavior_traits

    def test_positive_whitespace_string_returns_default(self) -> None:
        resolved = resolve_extractor_hook("   ")
        assert resolved is extract_behavior_traits

    def test_positive_valid_path_resolves(self) -> None:
        """Resolving the bundled default via its dotted path must
        return the same callable the ``None`` shortcut returns."""
        resolved = resolve_extractor_hook("volnix.actors.trait_extractor:extract_behavior_traits")
        assert resolved is extract_behavior_traits

    def test_negative_missing_colon_raises(self) -> None:
        with pytest.raises(TraitExtractorHookError, match="colon"):
            resolve_extractor_hook("volnix.actors.trait_extractor.extract_behavior_traits")

    def test_negative_empty_module_raises(self) -> None:
        with pytest.raises(TraitExtractorHookError):
            resolve_extractor_hook(":some_fn")

    def test_negative_empty_callable_raises(self) -> None:
        with pytest.raises(TraitExtractorHookError):
            resolve_extractor_hook("volnix.actors.trait_extractor:")

    def test_negative_bad_module_raises(self) -> None:
        with pytest.raises(TraitExtractorHookError, match="import failed"):
            resolve_extractor_hook("nonexistent.module:fn")

    def test_negative_missing_attribute_raises(self) -> None:
        with pytest.raises(TraitExtractorHookError, match="no attribute"):
            resolve_extractor_hook("volnix.actors.trait_extractor:does_not_exist")

    def test_negative_non_callable_raises(self) -> None:
        """Resolving to a non-callable (a module-level float
        constant) must fail loudly at resolve time, not silently
        at extract time."""
        with pytest.raises(TraitExtractorHookError, match="not"):
            # ``_AXIS_MIN`` is a float constant, definitely not callable.
            resolve_extractor_hook("volnix.actors.behavioral_signature:_AXIS_MIN")


# ─── Integration: default extractor still works ──────────────────


def test_positive_default_extractor_returns_signature() -> None:
    """The default extractor must continue to return a
    ``BehavioralSignature`` (via the alias) so existing callers
    are byte-identical."""
    from volnix.actors.definition import ActorDefinition
    from volnix.core.types import ActorId, ActorType

    actor = ActorDefinition(id=ActorId("alice"), type=ActorType.HUMAN, role="mentor")
    traits = extract_behavior_traits(actor)
    assert isinstance(traits, BehavioralSignature)
    assert 0.0 <= traits.cooperation_level <= 1.0


# ─── Config field ─────────────────────────────────────────────────


def test_positive_config_trait_extractor_hook_default_is_none() -> None:
    from volnix.config.schema import VolnixConfig

    cfg = VolnixConfig()
    assert cfg.trait_extractor_hook is None


def test_positive_config_accepts_hook_string() -> None:
    from volnix.config.schema import VolnixConfig

    cfg = VolnixConfig(trait_extractor_hook="some.module:fn")
    assert cfg.trait_extractor_hook == "some.module:fn"


def test_positive_config_builder_trait_extractor_hook_method() -> None:
    """``ConfigBuilder.trait_extractor_hook(...)`` threads the
    value into the built config."""
    from volnix.config.builder import ConfigBuilder

    cfg = ConfigBuilder().trait_extractor_hook("mypkg.mod:my_fn").build()
    assert cfg.trait_extractor_hook == "mypkg.mod:my_fn"


def test_positive_config_builder_hook_none_clears_override() -> None:
    from volnix.config.builder import ConfigBuilder

    cfg = ConfigBuilder().trait_extractor_hook(None).build()
    assert cfg.trait_extractor_hook is None
