"""ConfigBuilder — fluent API for programmatic VolnixConfig construction
(PMF Plan Phase 4C Step 2).

``VolnixConfig`` is frozen Pydantic — direct mutation is impossible.
``ConfigLoader`` is file-driven (6-layer TOML merge). The builder fills
the gap for library consumers: construct a config in code without
writing TOML, validate at ``.build()`` time.

Example::

    # Library-embedding style: external catalog at
    # /opt/myproduct/characters whose subdirectories contain pack.py
    # files that import as ``characters.<name>.pack``. The parent
    # (/opt/myproduct) is placed on sys.path automatically.
    config = (
        ConfigBuilder()
        .memory(enabled=True)
        .pack_search_path(
            "/opt/myproduct/characters",
            package_prefix="characters",
        )
        .build()
    )
    app = VolnixApp(config=config)

Semantics of ``.build()``:
- Accumulated dict is passed to ``VolnixConfig.from_dict()``.
- Pydantic validation runs once — errors surface as ``ValidationError``.
- No shared state between build() calls; each call produces an
  independently-equal config (deep-copy on build).

Section coverage: the builder ships fluent methods only for sections
that (a) exist in ``VolnixConfig`` today AND (b) have been requested
by a consumer. As of Step 2 that set is ``memory``, ``agency``,
``llm``, ``persistence``, and ``simulation``. Sections without a
dedicated setter can still be overridden via :meth:`raw`. Drift
between ``VolnixConfig.model_fields`` and ``ConfigBuilder`` methods
is guarded by the ``TestSectionMethodDriftGuard`` class in
``tests/config/test_config_builder.py``, which enforces that every
top-level section is either covered by a method or on an explicit
deferral allowlist. Future 4C steps extend
both the schema and this builder in lockstep — per the "earn the
method" principle, speculative methods are not shipped.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

from volnix.config._utils import deep_merge
from volnix.config.schema import VolnixConfig


class ConfigBuilder:
    """Fluent accumulator for VolnixConfig overrides."""

    def __init__(self, base: VolnixConfig | dict[str, Any] | None = None) -> None:
        if base is None:
            self._overrides: dict[str, Any] = {}
        elif isinstance(base, VolnixConfig):
            self._overrides = base.model_dump(mode="python")
        elif isinstance(base, dict):
            self._overrides = copy.deepcopy(base)
        else:
            raise TypeError(
                f"ConfigBuilder base must be VolnixConfig | dict | None, got {type(base).__name__}"
            )

    # ── Fluent setters (one per top-level section) ──────────────────
    # Each setter merges its kwargs into the named section, preserving
    # any previously accumulated keys within that section. Only sections
    # that exist in VolnixConfig today are exposed; later 4C steps add
    # more (privacy, sessions, ...) by extending this class.

    def memory(self, **kwargs: Any) -> ConfigBuilder:
        """Merge into the ``[memory]`` section."""
        self._merge_section("memory", kwargs)
        return self

    def privacy(self, **kwargs: Any) -> ConfigBuilder:
        """Merge into the ``[privacy]`` section (PMF Plan Phase 4C
        Step 14). Accepts ``ephemeral: bool`` and
        ``ledger_redactor: str | None``."""
        self._merge_section("privacy", kwargs)
        return self

    def agency(self, **kwargs: Any) -> ConfigBuilder:
        """Merge into the ``[agency]`` section."""
        self._merge_section("agency", kwargs)
        return self

    def llm(self, **kwargs: Any) -> ConfigBuilder:
        """Merge into the ``[llm]`` section."""
        self._merge_section("llm", kwargs)
        return self

    def persistence(self, **kwargs: Any) -> ConfigBuilder:
        """Merge into the ``[persistence]`` section."""
        self._merge_section("persistence", kwargs)
        return self

    def simulation(self, **kwargs: Any) -> ConfigBuilder:
        """Merge into the ``[simulation]`` section."""
        self._merge_section("simulation", kwargs)
        return self

    # ── Pack search path accumulator ───────────────────────────────

    def pack_search_path(
        self,
        path: str | Path,
        *,
        package_prefix: str | None = None,
        ensure_on_syspath: bool = True,
    ) -> ConfigBuilder:
        """Append one entry to ``pack_search_paths``. Idempotent on
        ``(path, package_prefix)``: duplicates are skipped, first-seen
        wins for precedence.

        Args:
            path: Directory whose subdirectories contain ``pack.py``
                modules. When ``package_prefix`` is supplied, the path
                is typically the last segment of the prefix's dotted
                name (e.g. ``/opt/myproduct/characters`` for
                ``package_prefix="characters"``).
            package_prefix: Dotted Python module prefix that maps to
                ``path`` on import. Required for external catalogs
                outside the ``volnix`` namespace; leave ``None`` only
                for paths that live under an importable ``volnix``
                package.
            ensure_on_syspath: If ``True`` (default) and
                ``package_prefix`` is set, inserts the PARENT of
                ``path`` at the head of ``sys.path`` unless already
                present. If ``package_prefix`` is ``None``, inserts
                ``path`` itself (bundled-mode). The value chosen makes
                ``{package_prefix}.<subdir>.pack`` importable without
                further consumer action.

        SIDE EFFECT WARNING: when ``ensure_on_syspath=True``, this
        method mutates process-global ``sys.path``. The check-then-
        insert guard is NOT thread-safe; a library deployment building
        configs concurrently must either (a) set this up once at
        process startup, or (b) pass ``ensure_on_syspath=False`` and
        manage ``sys.path`` externally. ``PackRegistry.discover()``
        does NOT mutate ``sys.path`` — this method is the single
        documented side-effect point.
        """
        path_str = str(path).strip()
        if not path_str:
            raise ValueError("ConfigBuilder.pack_search_path(): path must be non-empty")
        path_str = str(Path(path_str))
        entry = {"path": path_str, "package_prefix": package_prefix}
        entries = list(self._overrides.get("pack_search_paths", []))
        if entry not in entries:
            entries.append(entry)
        self._overrides["pack_search_paths"] = entries

        if ensure_on_syspath:
            syspath_entry = str(Path(path_str).parent) if package_prefix is not None else path_str
            if syspath_entry not in sys.path:
                sys.path.insert(0, syspath_entry)
        return self

    def pack_search_paths(
        self,
        entries: list[tuple[str | Path, str | None]] | list[dict[str, Any]],
        *,
        ensure_on_syspath: bool = True,
    ) -> ConfigBuilder:
        """Replace the entire ``pack_search_paths`` list.

        ``entries`` accepts either tuples of ``(path, package_prefix)``
        or already-shaped dicts with ``path`` / ``package_prefix``
        keys. First-seen wins on dedup.

        ``ensure_on_syspath`` semantics match
        :meth:`pack_search_path` — for each entry the parent dir is
        inserted when ``package_prefix`` is set, otherwise the path
        itself. Iteration order is preserved: the FIRST input entry
        ends up earliest on ``sys.path``. Same thread-safety caveat
        applies.
        """
        normalized: list[dict[str, Any]] = []
        for entry in entries:
            if isinstance(entry, dict):
                normalized.append(
                    {
                        "path": str(Path(entry["path"])),
                        "package_prefix": entry.get("package_prefix"),
                    }
                )
            else:
                path, prefix = entry
                normalized.append({"path": str(Path(path)), "package_prefix": prefix})
        # Dedup preserving input order (first-seen wins).
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str | None]] = set()
        for e in normalized:
            key = (e["path"], e["package_prefix"])
            if key not in seen:
                deduped.append(e)
                seen.add(key)
        self._overrides["pack_search_paths"] = deduped

        if ensure_on_syspath:
            # Insert in reverse so earliest input ends up earliest on sys.path.
            for e in reversed(deduped):
                path_str = e["path"]
                prefix = e["package_prefix"]
                syspath_entry = str(Path(path_str).parent) if prefix is not None else path_str
                if syspath_entry not in sys.path:
                    sys.path.insert(0, syspath_entry)
        return self

    def trait_extractor_hook(self, hook: str | None) -> ConfigBuilder:
        """Set the product-side trait extractor hook (PMF Plan
        Phase 4C Step 12).

        ``hook`` is a dotted-path string in the form
        ``"package.module:callable_name"`` referring to a callable
        that takes an ``ActorDefinition`` and returns a
        ``BehavioralSignature``. Pass ``None`` to clear / revert
        to the bundled default.

        Resolution happens at engine-wiring time via
        ``volnix.actors.trait_extractor.resolve_extractor_hook`` —
        an invalid path raises there, not here.
        """
        self._overrides["trait_extractor_hook"] = hook
        return self

    # ── Escape hatch ───────────────────────────────────────────────

    def raw(self, path: str, value: Any) -> ConfigBuilder:
        """Set a value at a dotted path inside the config dict. Use for
        fields that don't have a dedicated fluent method yet (e.g.
        ``"runs.data_dir"``).

        Raises ``ValueError`` if an intermediate segment conflicts with
        a non-dict value already set at that location.
        """
        if not path:
            raise ValueError("ConfigBuilder.raw(): path must be non-empty")
        parts = path.split(".")
        cursor: dict[str, Any] = self._overrides
        for part in parts[:-1]:
            existing = cursor.get(part)
            if existing is None:
                new: dict[str, Any] = {}
                cursor[part] = new
                cursor = new
            elif isinstance(existing, dict):
                cursor = existing
            else:
                raise ValueError(
                    f"ConfigBuilder.raw({path!r}): path conflicts with "
                    f"an existing non-dict value at {part!r}"
                )
        cursor[parts[-1]] = value
        return self

    # ── Build ──────────────────────────────────────────────────────

    def build(self) -> VolnixConfig:
        """Validate + freeze. Can be called multiple times; each call
        returns an independently-equal config (no shared references)."""
        return VolnixConfig.from_dict(copy.deepcopy(self._overrides))

    # ── Internals ──────────────────────────────────────────────────

    def _merge_section(self, section: str, kwargs: dict[str, Any]) -> None:
        existing = self._overrides.get(section, {})
        if not isinstance(existing, dict):
            raise ValueError(
                f"ConfigBuilder.{section}(...): existing value at {section!r} is not a mapping"
            )
        self._overrides[section] = deep_merge(existing, kwargs)
