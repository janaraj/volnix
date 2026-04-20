"""Phase 4C Step 2 — ConfigBuilder + VolnixConfig.from_dict tests.

Negative-first per test discipline
(``feedback_test_discipline.md``): every behavior that has an invalid
input, conflicting side effect, or silent-degradation risk gets a
``test_negative_*`` guarding it.

What this module locks in:
- ``VolnixConfig.from_dict`` rejects invalid input and round-trips nested overrides.
- ``ConfigBuilder`` accumulates per-section overrides and validates at ``.build()``.
- ``PackSearchPath`` entries carry ``(path, package_prefix)`` tuple semantics.
- ``ensure_on_syspath`` side-effect contract is loud, opt-out-able, and
  inserts the parent dir for prefixed entries (so ``package_prefix``
  imports resolve without further consumer action).
- ``VolnixApp(config=...)`` accepts ``None | VolnixConfig | ConfigBuilder | dict``
  and rejects other types with a ``TypeError``.
"""

from __future__ import annotations

import inspect
import sys

import pytest
from pydantic import ValidationError

from volnix.app import VolnixApp
from volnix.config.builder import ConfigBuilder
from volnix.config.schema import PackSearchPath, VolnixConfig

# ─── VolnixConfig.from_dict ───────────────────────────────────────────


class TestFromDict:
    def test_negative_empty_dict_uses_all_defaults(self) -> None:
        cfg = VolnixConfig.from_dict({})
        assert cfg.memory.enabled is False
        assert cfg.pack_search_paths == []

    def test_negative_invalid_type_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            VolnixConfig.from_dict({"memory": {"enabled": "not-a-bool-like-string"}})

    def test_negative_pack_search_paths_rejects_non_list(self) -> None:
        with pytest.raises(ValidationError):
            VolnixConfig.from_dict({"pack_search_paths": "/single/string/not/list"})

    def test_negative_pack_search_path_entry_missing_path_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            VolnixConfig.from_dict({"pack_search_paths": [{"package_prefix": "orphan"}]})

    def test_negative_pack_search_path_entry_rejects_non_dict_item(self) -> None:
        with pytest.raises(ValidationError):
            VolnixConfig.from_dict({"pack_search_paths": ["/not/a/dict/or/model"]})

    def test_positive_nested_override_round_trips(self) -> None:
        data = {
            "memory": {"enabled": True, "embedder": "fts5"},
            "pack_search_paths": [{"path": "/custom/path", "package_prefix": "custom"}],
        }
        cfg = VolnixConfig.from_dict(data)
        assert cfg.memory.enabled is True
        assert len(cfg.pack_search_paths) == 1
        assert cfg.pack_search_paths[0].path == "/custom/path"
        assert cfg.pack_search_paths[0].package_prefix == "custom"

    def test_positive_model_dump_round_trips_through_from_dict(self) -> None:
        original = VolnixConfig.from_dict({"memory": {"enabled": True}})
        reconstructed = VolnixConfig.from_dict(original.model_dump(mode="python"))
        assert reconstructed == original
        assert reconstructed is not original


# ─── ConfigBuilder ────────────────────────────────────────────────────


