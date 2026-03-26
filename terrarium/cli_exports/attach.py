"""Attach/detach helpers — patch and restore agent config files.

Each agent type has a known config file path. ``patch_config`` backs
up the original, merges the Terrarium config snippet, and writes it
atomically. ``restore_config`` restores from backup.
"""
from __future__ import annotations

import json
import logging
import platform
import shutil
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BACKUP_SUFFIX = ".terrarium-backup"


# ---------------------------------------------------------------------------
# Known config paths per agent type
# ---------------------------------------------------------------------------


def _get_config_path(
    agent: str, workspace: Path | None = None
) -> Path | None:
    """Return the known config file path for an agent type."""
    system = platform.system()
    ws = workspace or Path.cwd()

    if agent == "claude-desktop":
        if system == "Darwin":
            return (
                Path.home()
                / "Library"
                / "Application Support"
                / "Claude"
                / "claude_desktop_config.json"
            )
        if system == "Linux":
            return (
                Path.home()
                / ".config"
                / "claude"
                / "claude_desktop_config.json"
            )
        return (
            Path.home()
            / "AppData"
            / "Roaming"
            / "Claude"
            / "claude_desktop_config.json"
        )

    if agent == "cursor":
        return ws / ".cursor" / "mcp.json"

    if agent == "windsurf":
        return ws / ".windsurf" / "mcp.json"

    return None


# ---------------------------------------------------------------------------
# Patch and restore
# ---------------------------------------------------------------------------


def patch_config(
    config_path: Path,
    patch: dict[str, Any],
) -> None:
    """Back up existing config and merge the patch atomically.

    H4 fix: uses atomic write (temp file + rename).
    H5 fix: always overwrites backup to capture latest pre-patch state.
    """
    # Read existing config (or start empty)
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            logger.warning(
                "Malformed JSON in %s — starting fresh",
                config_path,
            )
            existing = {}
    else:
        existing = {}

    # H5 fix: always backup current state
    backup_path = config_path.with_suffix(
        config_path.suffix + _BACKUP_SUFFIX
    )
    if config_path.exists():
        shutil.copy2(config_path, backup_path)
        logger.info("Backed up %s to %s", config_path, backup_path)

    # Deep merge (one level)
    for key, value in patch.items():
        if (
            key in existing
            and isinstance(existing[key], dict)
            and isinstance(value, dict)
        ):
            existing[key].update(value)
        else:
            existing[key] = value

    # H4 fix: atomic write (temp file + rename)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(existing, indent=2) + "\n"
    try:
        fd, temp_path = tempfile.mkstemp(
            dir=config_path.parent, suffix=".tmp"
        )
        with open(fd, "w") as f:
            f.write(content)
        Path(temp_path).rename(config_path)
    except OSError:
        config_path.write_text(content)

    logger.info("Patched %s", config_path)


def restore_config(config_path: Path) -> bool:
    """Restore config from backup. Returns True if restored."""
    backup_path = config_path.with_suffix(
        config_path.suffix + _BACKUP_SUFFIX
    )
    if not backup_path.exists():
        return False

    shutil.copy2(backup_path, config_path)
    backup_path.unlink()
    logger.info("Restored %s from backup", config_path)
    return True
