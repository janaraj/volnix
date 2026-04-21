"""Phase 4C Step 13 — PackManifest + compatibility-gate tests.

Locks:
- PackManifest schema: name / version / compatible_with validated;
  version must be PEP-440, compatible_with must parse as SpecifierSet;
  extra fields rejected.
- Grandfather policy: packs without a manifest default to
  ``GRANDFATHERED_COMPAT_SPEC`` which must include current volnix.
- Registry gate: a pack declaring ``compatible_with`` that excludes
  the current volnix version raises ``IncompatiblePackError``
  at register time (not runtime).
- Manifest ↔ ClassVar agreement: mismatched name or category raises
  ``PackManifestMismatchError``.
- YAML loader: missing file, bad YAML, non-dict top level all wrap
  cleanly into ``PackManifestLoadError``.

Negative ratio: 8/15 = 53%.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from volnix.core.context import ResponseProposal
from volnix.core.errors import (
    IncompatiblePackError,
    PackManifestMismatchError,
)
from volnix.packs.base import ServicePack
from volnix.packs.manifest import (
    GRANDFATHERED_COMPAT_SPEC,
    PackManifest,
    PackManifestLoadError,
    check_compatibility,
    load_manifest,
)
from volnix.packs.registry import PackRegistry


class _MockPack(ServicePack):
    pack_name = "mock_manifest_test"
    category = "test_category"
    fidelity_tier = 1

    def get_tools(self):
        return []

    def get_entity_schemas(self):
        return {}

    def get_state_machines(self):
        return {}

    async def handle_action(self, action, input_data, state):
        return ResponseProposal(response_body={})


def _manifest(**overrides) -> PackManifest:
    defaults = {
        "name": "mock_manifest_test",
        "version": "1.0.0",
        "compatible_with": ">=0.1,<0.3",
        "category": "test_category",
    }
    defaults.update(overrides)
    return PackManifest(**defaults)


# ─── Schema validation ────────────────────────────────────────────


def test_negative_empty_name_rejected() -> None:
    with pytest.raises(ValidationError):
        _manifest(name="")


def test_negative_invalid_version_rejected() -> None:
    with pytest.raises(ValidationError):
        _manifest(version="not-a-semver-thing-xyz")


def test_negative_invalid_compatible_with_rejected() -> None:
    with pytest.raises(ValidationError):
        _manifest(compatible_with="~~~bogus")


def test_negative_extra_fields_rejected() -> None:
    """extra="forbid" catches typo'd fields at author time."""
    with pytest.raises(ValidationError):
        PackManifest(
            name="x",
            version="1.0.0",
            compatible_with=">=0.1",
            typo_field="ignored",  # type: ignore[call-arg]
        )


def test_positive_valid_manifest_roundtrips() -> None:
    m = _manifest()
    restored = PackManifest.model_validate_json(m.model_dump_json())
    assert restored == m


# ─── check_compatibility ──────────────────────────────────────────


def test_positive_current_volnix_satisfies_grandfather_spec() -> None:
    """The grandfather constant must include the real installed
    version or every existing bundled pack would fail at boot."""
    from importlib.metadata import version

    check_compatibility(
        version("volnix"),
        compatible_with=GRANDFATHERED_COMPAT_SPEC,
        pack_name="grandfathered_test",
    )


def test_negative_version_outside_spec_raises() -> None:
    with pytest.raises(IncompatiblePackError, match="does not include"):
        check_compatibility(
            "0.5.0",
            compatible_with=">=0.1,<0.3",
            pack_name="future_pack",
        )


def test_negative_invalid_spec_raises_at_check_time() -> None:
    with pytest.raises(IncompatiblePackError):
        check_compatibility(
            "0.1.9",
            compatible_with="!!not-a-spec",
            pack_name="broken_pack",
        )


# ─── Registry integration ────────────────────────────────────────


def test_positive_register_without_manifest_permissive_with_warning() -> None:
    """Post-impl audit C2: manifest-less registration succeeds with
    a ``DeprecationWarning`` — not a hard fail. Prevents the 0.2.0
    bump from bricking every bundled pack."""
    import warnings

    registry = PackRegistry()
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        registry.register(_MockPack())
    depr = [w for w in captured if issubclass(w.category, DeprecationWarning)]
    assert depr, "expected DeprecationWarning on manifest-less register"
    assert "pack.yaml" in str(depr[0].message)
    assert registry.has_pack("mock_manifest_test")
    assert registry.get_manifest("mock_manifest_test") is None


def test_positive_register_with_manifest_stores_it() -> None:
    registry = PackRegistry()
    manifest = _manifest()
    registry.register(_MockPack(), manifest=manifest)
    assert registry.get_manifest("mock_manifest_test") == manifest


def test_negative_register_pack_incompatible_raises() -> None:
    """A pack declaring ``compatible_with=">=1.0"`` fails the gate
    against current volnix 0.1.9."""
    registry = PackRegistry()
    manifest = _manifest(compatible_with=">=1.0")
    with pytest.raises(IncompatiblePackError):
        registry.register(_MockPack(), manifest=manifest)
    # Critical: incompatible pack must NOT leak into registry indices.
    assert not registry.has_pack("mock_manifest_test")


