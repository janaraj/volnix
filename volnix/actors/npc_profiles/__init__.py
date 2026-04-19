"""Activation-profile loader registry.

Mirrors ``volnix/deliverable_presets/__init__.py``. Each profile is a
YAML file adjacent to this module whose stem matches the ``name`` field
in the file contents. :func:`load_activation_profile` parses and
validates the YAML into a frozen :class:`ActivationProfile`; results
are cached per-process.

Adding a new Active-NPC archetype is a one-file change:

1. Create ``volnix/actors/npc_profiles/<name>.yaml``.
2. Create ``volnix/actors/npc_profiles/prompts/<template>.j2``.
3. Add ``"<name>"`` to :data:`AVAILABLE_PROFILES`.

No engine code changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from volnix.actors.activation_profile import ActivationProfile

_PROFILES_DIR = Path(__file__).parent

# Cache loaded profiles to avoid repeated disk I/O + Pydantic validation.
_cache: dict[str, ActivationProfile] = {}

AVAILABLE_PROFILES: tuple[str, ...] = ("consumer_user",)


def load_activation_profile(name: str) -> ActivationProfile:
    """Load an activation profile by name.

    Args:
        name: Profile name (matches YAML stem, e.g. ``"consumer_user"``).

    Returns:
        The frozen :class:`ActivationProfile` instance.

    Raises:
        FileNotFoundError: If the profile YAML does not exist.
        ValueError: If the YAML is malformed or fails Pydantic validation.
    """
    if name in _cache:
        return _cache[name]

    path = _PROFILES_DIR / f"{name}.yaml"
    if not path.exists():
        available = ", ".join(AVAILABLE_PROFILES)
        raise FileNotFoundError(
            f"Activation profile '{name}' not found at {path}. Available profiles: {available}"
        )

    with open(path) as f:
        data: Any = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Profile '{name}' YAML must be a mapping, got {type(data).__name__}")

    try:
        profile = ActivationProfile(**data)
    except Exception as exc:  # Pydantic raises ValidationError — surface as ValueError
        raise ValueError(f"Profile '{name}' failed validation: {exc}") from exc

    if profile.name != name:
        raise ValueError(
            f"Profile '{name}' YAML declares name={profile.name!r} — must match filename stem."
        )

    _cache[name] = profile
    return profile


def list_profiles() -> list[dict[str, str]]:
    """Return summary info for every profile in :data:`AVAILABLE_PROFILES`.

    Skips profiles whose YAML is missing or malformed so the registry
    never crashes the app just because one optional profile is broken.
    """
    out: list[dict[str, str]] = []
    for name in AVAILABLE_PROFILES:
        try:
            profile = load_activation_profile(name)
        except (FileNotFoundError, ValueError):
            continue
        out.append({"name": profile.name, "description": profile.description})
    return out


def _clear_cache() -> None:
    """Testing helper — clear the in-memory profile cache."""
    _cache.clear()


class ActivationProfileLoader:
    """Concrete :class:`ActivationProfileLoaderProtocol` adapter.

    Wraps the module-level loader functions so they satisfy the
    Protocol shape (``load(name) -> ActivationProfile``,
    ``list_available() -> list[str]``). A class instance — not a module
    function — is what gets injected via the composition root so the
    Protocol type-check is satisfied at run time.
    """

    def load(self, name: str) -> ActivationProfile:
        return load_activation_profile(name)

    def list_available(self) -> list[str]:
        return [p["name"] for p in list_profiles()]
