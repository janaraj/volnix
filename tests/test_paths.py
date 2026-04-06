"""Tests for volnix.paths — path resolution, sanitization, security.

Covers: resolve_blueprint, resolve_preset, sanitize_filename,
path traversal prevention, precedence chain, listing, error handling.
"""

from __future__ import annotations

import os
from unittest.mock import patch

# ── sanitize_filename ────────────────────────────────────────────


class TestSanitizeFilename:
    """sanitize_filename strips traversal, special chars, and caps length."""

    def test_basic_name(self):
        from volnix.paths import sanitize_filename

        assert sanitize_filename("My Support World") == "my_support_world"

    def test_traversal_stripped(self):
        from volnix.paths import sanitize_filename

        result = sanitize_filename("../../evil/payload")
        assert ".." not in result
        assert "/" not in result

    def test_slashes_replaced(self):
        from volnix.paths import sanitize_filename

        result = sanitize_filename("a/b\\c")
        assert "/" not in result
        assert "\\" not in result

    def test_empty_string(self):
        from volnix.paths import sanitize_filename

        assert sanitize_filename("") == "unnamed"

    def test_only_special_chars(self):
        from volnix.paths import sanitize_filename

        assert sanitize_filename("!!!") == "unnamed"

    def test_long_name_truncated(self):
        from volnix.paths import sanitize_filename

        result = sanitize_filename("a" * 200)
        assert len(result) <= 100

    def test_leading_dots_stripped(self):
        from volnix.paths import sanitize_filename

        result = sanitize_filename(".hidden_file")
        assert not result.startswith(".")

    def test_unicode_replaced(self):
        from volnix.paths import sanitize_filename

        result = sanitize_filename("世界テスト")
        assert result  # Should produce something, not empty


# ── resolve_blueprint — security ─────────────────────────────────


class TestResolveBlueprintSecurity:
    """resolve_blueprint rejects traversal, absolute paths, empty strings."""

    def test_empty_string_returns_none(self):
        from volnix.paths import resolve_blueprint

        assert resolve_blueprint("") is None

    def test_whitespace_only_returns_none(self):
        from volnix.paths import resolve_blueprint

        assert resolve_blueprint("   ") is None

    def test_path_traversal_returns_none(self):
        from volnix.paths import resolve_blueprint

        assert resolve_blueprint("../../etc/passwd") is None

    def test_absolute_path_returns_none(self):
        from volnix.paths import resolve_blueprint

        assert resolve_blueprint("/etc/passwd.yaml") is None

    def test_dot_dot_in_name_returns_none(self):
        from volnix.paths import resolve_blueprint

        assert resolve_blueprint("..secret") is None

    def test_slash_in_name_returns_none(self):
        from volnix.paths import resolve_blueprint

        assert resolve_blueprint("path/to/file") is None


# ── resolve_blueprint — resolution chain ────────────────────────


class TestResolveBlueprintChain:
    """resolve_blueprint follows priority: exact → user → community → official."""

    def test_exact_relative_path(self, tmp_path):
        from volnix.paths import resolve_blueprint

        world_file = tmp_path / "my_world.yaml"
        world_file.write_text("name: test")
        # Change to tmp_path so relative path resolves
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            result = resolve_blueprint("my_world.yaml")
            assert result is not None
            assert result.name == "my_world.yaml"
        finally:
            os.chdir(old_cwd)

    def test_official_blueprint_found(self):
        from volnix.paths import resolve_blueprint

        result = resolve_blueprint("customer_support")
        assert result is not None
        assert "official" in str(result)
        assert result.name == "customer_support.yaml"

    def test_unknown_name_returns_none(self):
        from volnix.paths import resolve_blueprint

        assert resolve_blueprint("nonexistent_world_xyz") is None

    def test_user_takes_precedence_over_official(self, tmp_path):
        from volnix.paths import resolve_blueprint

        with patch.dict(os.environ, {"VOLNIX_HOME": str(tmp_path)}):
            user_dir = tmp_path / "blueprints"
            user_dir.mkdir(parents=True)
            (user_dir / "customer_support.yaml").write_text("name: user version")

            result = resolve_blueprint("customer_support")
            assert result is not None
            assert "blueprints" in str(result)
            # User version, not official
            assert result.read_text() == "name: user version"


