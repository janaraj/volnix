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

logger = logging.getLogger(__name__)


class PackRegistry:
    """Central registry for packs and profiles with multi-key lookup."""

    def __init__(self) -> None:
        self._packs: dict[str, ServicePack] = {}
        self._tool_index: dict[str, str] = {}  # tool_name -> pack_name
        self._category_index: dict[str, list[str]] = {}  # category -> [pack_name]
        self._profiles: dict[str, ServiceProfile] = {}
        self._profile_pack_index: dict[str, list[str]] = {}  # pack_name -> [profile_name]

    def register(self, pack: ServicePack) -> None:
        """Register a pack. Builds all indices from pack's ABC methods.

        Raises:
            ValueError: If pack_name is empty.
            DuplicatePackError: If pack_name already registered.
        """
        if not pack.pack_name:
            raise ValueError("ServicePack must have a non-empty pack_name")
        if pack.pack_name in self._packs:
            raise DuplicatePackError(f"Pack '{pack.pack_name}' is already registered")

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

    def register_profile(self, profile: ServiceProfile) -> None:
        """Register a service profile. Validates extends_pack and uniqueness."""
        if not profile.profile_name:
            raise ValueError("ServiceProfile must have a non-empty profile_name")
        if profile.profile_name in self._profiles:
            raise DuplicatePackError(f"Profile '{profile.profile_name}' is already registered")
        if profile.extends_pack not in self._packs:
            raise PackNotFoundError(
                f"Profile '{profile.profile_name}' extends pack '{profile.extends_pack}' "
                f"which is not registered"
            )
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
                    self.register(pack)

        if external_paths:
            for path, package_prefix in external_paths:
                for pack in discover_packs(path, package_prefix=package_prefix):
                    if pack.pack_name not in self._packs:
                        self.register(pack)

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
