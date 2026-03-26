"""Terrarium path resolution — user home, blueprints, presets, data.

Single source of truth for all file system paths. No other module
should hardcode directory paths.

User home: ``~/.terrarium/`` (override with ``TERRARIUM_HOME`` env var)
Package dirs: ``terrarium/blueprints/``, ``terrarium/presets/``
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_PACKAGE_DIR = Path(__file__).parent


# ── Filename sanitization ────────────────────────────────────────


def sanitize_filename(name: str) -> str:
    """Sanitize a string for safe use as a filename.

    Strips path separators, traversal characters, and special chars.
    Returns a lowercase, underscore-separated name capped at 100 chars.
    """
    name = name.lower().replace(" ", "_")
    name = re.sub(r"[^\w\-.]", "_", name)  # Only alphanumeric, _, -, .
    name = name.strip("._")  # No leading dots or underscores
    return name[:100] or "unnamed"


# ── User home (~/.terrarium/) ────────────────────────────────────


def _safe_mkdir(path: Path) -> None:
    """Create directory, ignoring permission/OS errors."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # Dir might not be writable; callers check .exists()


def terrarium_home() -> Path:
    """Return user data directory. Respects TERRARIUM_HOME env var."""
    home = Path(os.environ.get("TERRARIUM_HOME", Path.home() / ".terrarium"))
    _safe_mkdir(home)
    return home


def user_blueprints_dir() -> Path:
    """User-created world blueprints: ``~/.terrarium/blueprints/``"""
    d = terrarium_home() / "blueprints"
    _safe_mkdir(d)
    return d


def user_presets_dir() -> Path:
    """User-created reality presets: ``~/.terrarium/presets/``"""
    d = terrarium_home() / "presets"
    _safe_mkdir(d)
    return d


def user_data_dir() -> Path:
    """Runtime data (runs, state, snapshots): ``~/.terrarium/data/``"""
    d = terrarium_home() / "data"
    _safe_mkdir(d)
    return d


def user_config_dir() -> Path:
    """User config overrides: ``~/.terrarium/config/``"""
    d = terrarium_home() / "config"
    _safe_mkdir(d)
    return d


# ── Package directories (read-only at runtime) ──────────────────


def official_blueprints_dir() -> Path:
    """First-class blueprints shipped with the package."""
    return _PACKAGE_DIR / "blueprints" / "official"


def community_blueprints_dir() -> Path:
    """Community-contributed blueprints shipped with the package."""
    return _PACKAGE_DIR / "blueprints" / "community"


def official_presets_dir() -> Path:
    """Built-in reality presets shipped with the package."""
    return _PACKAGE_DIR / "presets"


# ── Resolution chains ────────────────────────────────────────────


def _is_safe_name(name: str) -> bool:
    """Check that a name has no path traversal or absolute path components."""
    return bool(name) and ".." not in name and "/" not in name and "\\" not in name


def resolve_blueprint(name: str) -> Path | None:
    """Resolve a blueprint name to a file path.

    Priority: exact path → user → community → official → None (NL).
    Rejects absolute paths, traversal (``..``), and empty strings.
    """
    if not name or not name.strip():
        return None

    # 1. Exact relative file path (no absolute, no traversal)
    p = Path(name)
    if p.suffix in (".yaml", ".yml"):
        if not p.is_absolute() and ".." not in p.parts and p.exists():
            return p.resolve()

    # 2-4. Name-based lookup — reject unsafe names
    stem = p.stem if name.endswith((".yaml", ".yml")) else name
    if not _is_safe_name(stem):
        return None

    for search_dir in (
        user_blueprints_dir(),
        community_blueprints_dir(),
        official_blueprints_dir(),
    ):
        candidate = search_dir / f"{stem}.yaml"
        if candidate.exists():
            return candidate

    return None  # Caller treats as NL description


def resolve_preset(name: str) -> Path | None:
    """Resolve a reality preset name.

    Priority: user presets → official presets → None.
    Rejects traversal and empty strings.
    """
    if not _is_safe_name(name):
        return None
    for search_dir in (user_presets_dir(), official_presets_dir()):
        candidate = search_dir / f"{name}.yaml"
        if candidate.exists():
            return candidate
    return None


def list_blueprints() -> list[dict[str, Any]]:
    """List all available blueprints across tiers.

    Returns a list of dicts with ``tier``, ``name``, ``description``, ``path``.
    """
    import yaml

    results: list[dict[str, Any]] = []
    tiers = [
        ("official", official_blueprints_dir()),
        ("community", community_blueprints_dir()),
        ("user", user_blueprints_dir()),
    ]
    for tier, directory in tiers:
        if not directory.exists():
            continue
        for f in sorted(directory.glob("*.yaml")):
            desc = ""
            try:
                data = yaml.safe_load(f.read_text()) or {}
                world = data.get("world", data)
                desc = str(
                    world.get("description", world.get("name", ""))
                )[:80]
            except Exception:
                pass
            results.append({
                "tier": tier,
                "name": f.stem,
                "description": desc.strip(),
                "path": str(f),
            })
    return results


def list_presets() -> list[dict[str, Any]]:
    """List all available reality presets (built-in + user)."""
    results: list[dict[str, Any]] = []
    tiers = [
        ("built-in", official_presets_dir()),
        ("user", user_presets_dir()),
    ]
    for tier, directory in tiers:
        if not directory.exists():
            continue
        for f in sorted(directory.glob("*.yaml")):
            results.append({"tier": tier, "name": f.stem, "path": str(f)})
    return results
