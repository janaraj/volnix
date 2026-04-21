"""Pack registry -- central index for all registered service packs and profiles.

Maintains three indices built from pack ABC methods:
- by pack_name: direct pack lookup
- by tool_name: reverse lookup (any tool -> its owning pack)
- by category: category -> [packs]

Contains ZERO pack-specific logic. All indexing derived from ServicePack ABC.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from volnix.core.errors import DuplicatePackError, PackNotFoundError
from volnix.packs.base import ServicePack, ServiceProfile
from volnix.packs.loader import discover_packs, discover_profiles
from volnix.packs.manifest import (
    GRANDFATHERED_COMPAT_SPEC,
    PackManifest,
    check_compatibility,
    check_manifest_matches_pack,
    load_manifest,
)

logger = logging.getLogger(__name__)


class PackRegistry:
    """Central registry for packs and profiles with multi-key lookup."""

    def __init__(self) -> None:
        self._packs: dict[str, ServicePack] = {}
        self._tool_index: dict[str, str] = {}  # tool_name -> pack_name
        self._category_index: dict[str, list[str]] = {}  # category -> [pack_name]
        self._profiles: dict[str, ServiceProfile] = {}
        self._profile_pack_index: dict[str, list[str]] = {}  # pack_name -> [profile_name]
        # PMF Plan Phase 4C Step 13 — per-pack manifest lookup.
        # Populated only when ``register(pack, manifest=...)`` is
        # called with an explicit manifest; discovery with a
        # ``pack.yaml`` sidecar populates it; bundled / pre-0.2
        # packs without a manifest are grandfathered and absent
        # from this dict.
        self._manifests: dict[str, PackManifest] = {}

    def register(
        self,
        pack: ServicePack,
        *,
        manifest: PackManifest | None = None,
    ) -> None:
        """Register a pack. Builds all indices from pack's ABC methods.

        ``manifest`` (PMF Plan Phase 4C Step 13): optional
        ``PackManifest`` loaded from the pack's ``pack.yaml``
        sidecar. When present, the registry validates
        ``manifest.compatible_with`` against the installed volnix
        version AND that the manifest's ``name`` / ``category``
        agree with the pack's ClassVars. When absent, the pack
        is grandfathered under ``GRANDFATHERED_COMPAT_SPEC`` —
        still subject to the volnix-version compatibility check
        (so a 0.2.x volnix refuses a pre-0.2 pack at boot, not
        at runtime).

        Raises:
            ValueError: If pack_name is empty.
            DuplicatePackError: If pack_name already registered.
            IncompatiblePackError: If the pack's compatibility
                specifier excludes the current volnix version.
            PackManifestMismatchError: If manifest fields disagree
                with pack ClassVars.
        """
        if not pack.pack_name:
            raise ValueError("ServicePack must have a non-empty pack_name")
        if pack.pack_name in self._packs:
            raise DuplicatePackError(f"Pack '{pack.pack_name}' is already registered")

        # Phase 4C Step 13 — compatibility gate. Runs BEFORE any
        # indexing so an incompatible pack leaves the registry
        # untouched. Grandfathered packs (no manifest) use the
        # module-level ``GRANDFATHERED_COMPAT_SPEC`` constant.
        self._enforce_pack_compatibility(pack, manifest)

        # Store pack
        self._packs[pack.pack_name] = pack

        # Build tool index from pack.get_tools()
        tools = pack.get_tools()
        if not isinstance(tools, list):
            logger.warning(
                "Pack '%s' get_tools() returned %s instead of list — skipping tool indexing",
                pack.pack_name,
                type(tools).__name__,
            )
            tools = []
        for tool_def in tools:
            tool_name = tool_def.get("name", "") if isinstance(tool_def, dict) else ""
            if tool_name:
                if tool_name in self._tool_index:
                    logger.warning(
                        "Tool '%s' already registered by pack '%s', overwriting with '%s'",
                        tool_name,
                        self._tool_index[tool_name],
                        pack.pack_name,
                    )
                self._tool_index[tool_name] = pack.pack_name

        # Build category index
        self._category_index.setdefault(pack.category, []).append(pack.pack_name)
        logger.info(
            "Registered pack '%s' (category=%s, tools=%d)",
            pack.pack_name,
            pack.category,
            len(tools),
        )

    def get_manifest(self, pack_name: str) -> PackManifest | None:
        """Return the registered ``PackManifest`` for ``pack_name``,
        or ``None`` if the pack was grandfathered (no sidecar).

        PMF Plan Phase 4C Step 13.
        """
        return self._manifests.get(pack_name)

    def _enforce_pack_compatibility(
        self,
        pack: ServicePack,
        manifest: PackManifest | None,
    ) -> None:
        """Internal: run the compatibility gate before indexing.

        Policy (post-impl audit C2):

        - Manifest present → hard enforcement. ``compatible_with``
          checked against installed volnix; mismatch raises
          ``IncompatiblePackError`` at register time.
        - Manifest absent → permissive. A ``DeprecationWarning``
          recommends manifest authorship but the register
          succeeds. Prevents a hard break on the 0.2.0 bump for
          every bundled / third-party pack that hasn't migrated.
          A future major release MAY flip this to hard-enforce.
        """
        if manifest is None:
            import warnings

            warnings.warn(
                f"Pack {pack.pack_name!r} registered without a "
                f"pack.yaml manifest. Manifest declaration will "
                f"become required in a future volnix major release. "
                f"Author a pack.yaml with compatible_with to pin "
                f"the supported volnix range. "
                f"(Grandfather reference spec: {GRANDFATHERED_COMPAT_SPEC})",
                DeprecationWarning,
                stacklevel=3,
            )
            return

        # Manifest + pack ClassVar agreement.
        check_manifest_matches_pack(
            manifest,
            pack_name=pack.pack_name,
            pack_category=pack.category,
            pack_fidelity_tier=pack.fidelity_tier,
        )
        check_compatibility(
            _current_volnix_version(),
            compatible_with=manifest.compatible_with,
            pack_name=pack.pack_name,
        )
        self._manifests[pack.pack_name] = manifest

    def register_profile(
        self,
        profile: ServiceProfile,
        *,
        manifest: PackManifest | None = None,
    ) -> None:
        """Register a service profile. Validates extends_pack and uniqueness.

        Post-impl audit M2 (Step 13): profiles now accept an
        optional ``manifest`` the same way packs do. Compat
        semantics match ``register(pack, manifest=...)``:
        manifest present → hard enforcement of
        ``compatible_with`` against current volnix; manifest
        absent → permissive with a ``DeprecationWarning``
        recommending manifest authorship.
        """
        if not profile.profile_name:
            raise ValueError("ServiceProfile must have a non-empty profile_name")
        if profile.profile_name in self._profiles:
            raise DuplicatePackError(f"Profile '{profile.profile_name}' is already registered")
        if profile.extends_pack not in self._packs:
            raise PackNotFoundError(
                f"Profile '{profile.profile_name}' extends pack '{profile.extends_pack}' "
                f"which is not registered"
            )
        # Step-13 cleanup — run the compat gate before indexing
        # (parallel to pack registration).
        if manifest is None:
            import warnings

            warnings.warn(
                f"Profile {profile.profile_name!r} registered without a "
                f"pack.yaml manifest. Manifest declaration will become "
                f"required in a future volnix major release.",
                DeprecationWarning,
                stacklevel=3,
            )
        else:
            check_manifest_matches_pack(
                manifest,
                pack_name=profile.profile_name,
                pack_category=profile.category,
                pack_fidelity_tier=profile.fidelity_tier,
            )
            check_compatibility(
                _current_volnix_version(),
                compatible_with=manifest.compatible_with,
                pack_name=profile.profile_name,
            )
            self._manifests[profile.profile_name] = manifest

        self._profiles[profile.profile_name] = profile
        self._profile_pack_index.setdefault(profile.extends_pack, []).append(profile.profile_name)

    def discover(
        self,
        verified_path: str | Path | list[str | Path],
        profiled_path: str | None = None,
        *,
        external_paths: list[tuple[str | Path, str]] | None = None,
    ) -> None:
        """Scan filesystem directories and register all discovered packs/profiles.

        Args:
            verified_path: A single path or a list of paths to scan for
                bundled-style ``pack.py`` files under the ``volnix`` namespace
                (PMF Plan Phase 4C Step 2 — accepts list for pack-path
                extensibility). Duplicate pack names across paths are silently
                skipped (first-path wins) — matches the pre-Step-2 behaviour.
            profiled_path: Optional directory of YAML profile files.
            external_paths: (Step 2) List of ``(path, package_prefix)`` pairs
                for packs outside the ``volnix`` namespace. Consumer is
                responsible for placing ``path`` on ``sys.path`` (use
                ``ConfigBuilder.pack_search_path`` for the opt-in helper).
        """
        # Normalise verified_path to a list; accept str / Path / list for
        # backward compatibility with pre-Step-2 single-path callers.
        if isinstance(verified_path, (str, Path)):
            verified_paths: list[str | Path] = [verified_path]
        else:
            verified_paths = list(verified_path)

        for path in verified_paths:
            for pack in discover_packs(path):
                if pack.pack_name not in self._packs:
                    self.register(pack, manifest=_find_pack_manifest(pack))

        if external_paths:
            for path, package_prefix in external_paths:
                for pack in discover_packs(path, package_prefix=package_prefix):
                    if pack.pack_name not in self._packs:
                        self.register(pack, manifest=_find_pack_manifest(pack))

        if profiled_path:
            for profile in discover_profiles(profiled_path):
                if profile.profile_name not in self._profiles:
                    try:
                        self.register_profile(profile)
                    except PackNotFoundError:
                        logger.warning(
                            "Profile '%s' extends unregistered pack '%s'",
                            profile.profile_name,
                            profile.extends_pack,
                        )

    def get_pack(self, pack_name: str) -> ServicePack:
        """Retrieve pack by name. Raises PackNotFoundError."""
        if pack_name not in self._packs:
            raise PackNotFoundError(
                f"Pack '{pack_name}' not registered. Available: {sorted(self._packs.keys())}"
            )
        return self._packs[pack_name]

    def get_pack_for_tool(self, tool_name: str) -> ServicePack:
        """Reverse lookup: tool -> owning pack. Raises PackNotFoundError."""
        pack_name = self._tool_index.get(tool_name)
        if pack_name is None:
            raise PackNotFoundError(
                f"No pack provides tool '{tool_name}'. Available tools: {sorted(self._tool_index.keys())}"
            )
        return self._packs[pack_name]

    def get_packs_for_category(self, category: str) -> list[ServicePack]:
        """Return all packs in a category. Returns [] if unknown category."""
        names = self._category_index.get(category, [])
        return [self._packs[n] for n in names]

    def get_profiles_for_pack(self, pack_name: str) -> list[ServiceProfile]:
        """Return all profiles extending a pack."""
        names = self._profile_pack_index.get(pack_name, [])
        return [self._profiles[n] for n in names]

    def list_packs(self) -> list[dict[str, Any]]:
        """Return metadata for all packs."""
        return [
            {
                "pack_name": p.pack_name,
                "category": p.category,
                "fidelity_tier": p.fidelity_tier,
                "tools": [t["name"] for t in (p.get_tools() or [])],
            }
            for p in self._packs.values()
        ]

    def list_tools(self) -> list[dict[str, Any]]:
        """Return all tools across all packs."""
        tools: list[dict[str, Any]] = []
        for pack in self._packs.values():
            pack_tools = pack.get_tools()
            if not isinstance(pack_tools, list):
                continue
            for tool_def in pack_tools:
                tools.append({**tool_def, "pack_name": pack.pack_name, "category": pack.category})
        return tools

    def has_pack(self, pack_name: str) -> bool:
        return pack_name in self._packs

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._tool_index


def _find_pack_manifest(pack: ServicePack) -> PackManifest | None:
    """Return the ``PackManifest`` for ``pack`` if a ``pack.yaml``
    sidecar exists next to the pack's Python module, else ``None``.

    Post-impl audit C1: discovery previously registered every pack
    without a manifest, making the feature effectively dead for
    bundled packs. This helper locates the sidecar via the pack
    class's source file so ``discover()`` can thread it through.
    IO / parse failures bubble up as ``PackManifestLoadError`` to
    make authoring errors visible at boot.
    """
    import inspect

    try:
        pack_file = Path(inspect.getfile(type(pack)))
    except (TypeError, OSError):
        return None
    manifest_path = pack_file.parent / "pack.yaml"
    if not manifest_path.exists():
        return None
    # Delegate to the loader — raises ``PackManifestLoadError`` on
    # malformed YAML / schema violation / oversize file. The
    # discovery path does NOT swallow those errors; a corrupt
    # manifest SHOULD fail boot.
    return load_manifest(manifest_path)


def _current_volnix_version() -> str:
    """Best-effort discovery of the installed ``volnix`` version
    for compatibility-gate checks.

    Reads ``importlib.metadata.version("volnix")`` directly on
    every call. NOT cached via ``volnix.__version__`` because
    that module-level string is captured once at import time and
    can be polluted by unrelated tests that monkeypatch
    ``importlib.metadata`` (Step-1 fallback regression test). A
    fresh lookup here means the gate always reflects the current
    package metadata.

    Falls back to the ``"0.0.0+source"`` sentinel on
    ``PackageNotFoundError`` — a sentinel that DELIBERATELY fails
    any ``>=0.1`` specifier so source-tree runs against a
    manifest-bearing pack surface "package not installed" at
    register time rather than silently accepting (post-impl audit
    C3).

    PMF Plan Phase 4C Step 13.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("volnix")
    except PackageNotFoundError:
        return "0.0.0+source"
