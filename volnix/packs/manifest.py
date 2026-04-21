"""Pack manifest schema + compatibility resolver (PMF Plan
Phase 4C Step 13).

Every pack directory may ship a ``pack.yaml`` sidecar declaring
pack-level metadata:

.. code-block:: yaml

    name: my_pack
    version: "1.2.0"
    compatible_with: ">=0.2,<0.3"
    author: "product-team"
    description: "..."
    category: "communication"

The registry validates ``compatible_with`` against the installed
``volnix`` version at pack-register time. A mismatch raises
``IncompatiblePackError`` so upgrades surface cleanly at boot
rather than as mysterious runtime failures.

Packs that do NOT ship a ``pack.yaml`` (pre-0.2.0 bundled packs,
third-party packs that haven't migrated yet) are permitted but
emit a ``DeprecationWarning`` on register — authors have time
to add a manifest before a future major bump enforces
authorship (post-impl audit C2). The permissive policy is
implemented in the registry, not here.

``GRANDFATHERED_COMPAT_SPEC`` is kept as a documented constant
for consumers who want to manually compat-check a no-manifest
pack against the same spec the registry's warning uses.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Final

import yaml
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version
from pydantic import BaseModel, ConfigDict, Field, field_validator

from volnix.core.errors import (
    IncompatiblePackError,
    PackError,
    PackManifestMismatchError,
)

# Grandfather policy reference — pre-0.2.0 packs authored without
# a ``pack.yaml`` are documented as belonging to this range. The
# registry treats missing manifests permissively (deprecation
# warning, not hard fail) regardless of this constant; the
# string is kept as a documented reference for consumers who
# want to audit grandfather-era packs explicitly.
GRANDFATHERED_COMPAT_SPEC: Final[str] = ">=0.1,<0.2"


class _NoAnchorPackLoader(yaml.SafeLoader):
    """YAML SafeLoader subclass that rejects anchors/aliases.

    Post-impl audit H3: mirrors the ``_NoAnchorSafeLoader`` from
    ``volnix.actors.character_loader``. Character catalogs and pack
    manifests face the same alias-amplification risk (billion-
    laughs style DoS); both reject anchors at compose time.
    """

    def compose_node(self, parent, index):  # type: ignore[no-untyped-def]
        if self.check_event(yaml.AliasEvent):
            event = self.peek_event()
            raise yaml.YAMLError(
                f"YAML alias *{event.anchor} rejected in pack.yaml — amplification guard."
            )
        event = self.peek_event()
        if (
            isinstance(
                event,
                (yaml.MappingStartEvent, yaml.SequenceStartEvent, yaml.ScalarEvent),
            )
            and event.anchor is not None
        ):
            raise yaml.YAMLError(
                f"YAML anchor &{event.anchor} rejected in pack.yaml — amplification guard."
            )
        return super().compose_node(parent, index)


# Per-file size cap for pack.yaml (post-impl audit H3). 256 KB is
# generous for any realistic manifest; anything larger is either a
# binary blob or an amplification attack pre-parse.
_MAX_MANIFEST_SIZE_BYTES: Final[int] = 256 * 1024


class PackManifestLoadError(PackError):
    """Raised when a ``pack.yaml`` cannot be read or parsed.
    Kept distinct from ``PackManifestMismatchError`` (manifest
    vs class drift) so consumers can distinguish parse failures
    from declaration-drift failures.
    """

    pass


class PackManifest(BaseModel):
    """Declarative pack metadata sidecar.

    Attributes:
        name: Pack name (matches ``ServicePack.pack_name`` or
            ``ServiceProfile.profile_name``).
        version: PEP-440 version string for the pack itself
            (e.g. ``"1.2.0"``, ``"2.0.0a1"``). Note: the
            validator accepts any PEP-440 string including
            local versions (``+local``); those are technically
            valid but discouraged for published packs (audit L1).
        compatible_with: PEP-440 specifier set the pack requires
            on the installed ``volnix`` version (e.g.
            ``">=0.2,<0.3"``). Validated via
            ``packaging.specifiers.SpecifierSet``. Empty strings
            and accept-all specs are rejected (audit H2).
        author: Free-form author / team string.
        description: One-line pack description.
        category: Semantic category. Must match
            ``ServicePack.category`` at load time (see
            :class:`PackManifestMismatchError`).
        fidelity_tier: Optional pack-declared fidelity tier
            (``1`` = verified, ``2`` = profiled).
            ``check_manifest_matches_pack`` cross-checks this
            against ``ServicePack.fidelity_tier`` when non-zero
            so manifest and class can't drift (audit H4). ``0``
            (the default) skips the check for authors who
            haven't opted in.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: str
    compatible_with: str
    author: str = ""
    description: str = ""
    category: str = ""
    fidelity_tier: int = 0
    extensions: dict[str, Any] = Field(default_factory=dict)
    """Free-form product-scoped metadata — the platform ignores
    this but products can record release-notes URLs, changelog
    pointers, etc."""

    @field_validator("extensions", mode="before")
    @classmethod
    def _deepcopy_extensions(cls, v: Any) -> Any:
        """Step-13 post-impl audit M1: ``frozen=True`` only blocks
        attribute reassignment, not mutation of nested containers.
        Deep-copy the input at construction so mutation of the
        caller's source dict doesn't leak into the frozen model.
        (Consumer-side mutation of the stored dict is a separate
        concern — documented as a known limitation of Pydantic v2
        frozen semantics on container fields.)
        """
        if isinstance(v, dict):
            return copy.deepcopy(v)
        return v

    @field_validator("name")
    @classmethod
    def _non_empty_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("PackManifest.name must be non-empty")
        return v

    @field_validator("version")
    @classmethod
    def _valid_version(cls, v: str) -> str:
        try:
            Version(v)
        except InvalidVersion as exc:
            raise ValueError(
                f"PackManifest.version {v!r} is not a valid PEP-440 version: {exc}"
            ) from exc
        return v

    @field_validator("compatible_with")
    @classmethod
    def _valid_compatible_with(cls, v: str) -> str:
        # Post-impl audit H2: reject empty / whitespace-only specs
        # — ``SpecifierSet("")`` is technically valid and matches
        # every version, which hides author errors behind a silent
        # accept-all gate. Require explicit intent.
        if not v.strip():
            raise ValueError(
                "PackManifest.compatible_with must be a non-empty "
                "PEP-440 specifier (e.g. '>=0.2,<0.3')."
            )
        try:
            spec = SpecifierSet(v)
        except InvalidSpecifier as exc:
            raise ValueError(
                f"PackManifest.compatible_with {v!r} is not a valid PEP-440 specifier set: {exc}"
            ) from exc
        if not list(spec):
            raise ValueError(
                f"PackManifest.compatible_with {v!r} parses as an empty "
                f"specifier set — every volnix version matches. Provide "
                f"an explicit bound."
            )
        return v