# ── resolve_preset — security + chain ───────────────────────────


class TestResolvePresetSecurity:
    """resolve_preset rejects traversal and follows user → official chain."""

    def test_empty_returns_none(self):
        from volnix.paths import resolve_preset

        assert resolve_preset("") is None

    def test_traversal_returns_none(self):
        from volnix.paths import resolve_preset

        assert resolve_preset("../../etc/passwd") is None

    def test_builtin_preset_found(self):
        from volnix.paths import resolve_preset

        result = resolve_preset("messy")
        assert result is not None
        assert result.name == "messy.yaml"

    def test_unknown_preset_returns_none(self):
        from volnix.paths import resolve_preset

        assert resolve_preset("nonexistent_preset_xyz") is None

    def test_user_preset_shadows_builtin(self, tmp_path):
        from volnix.paths import resolve_preset

        with patch.dict(os.environ, {"VOLNIX_HOME": str(tmp_path)}):
            user_dir = tmp_path / "presets"
            user_dir.mkdir(parents=True)
            (user_dir / "messy.yaml").write_text("information: pristine")

            result = resolve_preset("messy")
            assert result is not None
            assert result.read_text() == "information: pristine"


# ── list_blueprints / list_presets ──────────────────────────────


class TestListBlueprintsAndPresets:
    """Listing functions return all tiers without crashing on bad files."""

    def test_list_blueprints_includes_official(self):
        from volnix.paths import list_blueprints

        items = list_blueprints()
        names = {i["name"] for i in items if i["tier"] == "official"}
        assert "customer_support" in names

    def test_list_blueprints_includes_user(self, tmp_path):
        from volnix.paths import list_blueprints

        with patch.dict(os.environ, {"VOLNIX_HOME": str(tmp_path)}):
            user_dir = tmp_path / "blueprints"
            user_dir.mkdir(parents=True)
            (user_dir / "my_test.yaml").write_text("world:\n  name: Test")

            items = list_blueprints()
            user_names = {i["name"] for i in items if i["tier"] == "user"}
            assert "my_test" in user_names

    def test_list_blueprints_corrupt_yaml_skipped(self, tmp_path):
        from volnix.paths import list_blueprints

        with patch.dict(os.environ, {"VOLNIX_HOME": str(tmp_path)}):
            user_dir = tmp_path / "blueprints"
            user_dir.mkdir(parents=True)
            (user_dir / "corrupt.yaml").write_text(": [invalid yaml {{{{")
            (user_dir / "valid.yaml").write_text("world:\n  name: Valid")

            items = list_blueprints()
            user_names = {i["name"] for i in items if i["tier"] == "user"}
            # Corrupt file skipped, valid file present
            assert "valid" in user_names
            assert "corrupt" in user_names  # Listed but with empty description

    def test_list_presets_includes_builtin(self):
        from volnix.paths import list_presets

        items = list_presets()
        names = {i["name"] for i in items if i["tier"] == "built-in"}
        assert {"ideal", "messy", "hostile"}.issubset(names)


# ── Error handling ──────────────────────────────────────────────


class TestErrorHandling:
    """Path functions handle permission errors gracefully."""

    def test_volnix_home_non_writable(self, tmp_path):
        """volnix_home doesn't crash if VOLNIX_HOME is not writable."""
        from volnix.paths import volnix_home

        # Point to a path that can't be created
        fake_path = str(tmp_path / "readonly" / "deeply" / "nested")
        (tmp_path / "readonly").mkdir()
        (tmp_path / "readonly").chmod(0o444)

        try:
            with patch.dict(os.environ, {"VOLNIX_HOME": fake_path}):
                result = volnix_home()
                # Should return the path even if mkdir failed
                assert str(result) == fake_path
        finally:
            (tmp_path / "readonly").chmod(0o755)
