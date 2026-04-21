"""CharacterLoader — YAML → CharacterDefinition catalog
(PMF Plan Phase 4C Step 11).

Reads a directory of ``*.yaml`` / ``*.yml`` files, each defining
one ``CharacterDefinition``. Returns a mapping by ``id``.

The loader is product-agnostic — it performs ONLY YAML parsing
and schema validation. No domain interpretation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from volnix.actors.character import CharacterDefinition
from volnix.core.errors import VolnixError


class CharacterCatalogError(VolnixError):
    """Raised when catalog loading fails — malformed YAML,
    duplicate ids, or schema-invalid entries. Subclasses
    ``VolnixError`` per the error-hierarchy lock.
    """

    pass


class CharacterLoader:
    """Directory-scanning character catalog loader."""

    def load_directory(self, path: str | Path) -> dict[str, CharacterDefinition]:
        """Load every ``*.yaml`` / ``*.yml`` file under ``path``
        into a ``{id: CharacterDefinition}`` mapping.

        Raises:
            CharacterCatalogError: if the path isn't a directory,
                any file fails YAML parse or schema validation,
                or duplicate ids are encountered.
        """
        root = Path(path)
        if not root.exists() or not root.is_dir():
            raise CharacterCatalogError(f"CharacterLoader: {str(root)!r} is not a directory")

        catalog: dict[str, CharacterDefinition] = {}
        for file in sorted(root.iterdir()):
            if file.suffix.lower() not in (".yaml", ".yml"):
                continue
            try:
                with file.open("r", encoding="utf-8") as fh:
                    data: Any = yaml.safe_load(fh)
            except yaml.YAMLError as exc:
                raise CharacterCatalogError(
                    f"CharacterLoader: {file.name}: YAML parse failed: {exc}"
                ) from exc
            if data is None:
                # Empty file — skip silently.
                continue
            if not isinstance(data, dict):
                raise CharacterCatalogError(
                    f"CharacterLoader: {file.name}: top-level must be a mapping, "
                    f"got {type(data).__name__}"
                )
            try:
                char = CharacterDefinition.model_validate(data)
            except ValidationError as exc:
                raise CharacterCatalogError(
                    f"CharacterLoader: {file.name}: schema validation failed: {exc}"
                ) from exc
            if char.id in catalog:
                raise CharacterCatalogError(
                    f"CharacterLoader: duplicate character id {char.id!r} "
                    f"in {file.name} (prior load from a different file)"
                )
            catalog[char.id] = char
        return catalog
