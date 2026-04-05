"""Profile loader -- reads .profile.yaml files and produces ServiceProfileData.

Scans a directory for *.profile.yaml files, parses each into
ServiceProfileData. Provides save/roundtrip support for generated profiles.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from volnix.packs.profile_schema import ServiceProfileData

logger = logging.getLogger(__name__)


class ProfileLoader:
    """Loads YAML service profiles from a directory."""

    def __init__(self, profiles_dir: Path | str | None = None) -> None:
        self._profiles_dir = Path(profiles_dir) if profiles_dir else None

    def discover(self) -> list[str]:
        """List all profile names found in the profiles directory.

        Scans for *.profile.yaml files (flat) and subdirectory profile.yaml
        files. Returns the list of discovered profile names (service_name).
        """
        if self._profiles_dir is None or not self._profiles_dir.is_dir():
            return []

        names: list[str] = []

        # Pattern 1: profiles/jira.profile.yaml (flat)
        for yaml_file in sorted(self._profiles_dir.glob("*.profile.yaml")):
            profile = self._load_file(yaml_file)
            if profile:
                names.append(profile.service_name)

        # Pattern 2: profiles/jira/profile.yaml (subdirectory)
        for subdir in sorted(self._profiles_dir.iterdir()):
            if subdir.is_dir() and not subdir.name.startswith("_"):
                yaml_file = subdir / "profile.yaml"
                if yaml_file.exists():
                    profile = self._load_file(yaml_file)
                    if profile:
                        names.append(profile.service_name)

        logger.info("ProfileLoader: discovered %d profiles: %s", len(names), names)
        return names

    def load(self, service_name: str) -> ServiceProfileData | None:
        """Load a specific profile by service name.

        Searches for ``<service_name>.profile.yaml`` in the profiles
        directory and also ``<service_name>/profile.yaml`` subdirectory.
        Returns None if not found or unparseable.
        """
        if self._profiles_dir is None or not self._profiles_dir.is_dir():
            return None

        # Try flat file first
        flat_path = self._profiles_dir / f"{service_name}.profile.yaml"
        if flat_path.exists():
            return self._load_file(flat_path)

        # Try subdirectory
        subdir_path = self._profiles_dir / service_name / "profile.yaml"
        if subdir_path.exists():
            return self._load_file(subdir_path)

        return None

    def save(self, profile: ServiceProfileData) -> Path:
        """Write a ServiceProfileData to disk as a .profile.yaml file.

        Returns the path of the written file.
        """
        if self._profiles_dir is None:
            raise ValueError("No profiles_dir configured for ProfileLoader")

        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        path = self._profiles_dir / f"{profile.service_name}.profile.yaml"

        data = profile.model_dump(mode="json", exclude_none=True)
        with path.open("w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        logger.info("ProfileLoader: saved profile '%s' to %s", profile.service_name, path)
        return path

    def list_profiles(self) -> list[ServiceProfileData]:
        """Load and return all profiles from the directory."""
        if self._profiles_dir is None or not self._profiles_dir.is_dir():
            return []

        profiles: list[ServiceProfileData] = []
        seen_services: dict[str, str] = {}  # service_name -> first file path

        # Flat files
        for yaml_file in sorted(self._profiles_dir.glob("*.profile.yaml")):
            profile = self._load_file(yaml_file)
            if profile:
                seen_services[profile.service_name] = str(yaml_file)
                profiles.append(profile)

        # Subdirectories
        for subdir in sorted(self._profiles_dir.iterdir()):
            if subdir.is_dir() and not subdir.name.startswith("_"):
                yaml_file = subdir / "profile.yaml"
                if yaml_file.exists():
                    profile = self._load_file(yaml_file)
                    if profile:
                        if profile.service_name in seen_services:
                            logger.warning(
                                "Duplicate profile for service '%s': "
                                "found in '%s' and '%s'. Using first.",
                                profile.service_name,
                                seen_services[profile.service_name],
                                str(yaml_file),
                            )
                        else:
                            seen_services[profile.service_name] = str(yaml_file)
                            profiles.append(profile)

        return profiles

    @staticmethod
    def _load_file(path: Path) -> ServiceProfileData | None:
        """Parse a single .profile.yaml file."""
        try:
            with path.open("r") as f:
                raw = yaml.safe_load(f)
            if not isinstance(raw, dict):
                logger.warning("Profile %s is not a dict", path)
                return None
            return ServiceProfileData(**raw)
        except Exception as exc:
            logger.warning("Failed to load profile %s: %s", path, exc)
            return None
