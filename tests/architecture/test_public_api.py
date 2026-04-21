"""Phase 4C Step 1 — locks the public API surface exported from
``volnix.__init__.__all__``.

Every string in ``_EXPECTED_PUBLIC_API`` below is a semver commitment:
removal requires a deprecation cycle. Additions are easy (bump the
list), removals are hard (break consumer pins).

Per DESIGN_PRINCIPLES.md §Test Discipline: this is a defensive contract
test — the assertion fires loudly on accidental re-export from the
public module.

The list is DELIBERATELY a subset of the 4C end-state. Later steps
extend both this set and ``__all__`` in lockstep; see
``volnix.__doc__`` for the canonical roadmap of reserved exports.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import sys

import pytest

import volnix

# IMPORTANT: this list is the ground truth for Step 1 ship. Update it
# with care — every name here is a promise to downstream consumers.
_EXPECTED_PUBLIC_API: frozenset[str] = frozenset(
    {
        "__version__",
        # Entry points
        "VolnixApp",
        "VolnixConfig",
        "ConfigBuilder",
        "PackSearchPath",
        # Core value objects
        "ActionEnvelope",
        "WorldEvent",
        "MemoryRecord",
        "MemoryQuery",
        "MemoryRecall",
        "MemoryScope",
        "MemoryWrite",
        "Session",
        "SessionEndedEvent",
        "SessionId",
        "SessionPausedEvent",
        "SessionResumedEvent",
        "SessionStartedEvent",
        "SessionStatus",
        "SessionType",
        "SessionManager",
        "SlotAssignment",
        "ActorId",
        "ActorType",
        "EntityId",
        "EventId",
        "MemoryRecordId",
        "RunId",
        "ServiceId",
        "SnapshotId",
        "Timestamp",
        "ToolName",
        "WorldId",
        # Actors
        "ActorDefinition",
        "ActorState",
        # Packs
        "ServicePack",
        "ServiceProfile",
        "PackRegistry",
        "PackManifest",
        # Protocols
        "MemoryEngineProtocol",
        "NPCActivatorProtocol",
        "PermissionEngineProtocol",
        # Ledger
        "LedgerEntry",
        "LedgerQuery",
        "UnknownLedgerEntry",
        # Simulation
        "SimulationRunner",
        "SimulationRunnerConfig",
        "SimulationType",
        "StopReason",
        # Character catalog (Step 11)
        "CharacterDefinition",
        "CharacterLoader",
        "CharacterCatalogError",
        # Behavioral signature (Step 12)
        "BehavioralSignature",
        "ActorBehaviorTraits",
        "TraitExtractorHookError",
        "resolve_extractor_hook",
        # Privacy (Step 14)
        "PrivacyConfig",
        "LedgerRedactorError",
        "identity_redactor",
        "resolve_ledger_redactor",
        # State trajectory (Step 9)
        "TrajectoryPoint",
        # Observation (Step 10)
        "ObservationQuery",
        "UnifiedTimeline",
        "TimelineEvent",
        "TimelineSource",
        "IntentBehaviorGap",
        "PersonaContribution",
        "VariantDeltaReport",
        "intent_behavior_gap",
        "load_bearing_personas",
        "variant_delta",
        # Errors
        "VolnixError",
        "DuplicatePackError",
        "IncompatiblePackError",
        "PackManifestLoadError",
        "PackManifestMismatchError",
        "PackNotFoundError",
        "ReplayJournalMismatch",
        "ReplayProviderNotFound",
        "SessionNotFoundError",
        "TrajectoryFieldNotFound",
    }
)


# Source-fallback sentinel — must match the literal in
# ``volnix/__init__.py`` so the fallback behavioural test can assert
# without the source-grep weakness.
_SOURCE_FALLBACK_SENTINEL: str = "0.0.0+source"


# ─── __all__ surface lock ─────────────────────────────────────────────


def test_negative_public_api_all_matches_expected() -> None:
    """``__all__`` must exactly equal the frozen expected set — adding
    a name silently is as bad as removing one (consumers can't rely on
    what they can't see; maintainers can't delete what they didn't
    declare)."""
    actual = frozenset(volnix.__all__)
    missing = _EXPECTED_PUBLIC_API - actual
    extra = actual - _EXPECTED_PUBLIC_API
    assert not missing, f"Public API names missing from __all__: {sorted(missing)}"
    assert not extra, (
        f"Unexpected names in __all__ (add to _EXPECTED_PUBLIC_API or "
        f"remove the export): {sorted(extra)}"
    )


def test_negative_every_expected_name_importable_from_volnix_root() -> None:
    """Every name in ``__all__`` must actually be importable from the
    root package — catches stale imports (e.g. a refactor removed the
    symbol but left the export)."""
    for name in _EXPECTED_PUBLIC_API:
        assert hasattr(volnix, name), f"volnix.{name} declared in __all__ but not importable"


# ─── Version lock ─────────────────────────────────────────────────────


def test_positive_version_sourced_from_package_metadata() -> None:
    """``__version__`` comes from ``importlib.metadata``, not a literal
    string that can drift from ``pyproject.toml``. Also asserts the
    version is a non-empty string and NOT the source-fallback sentinel
    (catches a broken build that emits empty metadata)."""
    try:
        expected = importlib.metadata.version("volnix")
    except importlib.metadata.PackageNotFoundError:
        pytest.skip("Package not installed (running from source tree)")
    assert volnix.__version__ == expected
    assert volnix.__version__, "installed version must be non-empty"
    assert volnix.__version__ != _SOURCE_FALLBACK_SENTINEL, (
        f"installed package resolved to the source-tree fallback "
        f"{_SOURCE_FALLBACK_SENTINEL!r} — package-metadata lookup is broken"
    )


def test_negative_fallback_string_literal_exists_in_init(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Documentation-level guard: the fallback literal appears in the
    init source. Catches a refactor that eliminates the fallback
    branch entirely. Complementary to the behavioural test below."""
    import pathlib

    init_source = (volnix.__file__ or "").replace(".pyc", ".py")
    src = pathlib.Path(init_source).read_text(encoding="utf-8")
    assert _SOURCE_FALLBACK_SENTINEL in src, (
        f"Missing the unpackaged-source version fallback {_SOURCE_FALLBACK_SENTINEL!r}"
    )