def load_manifest(pack_yaml_path: Path) -> PackManifest:
    """Read + validate a ``pack.yaml`` file.

    Raises ``PackManifestLoadError`` on missing file, IO error,
    YAML parse error (including anchor rejection and size-cap
    overflow — post-impl audit H3), or schema-validation failure
    — a single error hierarchy so callers can catch one thing.
    """
    if not pack_yaml_path.exists():
        raise PackManifestLoadError(f"pack.yaml not found at {pack_yaml_path}")
    try:
        size = pack_yaml_path.stat().st_size
    except OSError as exc:
        raise PackManifestLoadError(f"{pack_yaml_path}: stat failed: {exc}") from exc
    if size > _MAX_MANIFEST_SIZE_BYTES:
        raise PackManifestLoadError(
            f"{pack_yaml_path}: {size} bytes exceeds "
            f"{_MAX_MANIFEST_SIZE_BYTES}-byte cap. Amplification guard."
        )
    try:
        with pack_yaml_path.open("r", encoding="utf-8") as fh:
            data: Any = yaml.load(fh, Loader=_NoAnchorPackLoader)
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as exc:
        raise PackManifestLoadError(f"{pack_yaml_path}: {type(exc).__name__}: {exc}") from exc
    if not isinstance(data, dict):
        raise PackManifestLoadError(
            f"{pack_yaml_path}: top-level must be a mapping, got {type(data).__name__}"
        )
    try:
        return PackManifest.model_validate(data)
    except Exception as exc:  # pydantic ValidationError wrapped
        raise PackManifestLoadError(f"{pack_yaml_path}: schema validation failed: {exc}") from exc


def check_compatibility(
    volnix_version: str,
    *,
    compatible_with: str,
    pack_name: str,
) -> None:
    """Validate that ``volnix_version`` satisfies the pack's
    ``compatible_with`` specifier. Raises
    ``IncompatiblePackError`` on mismatch with an actionable
    message — surfaces at register time, not at call time.

    ``pack_name`` is embedded in error messages for actionable
    diagnostics; an empty string defaults to ``<unknown>`` so
    log output stays readable (post-impl audit L3).
    """
    if not pack_name or not pack_name.strip():
        pack_name = "<unknown>"
    try:
        spec = SpecifierSet(compatible_with)
    except InvalidSpecifier as exc:
        # Should be caught earlier by PackManifest validator; this
        # is the last-line defence for consumers passing raw
        # strings directly.
        raise IncompatiblePackError(
            f"pack {pack_name!r}: compatible_with {compatible_with!r} "
            f"is not a valid specifier: {exc}"
        ) from exc
    try:
        version = Version(volnix_version)
    except InvalidVersion as exc:
        raise IncompatiblePackError(
            f"pack {pack_name!r}: cannot parse volnix version {volnix_version!r}: {exc}"
        ) from exc
    if version not in spec:
        raise IncompatiblePackError(
            f"pack {pack_name!r}: compatible_with={compatible_with!r} "
            f"does not include current volnix=={volnix_version}. "
            f"Upgrade the pack or downgrade volnix."
        )


def check_manifest_matches_pack(
    manifest: PackManifest,
    *,
    pack_name: str,
    pack_category: str,
    pack_fidelity_tier: int = 0,
) -> None:
    """Validate that ``pack.yaml`` values agree with the Python
    ``ServicePack`` / ``ServiceProfile`` ClassVars. Raises
    ``PackManifestMismatchError`` on drift.

    Checked fields: ``name``, ``category``, ``fidelity_tier``
    (post-impl audit H4). Fields with ``0`` / ``""`` on the
    manifest side are treated as "author opted out" and skipped —
    authors who want strict agreement set every field on the
    manifest.
    """
    if manifest.name != pack_name:
        raise PackManifestMismatchError(
            f"pack.yaml name {manifest.name!r} does not match pack ClassVar {pack_name!r}"
        )
    if manifest.category and manifest.category != pack_category:
        raise PackManifestMismatchError(
            f"pack.yaml category {manifest.category!r} does not match "
            f"pack ClassVar {pack_category!r}"
        )
    if manifest.fidelity_tier and manifest.fidelity_tier != pack_fidelity_tier:
        raise PackManifestMismatchError(
            f"pack.yaml fidelity_tier {manifest.fidelity_tier!r} does "
            f"not match pack ClassVar {pack_fidelity_tier!r}"
        )


__all__ = [
    "PackManifest",
    "PackManifestLoadError",
    "GRANDFATHERED_COMPAT_SPEC",
    "load_manifest",
    "check_compatibility",
    "check_manifest_matches_pack",
]