class TestConfigBuilder:
    def test_negative_invalid_base_type_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="VolnixConfig"):
            ConfigBuilder(base="not-a-config")  # type: ignore[arg-type]

    def test_negative_raw_empty_path_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ConfigBuilder().raw("", "value")

    def test_negative_raw_path_conflicts_with_non_dict_value(self) -> None:
        builder = ConfigBuilder()
        builder.raw("simulation.seed", 99)
        with pytest.raises(ValueError, match="conflicts"):
            builder.raw("simulation.seed.subkey", 1)

    def test_negative_merge_section_refuses_non_dict_value(self) -> None:
        builder = ConfigBuilder().raw("memory", "oops-a-string")
        with pytest.raises(ValueError, match="not a mapping"):
            builder.memory(enabled=True)

    def test_negative_repeated_build_calls_produce_independent_configs(self) -> None:
        builder = ConfigBuilder().memory(enabled=True)
        a = builder.build()
        b = builder.build()
        assert a == b
        assert a is not b

    def test_positive_empty_builder_builds_default_config(self) -> None:
        cfg = ConfigBuilder().build()
        assert isinstance(cfg, VolnixConfig)
        assert cfg.memory.enabled is False
        assert cfg.pack_search_paths == []

    def test_positive_single_section_override(self) -> None:
        cfg = ConfigBuilder().memory(enabled=True).build()
        assert cfg.memory.enabled is True

    def test_positive_multi_section_merge_independent(self) -> None:
        cfg = ConfigBuilder().memory(enabled=True).simulation(seed=7).build()
        assert cfg.memory.enabled is True
        assert cfg.simulation.seed == 7

    def test_positive_same_section_called_twice_merges(self) -> None:
        cfg = ConfigBuilder().memory(enabled=True).memory(embedder="fts5").build()
        assert cfg.memory.enabled is True
        assert cfg.memory.embedder == "fts5"

    def test_positive_base_from_existing_config_preserves_values(self) -> None:
        base = ConfigBuilder().memory(enabled=True).build()
        extended = ConfigBuilder(base=base).simulation(seed=99).build()
        assert extended.memory.enabled is True
        assert extended.simulation.seed == 99

    def test_positive_raw_sets_nested_path(self) -> None:
        cfg = ConfigBuilder().raw("runs.data_dir", "/tmp/x").build()
        assert cfg.runs.data_dir == "/tmp/x"


# ─── pack_search_paths + sys.path side effect ────────────────────────


