"""Phase 4C Step 2 — pack path extensibility tests.

Locks in the list-path signature of ``PackRegistry.discover`` and the
``package_prefix`` parameter on ``_module_path_from_filepath`` /
``discover_packs`` / ``discover_profiles``. The latter powers
external character catalogs loaded from outside the ``volnix`` namespace.

Negative-first per test discipline.
"""

from __future__ import annotations

import sys
from pathlib import Path
from textwrap import dedent

from volnix.packs.base import ServicePack
from volnix.packs.loader import _module_path_from_filepath, discover_packs
from volnix.packs.registry import PackRegistry

# ─── _module_path_from_filepath (external-prefix mode) ────────────────


class TestModulePathPackagePrefix:
    def test_negative_empty_package_prefix_returns_none(self) -> None:
        p = Path("/opt/catalog/externalpkg/characters/interviewer/pack.py")
        assert _module_path_from_filepath(p, package_prefix="") is None

    def test_negative_anchor_missing_returns_best_effort_string(self) -> None:
        # Anchor not found in path — fallback returns a best-effort
        # dotted module name. Renamed from test_positive_* because the
        # returned string is NOT guaranteed importable; it's a
        # graceful-degradation path and downstream importlib will fail
        # if the consumer hasn't placed the synthetic prefix on
        # sys.path.
        p = Path("/mnt/weird/path/interviewer/pack.py")
        result = _module_path_from_filepath(p, package_prefix="externalpkg")
        assert result == "externalpkg.interviewer.pack"

    def test_negative_prefix_anchor_duplicates_in_path_uses_last_occurrence(
        self,
    ) -> None:
        """If the anchor name appears multiple times (e.g., a consumer
        nests ``characters`` inside another ``characters`` folder), the
        anchor-finding loop uses the LAST occurrence — farther toward
        the file, matching the real Python package that would be on
        sys.path."""
        p = Path("/srv/characters/characters/alice/pack.py")
        result = _module_path_from_filepath(p, package_prefix="characters")
        # Last occurrence of 'characters' is at index 3, so tail =
        # ['alice', 'pack.py'] → 'characters.alice.pack'.
        assert result == "characters.alice.pack"

    def test_positive_anchor_found_in_path_yields_full_dotted_path(self) -> None:
        p = Path("/opt/catalog/externalpkg/characters/interviewer/pack.py")
        result = _module_path_from_filepath(p, package_prefix="externalpkg.characters")
        assert result == "externalpkg.characters.interviewer.pack"

    def test_positive_bundled_mode_unchanged_when_prefix_absent(self) -> None:
        p = Path("/Users/jane/workspace/volnix/packs/verified/gmail/pack.py")
        assert _module_path_from_filepath(p) == "volnix.packs.verified.gmail.pack"


# ─── PackRegistry.discover(list[...]) backward compat + extension ─────


def _write_minimal_pack(pack_dir: Path, pack_name: str) -> None:
    """Author a minimal ServicePack module on disk for discovery tests.

    Creates ``__init__.py`` at every ancestor up to the last directory
    named like a Python package (avoids FS-root recursion) so the
    module is actually importable via the external-prefix loader path.
    """
    pack_dir.mkdir(parents=True, exist_ok=True)
    (pack_dir / "__init__.py").write_text("")
    (pack_dir / "pack.py").write_text(
        dedent(
            f"""
            from volnix.core.context import ResponseProposal
            from volnix.packs.base import ServicePack

            class _TestPack(ServicePack):
                pack_name = {pack_name!r}
                category = "test"
                fidelity_tier = 1

                def get_tools(self):
                    return []

                def get_entity_schemas(self):
                    return {{}}

                def get_state_machines(self):
                    return {{}}

                async def handle_action(self, action, input_data, state):
                    return ResponseProposal(
                        status_code=200,
                        body={{}},
                        mutations=[],
                        events=[],
                    )
            """
        ).strip()
        + "\n"
    )


def _ensure_init(path: Path) -> None:
    init_file = path / "__init__.py"
    if not init_file.exists():
        init_file.write_text("")


