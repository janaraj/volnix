"""Tests for volnix.packs.loader — dynamic pack/profile discovery."""

import tempfile
from pathlib import Path

import pytest

from volnix.packs.base import ServicePack
from volnix.packs.loader import (
    _module_path_from_filepath,
    discover_packs,
    discover_profiles,
)


class TestDiscoverPacks:
    def test_discover_from_verified_dir(self):
        """discover_packs finds the EmailPack from the real filesystem."""
        verified_dir = Path(__file__).resolve().parents[2] / "volnix" / "packs" / "verified"
        packs = discover_packs(verified_dir)
        assert len(packs) >= 1
        pack_names = [p.pack_name for p in packs]
        assert "gmail" in pack_names
        # Each discovered pack is a ServicePack instance
        for p in packs:
            assert isinstance(p, ServicePack)
            assert p.pack_name  # non-empty

    def test_discover_empty_dir(self):
        """discover_packs returns [] for an empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            packs = discover_packs(tmpdir)
            assert packs == []

    def test_discover_nonexistent_dir(self):
        """discover_packs returns [] for a path that does not exist."""
        packs = discover_packs("/nonexistent/path/that/does/not/exist")
        assert packs == []

    def test_discover_bad_dir_skipped(self):
        """Directories without pack.py are silently skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a subdirectory without pack.py
            subdir = Path(tmpdir) / "not_a_pack"
            subdir.mkdir()
            (subdir / "something.py").write_text("x = 1\n")
            packs = discover_packs(tmpdir)
            assert packs == []

    def test_discover_profiles_empty(self):
        """discover_profiles returns [] when no profile.py files exist."""
        verified_dir = Path(__file__).resolve().parents[2] / "volnix" / "packs" / "verified"
        profiles = discover_profiles(verified_dir)
        # Email pack has no profile.py, so profiles should be empty
        assert profiles == []


class TestModulePathComputation:
    def test_module_path_from_filepath(self):
        """Converts filesystem path to correct dotted module path."""
        p = Path("/Users/someone/workspace/volnix/packs/verified/gmail/pack.py")
        result = _module_path_from_filepath(p)
        assert result == "volnix.packs.verified.gmail.pack"

    def test_module_path_no_volnix_root(self):
        """Returns None if 'volnix' is not in the path parts."""
        p = Path("/tmp/some/other/project/pack.py")
        result = _module_path_from_filepath(p)
        assert result is None
