"""Dynamic pack and profile loader.

Discovers ServicePack/ServiceProfile subclasses by scanning directory trees
and importing pack.py / profile.py modules via importlib.

This is the ONLY module that performs dynamic imports of packs.
"""
from __future__ import annotations

import importlib
import inspect
import logging
from pathlib import Path

from volnix.packs.base import ServicePack, ServiceProfile

logger = logging.getLogger(__name__)


def discover_packs(base_dir: str | Path) -> list[ServicePack]:
    """Scan subdirectories of base_dir for pack.py files.

    For each subdirectory containing pack.py:
    1. Compute dotted module path: volnix.packs.verified.{subdir}.pack
    2. Import via importlib.import_module
    3. Find all ServicePack subclasses (not the ABC itself)
    4. Instantiate each (zero-arg constructor)

    Bad directories are logged as warnings and skipped.
    """
    results: list[ServicePack] = []
    base = Path(base_dir)
    if not base.is_dir():
        return results

    for subdir in sorted(base.iterdir()):
        if not subdir.is_dir() or subdir.name.startswith("_"):
            continue
        pack_file = subdir / "pack.py"
        if not pack_file.exists():
            continue
        module_path = _module_path_from_filepath(pack_file)
        if module_path is None:
            logger.warning("Could not determine module path for %s", pack_file)
            continue
        try:
            mod = importlib.import_module(module_path)
            classes = _find_subclasses(mod, ServicePack)
            for cls in classes:
                instance = cls()
                if instance.pack_name:  # skip malformed packs
                    results.append(instance)
                    logger.info("Discovered pack: %s (%s)", instance.pack_name, module_path)
        except Exception as exc:
            logger.warning("Failed to load pack from %s: %s", subdir.name, exc)
    return results


def discover_profiles(base_dir: str | Path) -> list[ServiceProfile]:
    """Same pattern as discover_packs but for profile.py / ServiceProfile."""
    results: list[ServiceProfile] = []
    base = Path(base_dir)
    if not base.is_dir():
        return results

    for subdir in sorted(base.iterdir()):
        if not subdir.is_dir() or subdir.name.startswith("_"):
            continue
        profile_file = subdir / "profile.py"
        if not profile_file.exists():
            continue
        module_path = _module_path_from_filepath(profile_file)
        if module_path is None:
            continue
        try:
            mod = importlib.import_module(module_path)
            classes = _find_subclasses(mod, ServiceProfile)
            for cls in classes:
                instance = cls()
                if instance.profile_name:
                    results.append(instance)
                    logger.info("Discovered profile: %s (%s)", instance.profile_name, module_path)
        except Exception as exc:
            logger.warning("Failed to load profile from %s: %s", subdir.name, exc)
    return results


def _find_subclasses(module: object, base_class: type) -> list[type]:
    """Find all classes in module that are concrete subclasses of base_class."""
    found: list[type] = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if (
            issubclass(obj, base_class)
            and obj is not base_class
            and not inspect.isabstract(obj)
        ):
            found.append(obj)
    return found


def _module_path_from_filepath(filepath: Path) -> str | None:
    """Convert filesystem path to dotted module path.

    Finds the 'volnix' PACKAGE directory (the one containing __init__.py)
    and builds the module path from there.
    Example: /Users/.../volnix/packs/verified/gmail/pack.py
           -> volnix.packs.verified.gmail.pack
    """
    parts = filepath.resolve().parts
    # Find the FIRST 'volnix' in the path that has an __init__.py
    # (distinguishes the Python package from the project root dir)
    idx = None
    for i, part in enumerate(parts):
        if part == "volnix":
            candidate = Path(*parts[: i + 1])
            if (candidate / "__init__.py").exists():
                idx = i
                break  # Use the first volnix that is a Python package
    if idx is None:
        # Fallback: use the last occurrence
        for i in range(len(parts) - 1, -1, -1):
            if parts[i] == "volnix":
                idx = i
                break
    if idx is None:
        return None
    module_parts = list(parts[idx:])
    module_parts[-1] = module_parts[-1].replace(".py", "")
    return ".".join(module_parts)
