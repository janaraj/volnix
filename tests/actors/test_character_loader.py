"""Phase 4C Step 11 — CharacterDefinition + CharacterLoader tests.

Locks:
- Schema: CharacterDefinition is frozen, id validated (non-empty,
  length cap, no whitespace / path separators / traversal),
  metadata is a free-form bag.
- ``to_actor_spec()`` emits ``personality`` (not ``persona``) so
  ``SimpleActorGenerator`` picks it up (post-impl audit C1).
- Loader: YAML files in a directory become
  ``{id: CharacterDefinition}``.
- Error path: bad YAML, duplicate id, non-dict top-level, missing
  directory, empty-string path, directory-with-.yaml-suffix,
  non-UTF-8 encoding, oversize file, YAML alias amplification all
  raise ``CharacterCatalogError``.
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
    # Post-impl audit C1: persona MUST map to the "personality" key
    # in the emitted spec (that's what SimpleActorGenerator reads).
    assert spec["personality"] == "direct and impatient"
    assert "persona" not in spec
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


# ─── Post-impl audit regression tests ──────────────────────────────


class TestIdValidation:
    """Post-impl audit H6: CharacterDefinition.id rejects
    malformed or dangerous identifiers."""

    def test_negative_empty_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CharacterDefinition(id="")

    def test_negative_whitespace_only_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CharacterDefinition(id="   ")

    def test_negative_id_with_embedded_whitespace_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CharacterDefinition(id="alice bob")

    def test_negative_id_with_path_separator_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CharacterDefinition(id="../../../etc/passwd")

    def test_negative_id_with_newline_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CharacterDefinition(id="alice\nbob")

    def test_negative_excessively_long_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CharacterDefinition(id="x" * 257)

    def test_positive_id_at_length_cap_accepted(self) -> None:
        c = CharacterDefinition(id="x" * 256)
        assert len(c.id) == 256


class TestLoaderHardening:
    """Post-impl audit H1/H3/H4/H5."""

    def test_negative_empty_path_rejected(self) -> None:
        """H1: empty string would scan CWD."""
        with pytest.raises(CharacterCatalogError, match="empty"):
            CharacterLoader().load_directory("")

    def test_negative_non_utf8_file_wrapped_in_catalog_error(self, tmp_path: Path) -> None:
        """H3: decode errors surface as ``CharacterCatalogError``,
        not bare ``UnicodeDecodeError``."""
        (tmp_path / "latin1.yaml").write_bytes(b"name: caf\xe9\nid: cafe\n")
        with pytest.raises(CharacterCatalogError):
            CharacterLoader().load_directory(tmp_path)

    def test_negative_directory_with_yaml_suffix_skipped_not_raised(self, tmp_path: Path) -> None:
        """H4: a directory named ``foo.yaml`` must be skipped
        silently (it's not a file) — no leaked IsADirectoryError."""
        (tmp_path / "subdir.yaml").mkdir()
        _write(tmp_path / "real.yaml", "id: real\nname: x\n")
        catalog = CharacterLoader().load_directory(tmp_path)
        assert set(catalog.keys()) == {"real"}

    def test_negative_yaml_with_alias_rejected(self, tmp_path: Path) -> None:
        """H5: YAML anchors/aliases are rejected — amplification
        guard prevents billion-laughs style attacks."""
        _write(
            tmp_path / "bomb.yaml",
            "id: bomb\nmetadata: &anchor\n  key: value\nname: *anchor\n",
        )
        with pytest.raises(CharacterCatalogError):
            CharacterLoader().load_directory(tmp_path)

    def test_negative_oversize_file_rejected(self, tmp_path: Path) -> None:
        """H5: files larger than 1 MB are rejected pre-parse."""
        # 2 MB file — beyond the 1 MB cap.
        _write(tmp_path / "huge.yaml", "id: huge\nname: " + ("a" * (2 * 1024 * 1024)))
        with pytest.raises(CharacterCatalogError, match="exceeds"):
            CharacterLoader().load_directory(tmp_path)

    def test_positive_duplicate_id_error_names_both_files(self, tmp_path: Path) -> None:
        """L2: duplicate-id error must name BOTH offending files."""
        _write(tmp_path / "a.yaml", "id: same-id\nname: first")
        _write(tmp_path / "b.yaml", "id: same-id\nname: second")
        with pytest.raises(CharacterCatalogError) as exc_info:
            CharacterLoader().load_directory(tmp_path)
        msg = str(exc_info.value)
        assert "a.yaml" in msg
        assert "b.yaml" in msg


class TestUnknownFieldRejection:
    """Post-impl audit M2: unknown fields fail loudly."""

    def test_negative_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CharacterDefinition(id="c-1", nmae="typo-name")  # type: ignore[call-arg]


class TestMetadataDeepCopy:
    """Post-impl audit H2: metadata deep-copied on to_actor_spec."""

    def test_negative_nested_metadata_mutation_does_not_leak(self) -> None:
        """Mutating the emitted dict's nested metadata must NOT
        mutate the source CharacterDefinition."""
        c = CharacterDefinition(id="c-1", metadata={"nested": {"key": "orig"}})
        spec = c.to_actor_spec()
        spec["metadata"]["nested"]["key"] = "HIJACKED"
        assert c.metadata["nested"]["key"] == "orig"


class TestEndToEndWithGenerator:
    """Post-impl audit C1 / M4: end-to-end round-trip proves
    CharacterDefinition.to_actor_spec() actually becomes a working
    ActorDefinition via SimpleActorGenerator."""

    async def test_positive_character_round_trips_to_actor_definition(
        self,
    ) -> None:
        from volnix.actors.simple_generator import SimpleActorGenerator
        from volnix.reality.dimensions import WorldConditions

        c = CharacterDefinition(
            id="alice",
            name="Alice",
            role="interviewer",
            persona="direct and impatient",
            activation_profile="consumer_user",
            metadata={"age": 45},
        )
        spec = c.to_actor_spec()
        spec["count"] = 1  # generator needs explicit count

        gen = SimpleActorGenerator(seed=42)
        actors = await gen.generate_batch(
            actor_specs=[spec],
            conditions=WorldConditions(),
        )
        assert len(actors) == 1
        actor = actors[0]
        # C1: persona must survive the round-trip as personality_hint.
        assert actor.personality_hint == "direct and impatient"
        # C1: activation_profile must thread through, NOT land in
        # metadata as junk.
        assert actor.activation_profile == "consumer_user"
        # C1: role respected.
        assert actor.role == "interviewer"
        # Metadata from character carries through to actor.
        assert actor.metadata.get("age") == 45