class TestPackSearchPaths:
    def test_negative_empty_path_string_rejected(self) -> None:
        """Catches the silent-``.`` bug: ``str(Path(""))`` is ``"."``
        (cwd), which would register the consumer's working directory
        as a pack search path. Must raise instead."""
        with pytest.raises(ValueError, match="non-empty"):
            ConfigBuilder().pack_search_path("", ensure_on_syspath=False)

    def test_negative_whitespace_only_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ConfigBuilder().pack_search_path("   ", ensure_on_syspath=False)

    def test_negative_duplicate_pack_search_paths_deduped_first_wins(self) -> None:
        """Same (path, prefix) twice — second call is a no-op."""
        cfg = (
            ConfigBuilder()
            .pack_search_path("/a", package_prefix="a", ensure_on_syspath=False)
            .pack_search_path("/a", package_prefix="a", ensure_on_syspath=False)
            .pack_search_path("/b", package_prefix="b", ensure_on_syspath=False)
            .build()
        )
        assert [e.path for e in cfg.pack_search_paths] == ["/a", "/b"]

    def test_negative_same_path_different_prefix_treated_as_distinct(self) -> None:
        """Dedup key is ``(path, prefix)``. Same path under two prefixes
        is a legitimate use case (rare, but a consumer could map the
        same catalog dir to two namespaces)."""
        cfg = (
            ConfigBuilder()
            .pack_search_path("/shared", package_prefix="alpha", ensure_on_syspath=False)
            .pack_search_path("/shared", package_prefix="beta", ensure_on_syspath=False)
            .build()
        )
        prefixes = sorted(e.package_prefix or "" for e in cfg.pack_search_paths)
        assert prefixes == ["alpha", "beta"]

    def test_negative_empty_list_produces_no_entries_and_no_syspath_mutation(
        self, tmp_path
    ) -> None:
        original = list(sys.path)
        try:
            cfg = ConfigBuilder().pack_search_paths([]).build()
            assert cfg.pack_search_paths == []
            assert sys.path == original
        finally:
            sys.path[:] = original

    def test_negative_ensure_on_syspath_false_skips_insertion(self, tmp_path) -> None:
        sentinel = tmp_path / "opt_out_sentinel"
        sentinel.mkdir()
        sentinel_str = str(sentinel)
        original_syspath = list(sys.path)
        try:
            ConfigBuilder().pack_search_path(sentinel_str, ensure_on_syspath=False)
            assert sentinel_str not in sys.path
            assert str(tmp_path) not in sys.path
        finally:
            sys.path[:] = original_syspath

    def test_negative_ensure_on_syspath_idempotent_when_already_present(self, tmp_path) -> None:
        """Calling twice with the same path must not cause duplicate
        sys.path entries — prevents accidental blow-up when a consumer
        constructs multiple builders against shared state."""
        sentinel = tmp_path / "idempotent_sentinel"
        sentinel.mkdir()
        sentinel_str = str(sentinel)
        original_syspath = list(sys.path)
        try:
            ConfigBuilder().pack_search_path(sentinel_str)
            ConfigBuilder().pack_search_path(sentinel_str)
            # No package_prefix → path itself is inserted (bundled mode).
            assert sys.path.count(sentinel_str) == 1
        finally:
            sys.path[:] = original_syspath

    def test_positive_pack_search_paths_bulk_replaces(self) -> None:
        cfg = (
            ConfigBuilder()
            .pack_search_path("/x", package_prefix="x", ensure_on_syspath=False)
            .pack_search_paths([("/a", "a"), ("/b", "b")], ensure_on_syspath=False)
            .build()
        )
        assert [e.path for e in cfg.pack_search_paths] == ["/a", "/b"]

    def test_positive_pack_search_paths_list_dedups_first_wins(self) -> None:
        cfg = (
            ConfigBuilder()
            .pack_search_paths([("/a", "a"), ("/a", "a"), ("/b", "b")], ensure_on_syspath=False)
            .build()
        )
        assert [e.path for e in cfg.pack_search_paths] == ["/a", "/b"]

    def test_positive_pack_search_paths_accepts_dict_entries(self) -> None:
        """Allow pre-shaped dict entries (useful when consumers round-
        trip through ``model_dump``)."""
        cfg = (
            ConfigBuilder()
            .pack_search_paths(
                [{"path": "/a", "package_prefix": "a"}],
                ensure_on_syspath=False,
            )
            .build()
        )
        assert cfg.pack_search_paths[0].path == "/a"
        assert cfg.pack_search_paths[0].package_prefix == "a"

    def test_positive_ensure_on_syspath_inserts_parent_for_prefixed_entry(self, tmp_path) -> None:
        """With ``package_prefix=X``, the PARENT of ``path`` goes on
        sys.path so ``X.<subdir>.pack`` is importable."""
        catalog = tmp_path / "characters"
        catalog.mkdir()
        original_syspath = list(sys.path)
        try:
            ConfigBuilder().pack_search_path(str(catalog), package_prefix="characters")
            assert sys.path[0] == str(tmp_path)
            assert str(catalog) not in sys.path
        finally:
            sys.path[:] = original_syspath

    def test_positive_ensure_on_syspath_inserts_path_for_bundled_entry(self, tmp_path) -> None:
        """Without ``package_prefix`` (bundled mode), the path itself
        is inserted — matches the pre-4C bundled-namespace convention."""
        sentinel = tmp_path / "bundled"
        sentinel.mkdir()
        original_syspath = list(sys.path)
        try:
            ConfigBuilder().pack_search_path(str(sentinel))
            assert sys.path[0] == str(sentinel)
        finally:
            sys.path[:] = original_syspath

    def test_positive_pack_search_paths_list_inserts_first_path_first(self, tmp_path) -> None:
        """When a list is supplied, the FIRST input entry must end up
        earliest on sys.path so precedence semantics survive."""
        a = tmp_path / "a"
        a.mkdir()
        b = tmp_path / "b"
        b.mkdir()
        original_syspath = list(sys.path)
        try:
            ConfigBuilder().pack_search_paths([(str(a), None), (str(b), None)])
            idx_a = sys.path.index(str(a))
            idx_b = sys.path.index(str(b))
            assert idx_a < idx_b
        finally:
            sys.path[:] = original_syspath

    def test_positive_pack_search_path_entry_is_frozen(self) -> None:
        entry = PackSearchPath(path="/x", package_prefix="x")
        with pytest.raises(ValidationError):
            entry.path = "/y"  # type: ignore[misc]

    def test_negative_from_dict_duplicate_entries_deduped(self) -> None:
        """Audit-fold M2: the ``ConfigBuilder`` dedupes at construction
        time. The dict / TOML path must offer the same guarantee —
        otherwise a consumer who round-trips ``model_dump`` back through
        ``from_dict`` (or writes a TOML layer that happens to repeat
        an entry) gets silent duplicates that waste discovery work."""
        cfg = VolnixConfig.from_dict(
            {
                "pack_search_paths": [
                    {"path": "/a", "package_prefix": "x"},
                    {"path": "/a", "package_prefix": "x"},
                    {"path": "/b", "package_prefix": "y"},
                ]
            }
        )
        assert len(cfg.pack_search_paths) == 2
        paths = [(e.path, e.package_prefix) for e in cfg.pack_search_paths]
        assert paths == [("/a", "x"), ("/b", "y")]


