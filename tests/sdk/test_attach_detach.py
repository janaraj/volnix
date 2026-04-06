"""Tests for attach/detach config patching."""

from __future__ import annotations

import json

from volnix.cli_exports.attach import patch_config, restore_config


def test_patch_creates_backup(tmp_path):
    """patch_config backs up existing config."""
    config_file = tmp_path / "config.json"
    config_file.write_text('{"existing": true}')

    patch_config(config_file, {"mcpServers": {"volnix": {"url": "test"}}})

    backup = tmp_path / "config.json.volnix-backup"
    assert backup.exists()
    assert json.loads(backup.read_text()) == {"existing": True}


def test_patch_merges_config(tmp_path):
    """patch_config merges into existing config."""
    config_file = tmp_path / "config.json"
    config_file.write_text('{"existing": true, "mcpServers": {"other": {}}}')

    patch_config(config_file, {"mcpServers": {"volnix": {"url": "test"}}})

    result = json.loads(config_file.read_text())
    assert result["existing"] is True
    assert "other" in result["mcpServers"]
    assert "volnix" in result["mcpServers"]


def test_patch_creates_new_file(tmp_path):
    """patch_config creates config file if it doesn't exist."""
    config_file = tmp_path / "new_config.json"

    patch_config(config_file, {"mcpServers": {"volnix": {"url": "test"}}})

    assert config_file.exists()
    result = json.loads(config_file.read_text())
    assert "volnix" in result["mcpServers"]


def test_restore_from_backup(tmp_path):
    """restore_config restores original and removes backup."""
    config_file = tmp_path / "config.json"
    config_file.write_text('{"patched": true}')

    backup = tmp_path / "config.json.volnix-backup"
    backup.write_text('{"original": true}')

    assert restore_config(config_file) is True
    assert json.loads(config_file.read_text()) == {"original": True}
    assert not backup.exists()


def test_restore_no_backup_returns_false(tmp_path):
    """restore_config returns False when no backup exists."""
    config_file = tmp_path / "config.json"
    config_file.write_text('{"current": true}')

    assert restore_config(config_file) is False


def test_patch_malformed_json(tmp_path):
    """patch_config handles malformed JSON in existing file."""
    config_file = tmp_path / "config.json"
    config_file.write_text("{bad json")

    patch_config(config_file, {"mcpServers": {"volnix": {}}})

    result = json.loads(config_file.read_text())
    assert "volnix" in result["mcpServers"]


def test_second_patch_updates_backup(tmp_path):
    """H5: second attach overwrites backup with latest state."""
    config_file = tmp_path / "config.json"
    config_file.write_text('{"v": 1}')

    # First patch
    patch_config(config_file, {"volnix": "first"})
    backup = tmp_path / "config.json.volnix-backup"
    assert json.loads(backup.read_text()) == {"v": 1}

    # Second patch — backup should now contain the first-patched state
    patch_config(config_file, {"volnix": "second"})
    assert json.loads(backup.read_text())["volnix"] == "first"