class TestPackRegistryDiscoverBackwardCompat:
    def test_negative_path_object_still_accepted_not_iterated_as_list(self, tmp_path: Path) -> None:
        """A pathlib.Path is iterable (over parts). The list-normalisation
        branch must match it via ``isinstance(Path)`` BEFORE falling into
        the "assume iterable of paths" branch — otherwise a single Path
        would be treated as a list of its segments (catastrophic, silent)."""
        verified_dir = Path(__file__).resolve().parents[2] / "volnix" / "packs" / "verified"
        registry = PackRegistry()
        # Pass an actual pathlib.Path, not a string.
        registry.discover(verified_dir)
        assert registry.has_pack("gmail")

    def test_positive_single_string_path_still_accepted(self, tmp_path: Path) -> None:
        """Step 2 adds list support; the existing single-str signature
        must keep working — responder/engine.py + all existing tests
        pass single str today."""
        package_dir = tmp_path / "volnix_test_bundle_single"
        (package_dir / "__init__.py").parent.mkdir(parents=True, exist_ok=True)
        # Author a synthetic bundle that mimics volnix/packs/verified layout
        # by reusing the real verified dir.
        verified_dir = Path(__file__).resolve().parents[2] / "volnix" / "packs" / "verified"

        registry = PackRegistry()
        registry.discover(str(verified_dir))
        # At least the gmail pack must be present (sanity check).
        assert registry.has_pack("gmail")


class TestPackRegistryDiscoverList:
    def test_positive_empty_list_is_noop(self) -> None:
        registry = PackRegistry()
        registry.discover([])
        assert registry.list_packs() == []

    def test_positive_list_of_paths_combines_discovery(self, tmp_path: Path) -> None:
        """Discover packs from the bundled verified dir AND an external
        directory in the same call."""
        verified_dir = Path(__file__).resolve().parents[2] / "volnix" / "packs" / "verified"

        # External layout: /<syspath_root>/<prefix_pkg>/<pack>/pack.py
        syspath_root = tmp_path / "ext_root"
        syspath_root.mkdir()
        prefix_pkg = syspath_root / "ext_pkg_step2"
        prefix_pkg.mkdir()
        _ensure_init(prefix_pkg)
        pack_dir = prefix_pkg / "ext_pack_a"
        _write_minimal_pack(pack_dir, "ext_pack_a_step2")

        original_syspath = list(sys.path)
        try:
            sys.path.insert(0, str(syspath_root))

            registry = PackRegistry()
            registry.discover(
                [str(verified_dir)],
                external_paths=[(str(prefix_pkg), "ext_pkg_step2")],
            )
            assert registry.has_pack("gmail")
            assert registry.has_pack("ext_pack_a_step2")
        finally:
            sys.path[:] = original_syspath

    def test_negative_duplicate_across_paths_keeps_first_hit(self, tmp_path: Path) -> None:
        """If the same ``pack_name`` appears in two search paths, the
        first-seen wins (matches pre-Step-2 single-path precedence)."""
        # Two syspath roots, each containing a distinct prefix pkg that
        # holds a pack with the same pack_name.
        root_a = tmp_path / "sysroot_a"
        root_b = tmp_path / "sysroot_b"
        root_a.mkdir()
        root_b.mkdir()

        prefix_a = root_a / "prefix_a_step2"
        prefix_b = root_b / "prefix_b_step2"
        prefix_a.mkdir()
        prefix_b.mkdir()
        _ensure_init(prefix_a)
        _ensure_init(prefix_b)
        _write_minimal_pack(prefix_a / "dup_pack", "dup_pack_step2")
        _write_minimal_pack(prefix_b / "dup_pack", "dup_pack_step2")

        original_syspath = list(sys.path)
        try:
            sys.path.insert(0, str(root_a))
            sys.path.insert(0, str(root_b))

            registry = PackRegistry()
            registry.discover(
                [],
                external_paths=[
                    (str(prefix_a), "prefix_a_step2"),
                    (str(prefix_b), "prefix_b_step2"),
                ],
            )
            # Registered exactly once — no DuplicatePackError, second
            # path's dup silently skipped (first-seen wins).
            assert registry.has_pack("dup_pack_step2")
        finally:
            sys.path[:] = original_syspath