# ─── Section-method drift guard (audit-fold M4) ──────────────────────


# Top-level VolnixConfig sections intentionally without a fluent
# ``ConfigBuilder`` method today. Consumers reach them via ``.raw()``.
# When a later 4C step earns a method for one of these, move it OUT
# of this set and add the fluent setter.
#
# Audit-fold C2: this set is DISJOINT from the set of sections that
# already have a method (memory, agency, llm, persistence, simulation,
# pack_search_paths). Keeping the sets disjoint is how the guard
# delivers on the promise in its docstring: deleting a method without
# extending this allowlist drops the section into ``uncovered`` and
# the drift-guard test fires.
_INTENTIONAL_DEFERRED_SECTIONS: frozenset[str] = frozenset(
    {
        "actors",
        "adapter",
        "agents",
        "animator",
        "budget",
        "bus",
        "dashboard",
        "feedback",
        "gateway",
        "ledger",
        "logging",
        "middleware",
        "permission",
        "pipeline",
        "policy",
        "profiles",
        "reporter",
        "responder",
        "runs",
        "simulation_runner",
        "state",
        "templates",
        "validation",
        "webhook",
        "world_compiler",
        "worlds",
    }
)


# ``VolnixConfig`` fields covered by non-standard helpers on
# ``ConfigBuilder`` (plural / side-effecting / multi-method).
# Accounted for separately so the deferred allowlist stays disjoint
# from method-backed section names (audit-fold C2).
_SECTIONS_COVERED_BY_SPECIAL_HELPERS: frozenset[str] = frozenset(
    {
        "pack_search_paths",  # covered by pack_search_path() + pack_search_paths()
    }
)


def _config_builder_section_methods() -> frozenset[str]:
    """Names of ``ConfigBuilder`` methods that correspond to top-level
    ``VolnixConfig`` sections. Excludes the path / raw / build helpers."""
    excluded = {
        "build",
        "raw",
        "pack_search_path",
        "pack_search_paths",
    }
    return frozenset(
        name
        for name, member in inspect.getmembers(ConfigBuilder, predicate=inspect.isfunction)
        if not name.startswith("_") and name not in excluded
    )


