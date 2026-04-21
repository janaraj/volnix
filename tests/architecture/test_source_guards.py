"""Static architecture guardrails for the Volnix backend."""

from __future__ import annotations

import pytest

from tests.architecture.helpers import (
    PRODUCT_ROOT,
    TEST_ROOT,
    find_attribute_call_offenders,
    find_call_offenders,
    find_import_offenders,
    find_placeholder_tests,
    imported_modules,
    iter_python_files,
    rel_repo_path,
)

pytestmark = pytest.mark.architecture

_ALLOWED_SQLITE_CONSTRUCTORS = {
    "volnix/persistence/manager.py",
    "volnix/persistence/snapshot.py",
}
_ALLOWED_CONCRETE_ENGINE_IMPORTERS = {
    "volnix/registry/composition.py",
}


def test_sqlite_database_construction_has_no_unexpected_offenders():
    """Concrete DB construction should stay tightly bounded."""
    offenders = set(find_call_offenders(PRODUCT_ROOT, {"SQLiteDatabase"}))
    assert offenders == _ALLOWED_SQLITE_CONSTRUCTORS


def test_sqlite_database_construction_is_confined_to_allowlist():
    offenders = set(find_call_offenders(PRODUCT_ROOT, {"SQLiteDatabase"}))
    assert offenders == _ALLOWED_SQLITE_CONSTRUCTORS


def test_low_level_sql_connectors_are_confined_to_sqlite_backend():
    """Direct sqlite connection APIs should only appear inside the sqlite backend."""
    for target in ("aiosqlite.connect", "sqlite3.connect"):
        offenders = set(find_call_offenders(PRODUCT_ROOT, {target}))
        assert offenders == {"volnix/persistence/sqlite.py"}


def test_dynamic_imports_are_confined_to_pack_loader():
    """Dynamic imports are sanctioned only for:
    - Pack discovery (``volnix/packs/loader.py``).
    - The shared hook resolver
      (``volnix/_internal/hook_resolver.py``) used by
      ``trait_extractor_hook`` (Step 12) and ``ledger_redactor``
      (Step 14) — consumers pass a fully-qualified name; the
      platform imports it lazily at hook-resolve time. Factored
      into ``_internal`` by cleanup sweep 2 to eliminate
      duplication (Step 14 audit M4).
    """
    offenders = set(find_call_offenders(PRODUCT_ROOT, {"importlib.import_module"}))
    allowed = {
        "volnix/packs/loader.py",
        "volnix/_internal/hook_resolver.py",
    }
    # Step 14 audit M5: actionable diff on failure so a reviewer
    # knows WHICH new caller broke the guard.
    unexpected = offenders - allowed
    missing = allowed - offenders
    assert offenders == allowed, (
        f"importlib.import_module allowlist violated. "
        f"Unexpected new callers: {sorted(unexpected)}. "
        f"Missing expected callers (did you delete the file?): {sorted(missing)}."
    )


def test_external_entrypoints_do_not_call_state_read_apis():
    adapter_paths = list((PRODUCT_ROOT / "engines" / "adapter").rglob("*.py"))
    gateway_paths = list((PRODUCT_ROOT / "gateway").rglob("*.py"))
    offenders = find_attribute_call_offenders(
        adapter_paths + gateway_paths,
        {"get_entity", "query_entities"},
    )
    assert offenders == {}


def test_external_entrypoints_do_not_import_pack_modules():
    """Adapters and gateway should not wire pack execution directly."""
    target_paths = [
        *iter_python_files(PRODUCT_ROOT / "engines" / "adapter"),
        *iter_python_files(PRODUCT_ROOT / "gateway"),
    ]
    offenders = {}
    for path in target_paths:
        matches = sorted(
            module for module in imported_modules(path) if module.startswith("volnix.packs")
        )
        if matches:
            offenders[rel_repo_path(path)] = matches
    assert offenders == {}


def test_concrete_engine_imports_stay_in_composition_boundaries():
    """Concrete engine-class imports should stay in the composition root or package exports."""
    offenders = find_import_offenders(
        PRODUCT_ROOT,
        lambda module: module.startswith("volnix.engines.") and module.endswith(".engine"),
    )
    filtered = {
        path: modules
        for path, modules in offenders.items()
        if path not in _ALLOWED_CONCRETE_ENGINE_IMPORTERS and not path.endswith("__init__.py")
    }
    assert filtered == {}


def test_verified_packs_do_not_import_runtime_layers():
    """Verified packs should remain isolated from engines, persistence, and bus layers."""
    offenders = find_import_offenders(
        PRODUCT_ROOT / "packs" / "verified",
        lambda module: module.startswith(("volnix.persistence", "volnix.engines", "volnix.bus")),
    )
    assert offenders == {}


def test_active_test_suites_do_not_contain_placeholder_bodies():
    """Integration and architecture suites should not masquerade as implemented coverage."""
    active_roots = [TEST_ROOT / "architecture", TEST_ROOT / "integration"]
    offenders = {}
    for root in active_roots:
        offenders.update(find_placeholder_tests(root))
    assert offenders == {}