def test_negative_fallback_fires_when_metadata_lookup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Behavioural guard (addresses M1 from Step-1 principal-engineer
    review). Simulate the unpackaged-source-tree scenario: force
    ``importlib.metadata.version("volnix")`` to raise
    ``PackageNotFoundError`` and verify the re-executed init-module
    branch yields ``_SOURCE_FALLBACK_SENTINEL``. Without this, a
    refactor that accidentally eats the fallback (e.g. narrow except
    clause, wrong exception type) would pass the source-grep test
    while silently losing the guarantee."""
    real_version = importlib.metadata.version

    def _force_not_found(package_name: str) -> str:
        if package_name == "volnix":
            raise importlib.metadata.PackageNotFoundError(package_name)
        return real_version(package_name)

    monkeypatch.setattr(importlib.metadata, "version", _force_not_found)

    # Reload the module under the monkeypatched metadata surface so the
    # top-level try/except runs fresh against the forced exception.
    sys.modules.pop("volnix", None)
    try:
        reloaded = importlib.import_module("volnix")
        assert reloaded.__version__ == _SOURCE_FALLBACK_SENTINEL, (
            f"Fallback did not fire: got {reloaded.__version__!r}, "
            f"expected {_SOURCE_FALLBACK_SENTINEL!r}"
        )
    finally:
        # Restore a clean volnix module so downstream tests see the
        # real (installed or source) version, not our forced fallback.
        sys.modules.pop("volnix", None)
        importlib.import_module("volnix")


# ─── Error-hierarchy lock (audit-fold D-Find-8) ───────────────────────


def _exported_exception_names() -> list[str]:
    """Derive the set of exception names dynamically from the actual
    public-API surface — not a separately-maintained hand list. M2 of
    the Step-1 principal-engineer review called this out: two lists
    drift; one list derived from the other does not."""
    names: list[str] = []
    for name in _EXPECTED_PUBLIC_API:
        obj = getattr(volnix, name, None)
        if isinstance(obj, type) and issubclass(obj, BaseException):
            names.append(name)
    return names


def test_negative_every_exported_error_inherits_volnix_error() -> None:
    """Locked hierarchy: every exported exception is a ``VolnixError``
    subclass. Prevents silent drift where a new 4C exception slips
    past consumers doing ``except VolnixError:``. The check is
    exhaustive over the actual exported set (no separate hand-list
    to forget to update)."""
    root = volnix.VolnixError
    error_names = _exported_exception_names()
    # Sanity: the root itself is one of the exceptions we iterate, but
    # every non-root exception must inherit from it.
    non_root = [n for n in error_names if n != "VolnixError"]
    assert non_root, (
        "Expected at least one exported error class besides VolnixError; "
        "is the error-hierarchy discipline actually being enforced?"
    )
    for name in non_root:
        cls = getattr(volnix, name)
        assert issubclass(cls, root), (
            f"{name!r} does not inherit from VolnixError — consumers "
            f"catching VolnixError will miss it"
        )


def test_positive_volnix_error_is_root_exception() -> None:
    """The root itself must be exported and be a proper Exception
    subclass — otherwise consumers can't reference the hierarchy
    root."""
    assert volnix.VolnixError is not None
    assert isinstance(volnix.VolnixError, type)
    assert issubclass(volnix.VolnixError, Exception)