class TestSectionMethodDriftGuard:
    """Audit-fold M4: prevents silent drift when a future step adds a
    ``VolnixConfig`` section but forgets to wire a ``ConfigBuilder``
    method. Every top-level schema field MUST be covered by either
    (a) a dedicated fluent method OR (b) the deferred-allowlist above.
    Locking both directions: the allowlist may not include names that
    are NOT in ``VolnixConfig`` (prevents typos and stale entries)."""

    def test_negative_every_schema_section_has_method_or_deferral(self) -> None:
        schema_sections = set(VolnixConfig.model_fields.keys())
        method_names = _config_builder_section_methods()
        uncovered = (
            schema_sections
            - method_names
            - _INTENTIONAL_DEFERRED_SECTIONS
            - _SECTIONS_COVERED_BY_SPECIAL_HELPERS
        )
        assert not uncovered, (
            f"VolnixConfig sections without a ConfigBuilder method or "
            f"explicit deferral: {sorted(uncovered)}. Add a fluent "
            f"method or extend _INTENTIONAL_DEFERRED_SECTIONS."
        )

    def test_negative_deferred_allowlist_disjoint_from_method_backed_sections(
        self,
    ) -> None:
        """Audit-fold C2: the deferred allowlist must NOT include any
        section already backed by a method. Otherwise a method
        deletion would leave the section silently "covered" by the
        deferral, defeating the drift-guard's own promise."""
        method_names = _config_builder_section_methods()
        overlap = _INTENTIONAL_DEFERRED_SECTIONS & method_names
        assert not overlap, (
            f"_INTENTIONAL_DEFERRED_SECTIONS contains names that also "
            f"have a method ({sorted(overlap)}). Remove them from the "
            f"deferred set so a method deletion fires the drift guard."
        )

    def test_negative_deferred_allowlist_entries_all_exist_in_schema(self) -> None:
        schema_sections = set(VolnixConfig.model_fields.keys())
        stale = _INTENTIONAL_DEFERRED_SECTIONS - schema_sections
        assert not stale, (
            f"Stale entries in _INTENTIONAL_DEFERRED_SECTIONS (not in "
            f"VolnixConfig anymore): {sorted(stale)}"
        )

    def test_negative_no_section_method_targets_missing_schema_field(self) -> None:
        """A method on ``ConfigBuilder`` that doesn't match a
        ``VolnixConfig`` section will silently fail at ``build()``
        (Pydantic rejects unknown fields in a frozen model). Catch
        the drift at import/test time instead."""
        schema_sections = set(VolnixConfig.model_fields.keys())
        orphaned = _config_builder_section_methods() - schema_sections
        assert not orphaned, (
            f"ConfigBuilder methods with no corresponding VolnixConfig "
            f"section (will blow up at build() time): {sorted(orphaned)}"
        )


# ─── VolnixApp constructor surface ───────────────────────────────────


class TestVolnixAppConfigAcceptance:
    def test_negative_invalid_type_raises_type_error(self) -> None:
        with pytest.raises(TypeError, match="VolnixConfig"):
            VolnixApp(config=42)  # type: ignore[arg-type]

    def test_negative_invalid_dict_bubbles_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            VolnixApp(config={"pack_search_paths": "not-a-list"})

    def test_negative_tuple_config_rejected(self) -> None:
        """Catches silent-accept bugs: a tuple looks vaguely dict-ish
        but isn't; must raise, not be reinterpreted."""
        with pytest.raises(TypeError, match="VolnixConfig"):
            VolnixApp(config=("memory", True))  # type: ignore[arg-type]

    def test_positive_none_uses_defaults(self) -> None:
        app = VolnixApp()
        assert isinstance(app._config, VolnixConfig)
        assert app._config.memory.enabled is False

    def test_positive_volnix_config_stored_unchanged(self) -> None:
        cfg = VolnixConfig.from_dict({"memory": {"enabled": True}})
        app = VolnixApp(config=cfg)
        assert app._config is cfg

    def test_positive_config_builder_built_on_construct(self) -> None:
        app = VolnixApp(config=ConfigBuilder().memory(enabled=True))
        assert app._config.memory.enabled is True

    def test_positive_dict_validated_via_from_dict(self) -> None:
        app = VolnixApp(config={"memory": {"enabled": True}})
        assert app._config.memory.enabled is True