def test_negative_register_manifest_name_mismatch_raises() -> None:
    registry = PackRegistry()
    manifest = _manifest(name="different_name")
    with pytest.raises(PackManifestMismatchError, match="name"):
        registry.register(_MockPack(), manifest=manifest)
    assert not registry.has_pack("mock_manifest_test")


def test_negative_register_manifest_category_mismatch_raises() -> None:
    registry = PackRegistry()
    manifest = _manifest(category="wrong_category")
    with pytest.raises(PackManifestMismatchError, match="category"):
        registry.register(_MockPack(), manifest=manifest)


# ─── YAML loader ───────────────────────────────────────────────────


def test_negative_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(PackManifestLoadError, match="not found"):
        load_manifest(tmp_path / "nope.yaml")


def test_negative_load_malformed_yaml_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.yaml"
    p.write_text("name: pack\n  nested wrong\n", encoding="utf-8")
    with pytest.raises(PackManifestLoadError):
        load_manifest(p)


def test_negative_load_non_dict_raises(tmp_path: Path) -> None:
    p = tmp_path / "list.yaml"
    p.write_text("- name: pack\n", encoding="utf-8")
    with pytest.raises(PackManifestLoadError, match="mapping"):
        load_manifest(p)


def test_positive_load_valid_manifest(tmp_path: Path) -> None:
    p = tmp_path / "pack.yaml"
    p.write_text(
        'name: alice\nversion: "1.2.0"\ncompatible_with: ">=0.2,<0.3"\ncategory: interview\n',
        encoding="utf-8",
    )
    m = load_manifest(p)
    assert m.name == "alice"
    assert m.version == "1.2.0"


# ─── Post-impl audit regression tests ─────────────────────────────


def test_negative_empty_compatible_with_rejected() -> None:
    """Post-impl audit H2: empty string would silently match every
    volnix version; must be rejected at validator time."""
    with pytest.raises(ValidationError, match="non-empty"):
        _manifest(compatible_with="")


def test_negative_whitespace_compatible_with_rejected() -> None:
    with pytest.raises(ValidationError):
        _manifest(compatible_with="   ")


def test_negative_yaml_with_alias_rejected(tmp_path: Path) -> None:
    """Post-impl audit H3: pack.yaml alias amplification guard."""
    p = tmp_path / "bomb.yaml"
    p.write_text(
        'name: bomb\nversion: "1.0.0"\ncompatible_with: ">=0.1"\n'
        "author: &anchor\n  key: value\ndescription: *anchor\n",
        encoding="utf-8",
    )
    with pytest.raises(PackManifestLoadError):
        load_manifest(p)


def test_negative_oversize_manifest_rejected(tmp_path: Path) -> None:
    """Post-impl audit H3: 256KB cap protects against payload-
    stuffing attacks. 512KB file is rejected pre-parse."""
    p = tmp_path / "huge.yaml"
    p.write_text(
        'name: huge\nversion: "1.0.0"\ncompatible_with: ">=0.1"\n'
        "description: " + ("x" * (512 * 1024)) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(PackManifestLoadError, match="exceeds"):
        load_manifest(p)


def test_negative_grandfather_packs_fail_on_manifest_compat_at_future_volnix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Post-impl audit M4: when a MANIFEST-declared pack's
    ``compatible_with`` excludes a future volnix version, the
    registry raises at boot — load-bearing for the feature."""
    # Import the module object BEFORE monkeypatching — under some
    # test orderings ``volnix.packs`` isn't yet an attribute of
    # the freshly-reloaded ``volnix`` module (it's a sub-package
    # imported lazily).
    from volnix.packs import registry as registry_module

    monkeypatch.setattr(
        registry_module, "_current_volnix_version", lambda: "0.5.0"
    )
    registry = PackRegistry()
    manifest = _manifest(compatible_with=">=0.1,<0.3")
    with pytest.raises(IncompatiblePackError):
        registry.register(_MockPack(), manifest=manifest)


def test_positive_register_finds_pack_yaml_sidecar(tmp_path: Path) -> None:
    """Post-impl audit C1: ``discover`` now auto-loads ``pack.yaml``
    sidecars. This test simulates the sidecar-next-to-module
    convention by pointing ``_find_pack_manifest`` at a pack whose
    source file we control."""
    import inspect

    from volnix.packs.registry import _find_pack_manifest

    # Write a pack.yaml next to this test file's directory; our
    # _MockPack lives in the tests/packs/ folder so the sidecar
    # would be located there. Use a temp-dir pack instead via
    # a synthetic class.
    module_dir = Path(inspect.getfile(_MockPack)).parent
    sidecar = module_dir / "pack.yaml"
    assert not sidecar.exists(), "unexpected pre-existing pack.yaml"
    sidecar.write_text(
        "name: mock_manifest_test\n"
        'version: "1.0.0"\n'
        'compatible_with: ">=0.1,<0.3"\n'
        "category: test_category\n",
        encoding="utf-8",
    )
    try:
        manifest = _find_pack_manifest(_MockPack())
        assert manifest is not None
        assert manifest.name == "mock_manifest_test"
    finally:
        sidecar.unlink()


def test_positive_find_pack_manifest_returns_none_when_no_sidecar() -> None:
    """Post-impl audit C1: absent sidecar returns None — the
    grandfather path (permissive deprecation warning) then kicks in."""
    from volnix.packs.registry import _find_pack_manifest

    assert _find_pack_manifest(_MockPack()) is None
