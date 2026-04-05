"""Profile registry -- central index for YAML-based service profiles.

Maintains indices by service_name and by operation name for fast lookup.
Separate from PackRegistry, which indexes Tier 1 Python packs.
"""

from __future__ import annotations

import logging

from volnix.packs.profile_schema import ServiceProfileData

logger = logging.getLogger(__name__)


class ProfileRegistry:
    """Central registry for YAML service profiles with multi-key lookup."""

    def __init__(self) -> None:
        self._profiles: dict[str, ServiceProfileData] = {}  # service_name -> profile
        self._action_index: dict[str, str] = {}  # operation_name -> service_name

    def register(self, profile: ServiceProfileData) -> None:
        """Register a profile. Builds index by service_name + operation names.

        If a profile with the same service_name is already registered,
        it is replaced (last-write-wins for re-registration during reload).
        """
        self._profiles[profile.service_name] = profile

        # Build action -> service_name index
        for op in profile.operations:
            if op.name:
                existing = self._action_index.get(op.name)
                if existing is not None and existing != profile.service_name:
                    logger.warning(
                        "Action '%s' already registered by '%s', skipping from '%s'",
                        op.name,
                        self._action_index[op.name],
                        profile.service_name,
                    )
                    continue  # Skip, don't overwrite
                self._action_index[op.name] = profile.service_name

        logger.info(
            "ProfileRegistry: registered '%s' (category=%s, operations=%d)",
            profile.service_name,
            profile.category,
            len(profile.operations),
        )

    def get_profile(self, service_name: str) -> ServiceProfileData | None:
        """Look up a profile by service name."""
        return self._profiles.get(service_name)

    def get_profile_for_action(self, action_name: str) -> ServiceProfileData | None:
        """Reverse lookup: action name -> owning profile."""
        service_name = self._action_index.get(action_name)
        if service_name is None:
            return None
        return self._profiles.get(service_name)

    def list_profiles(self) -> list[ServiceProfileData]:
        """Return all registered profiles."""
        return list(self._profiles.values())

    def has_profile(self, service_name: str) -> bool:
        """Check if a profile exists for the given service name."""
        return service_name in self._profiles