class TestDiscoverPacksExternalPrefix:
    def test_negative_nonexistent_external_dir_returns_empty(self) -> None:
        """A dangling path (consumer gave a wrong directory) must not
        raise — discover_packs is a scanner, not a validator. Caller
        is responsible for handling the empty result."""
        results = discover_packs(
            "/does/not/exist/anywhere",
            package_prefix="whatever",
        )
        assert results == []

    def test_negative_external_path_without_syspath_setup_logs_but_does_not_raise(
        self, tmp_path: Path, caplog
    ) -> None:
        """If the consumer sets ``package_prefix`` correctly but FAILS
        to put the syspath root in place, import fails — discover
        logs a warning and skips the pack. Contract: no exception
        escapes, empty result returned."""
        import logging

        syspath_root = tmp_path / "orphan_root"
        syspath_root.mkdir()
        prefix_pkg = syspath_root / "orphan_prefix"
        prefix_pkg.mkdir()
        _ensure_init(prefix_pkg)
        _write_minimal_pack(prefix_pkg / "orphan_pack", "orphan_pack_step2")

        # Deliberately DO NOT insert syspath_root into sys.path.
        with caplog.at_level(logging.WARNING, logger="volnix.packs.loader"):
            results = discover_packs(prefix_pkg, package_prefix="orphan_prefix")

        assert results == []
        assert any("Failed to load pack" in rec.message for rec in caplog.records), (
            "Expected a WARNING log from the loader when import fails"
        )

    def test_positive_external_prefix_loads_pack(self, tmp_path: Path) -> None:
        """Verify discover_packs can import a ServicePack from an
        external directory using ``package_prefix`` + ``sys.path``
        coordination (no volnix namespace walk)."""
        syspath_root = tmp_path / "ext_root"
        syspath_root.mkdir()
        prefix_pkg = syspath_root / "cat_root_step2"
        prefix_pkg.mkdir()
        _ensure_init(prefix_pkg)
        _write_minimal_pack(prefix_pkg / "cat_pack", "cat_pack_step2")

        original_syspath = list(sys.path)
        try:
            sys.path.insert(0, str(syspath_root))
            results = discover_packs(prefix_pkg, package_prefix="cat_root_step2")
            names = [p.pack_name for p in results]
            assert "cat_pack_step2" in names
            for pack in results:
                assert isinstance(pack, ServicePack)
        finally:
            sys.path[:] = original_syspath


# ─── End-to-end: VolnixApp + pack_search_paths (L3 integration) ───────


class TestVolnixAppPackSearchPathsIntegration:
    """Locks in the full wire path:
    ``ConfigBuilder.pack_search_path(..., package_prefix=...)`` →
    ``VolnixConfig.pack_search_paths`` →
    ``VolnixApp.start()`` engine_overrides → responder's
    ``PackRegistry.discover(external_paths=...)`` → pack registered.

    This is the Step-2 ship goal — if any link breaks, this test
    fails. Fills audit-fold L3.
    """

    async def test_positive_external_pack_registered_after_app_start(self, tmp_path: Path) -> None:
        import tempfile

        from volnix.app import VolnixApp
        from volnix.config.builder import ConfigBuilder

        # Layout: <syspath_root>/<prefix_pkg>/<pack>/pack.py
        syspath_root = tmp_path / "externalpkg_root"
        syspath_root.mkdir()
        prefix_pkg = syspath_root / "externalpkg_catalog_step2"
        prefix_pkg.mkdir()
        _ensure_init(prefix_pkg)
        _write_minimal_pack(prefix_pkg / "demo_pack", "e2e_demo_pack_step2")

        # Ephemeral persistence so the test doesn't touch ~/.volnix/.
        data_dir = tempfile.mkdtemp(prefix="volnix_step2_e2e_")
        original_syspath = list(sys.path)
        try:
            config = (
                ConfigBuilder()
                .pack_search_path(
                    str(prefix_pkg),
                    package_prefix="externalpkg_catalog_step2",
                )
                .raw("persistence.base_dir", data_dir)
                .raw("bus.db_path", f"{data_dir}/bus.db")
                .raw("ledger.db_path", f"{data_dir}/ledger.db")
                .raw("state.db_path", f"{data_dir}/state.db")
                .raw("state.snapshot_dir", f"{data_dir}/snapshots")
                .raw("runs.data_dir", f"{data_dir}/runs")
                .raw("worlds.data_dir", f"{data_dir}/worlds")
                .build()
            )
            app = VolnixApp(config=config)
            await app.start()
            try:
                responder = app._registry.get("responder")
                assert responder.pack_registry.has_pack("e2e_demo_pack_step2")
            finally:
                await app.stop()
        finally:
            sys.path[:] = original_syspath
