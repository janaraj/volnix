"""Phase 4C Step 11 — CharacterDefinition + CharacterLoader tests.

Locks:
- Schema: CharacterDefinition is frozen, id required, metadata
  is a free-form bag.
- Loader: YAML files in a directory become ``{id: CharacterDefinition}``.
- Error path: bad YAML, duplicate id, non-dict top-level, missing
  directory all raise ``CharacterCatalogError``.

Negative ratio: 5/9 = 55%.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from volnix.actors.character import CharacterDefinition
from volnix.actors.character_loader import (
    CharacterCatalogError,
    CharacterLoader,
)
from volnix.core.errors import VolnixError


def _write(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


# ─── CharacterDefinition ────────────────────────────────────────────


def test_negative_character_definition_requires_id() -> None:
    with pytest.raises(ValidationError):
        CharacterDefinition(name="nameless")  # type: ignore[call-arg]


def test_positive_character_definition_is_frozen() -> None:
    c = CharacterDefinition(id="c-1")
    with pytest.raises(Exception):
        c.name = "changed"  # type: ignore[misc]


def test_positive_character_definition_to_actor_spec_shape() -> None:
    c = CharacterDefinition(
        id="c-1",
        name="Alice",
        role="interviewer",
        persona="direct and impatient",
        activation_profile="consumer_user",
        metadata={"age": 45},
    )
    spec = c.to_actor_spec()
    assert spec["id"] == "c-1"
    assert spec["name"] == "Alice"
    assert spec["role"] == "interviewer"
    assert spec["persona"] == "direct and impatient"
    assert spec["activation_profile"] == "consumer_user"
    assert spec["metadata"] == {"age": 45}


def test_positive_character_definition_to_actor_spec_omits_optional_fields() -> None:
    """When ``activation_profile`` is None and metadata empty, the
    spec should NOT include those keys — consumers that merge
    specs don't want None overwrites."""
    c = CharacterDefinition(id="c-1")
    spec = c.to_actor_spec()
    assert "activation_profile" not in spec
    assert "metadata" not in spec


# ─── CharacterLoader ────────────────────────────────────────────────


def test_negative_load_directory_missing_raises(tmp_path: Path) -> None:
    loader = CharacterLoader()
    with pytest.raises(CharacterCatalogError):
        loader.load_directory(tmp_path / "nonexistent")


def test_negative_load_directory_malformed_yaml_raises(tmp_path: Path) -> None:
    _write(tmp_path / "bad.yaml", "id: c-1\n  name: nested wrong")
    loader = CharacterLoader()
    with pytest.raises(CharacterCatalogError):
        loader.load_directory(tmp_path)


def test_negative_load_directory_non_dict_top_level_raises(tmp_path: Path) -> None:
    _write(tmp_path / "list.yaml", "- id: c-1")
    with pytest.raises(CharacterCatalogError):
        CharacterLoader().load_directory(tmp_path)


def test_negative_load_directory_duplicate_id_raises(tmp_path: Path) -> None:
    _write(tmp_path / "a.yaml", "id: same-id\nname: first")
    _write(tmp_path / "b.yaml", "id: same-id\nname: second")
    with pytest.raises(CharacterCatalogError, match="duplicate"):
        CharacterLoader().load_directory(tmp_path)


def test_positive_load_directory_happy_path(tmp_path: Path) -> None:
    _write(
        tmp_path / "alice.yaml",
        "id: alice\nname: Alice\nrole: mentor\npersona: calm\n",
    )
    _write(
        tmp_path / "bob.yml",
        "id: bob\nname: Bob\nactivation_profile: consumer_user\n",
    )
    # Empty file — must be skipped, not raise.
    _write(tmp_path / "empty.yaml", "")
    # Non-YAML file — must be ignored, not loaded.
    _write(tmp_path / "readme.txt", "not a character")

    catalog = CharacterLoader().load_directory(tmp_path)
    assert set(catalog.keys()) == {"alice", "bob"}
    assert catalog["alice"].role == "mentor"
    assert catalog["bob"].activation_profile == "consumer_user"


def test_positive_catalog_error_subclasses_volnix_error() -> None:
    """Error-hierarchy lock: ``CharacterCatalogError`` must inherit
    from ``VolnixError`` so consumers catching the root still catch
    it."""
    assert issubclass(CharacterCatalogError, VolnixError)
