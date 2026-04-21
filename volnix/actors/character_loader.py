"""CharacterLoader — YAML → CharacterDefinition catalog
(PMF Plan Phase 4C Step 11).

Reads a directory of ``*.yaml`` / ``*.yml`` files, each defining
one ``CharacterDefinition``. Returns a mapping by ``id``.

The loader is product-agnostic — it performs ONLY YAML parsing
and schema validation. No domain interpretation.

Post-ship hardening (Opus audit H1/H3/H4/H5):
- Reject empty-string path (would scan CWD).
- Skip directories whose name ends in ``.yaml`` / ``.yml``.
- Wrap ``UnicodeDecodeError`` / ``OSError`` into
  ``CharacterCatalogError`` so the loader's exception contract
  holds under malformed input.
- Use a YAML SafeLoader subclass that REJECTS anchors/aliases
  (billion-laughs amplification protection).
- Cap file size at 1 MB; realistic character YAMLs are a few KB.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from volnix.actors.character import CharacterDefinition
from volnix.core.errors import VolnixError

# Post-impl audit H5 / L4: 1 MB is generous for any realistic
# character YAML. Exceeding this either signals a misplaced binary
# blob or an amplification attack pre-parse.
_MAX_FILE_SIZE_BYTES: int = 1 * 1024 * 1024


class _NoAnchorSafeLoader(yaml.SafeLoader):
    """``SafeLoader`` subclass that rejects YAML anchors / aliases.

    Post-impl audit H5: ``yaml.safe_load`` is safe against Python
    object construction but NOT against alias amplification
    (``metadata: *huge_anchor`` → 28 MB structure from 10 lines).
    Character catalogs have zero legitimate use for anchors; any
    file containing them is either buggy or adversarial.

    Intercepts alias resolution at ``get_single_node`` time by
    overriding the two Composer hooks that handle anchor / alias
    events in the event stream.
    """

    def compose_node(self, parent, index):  # type: ignore[no-untyped-def]
        # AliasEvent surfaces when a ``*anchor`` reference is
        # encountered — reject BEFORE the composer expands it.
        if self.check_event(yaml.AliasEvent):
            event = self.peek_event()
            raise yaml.YAMLError(
                f"YAML alias *{event.anchor} rejected — character "
                f"catalogs do not allow anchor/alias expansion "
                f"(amplification guard)."
            )
        # For non-alias events, peek at the anchor attribute on
        # the forthcoming event and reject if set.
        event = self.peek_event()
        if (
            isinstance(event, (yaml.MappingStartEvent, yaml.SequenceStartEvent, yaml.ScalarEvent))
            and event.anchor is not None
        ):
            raise yaml.YAMLError(
                f"YAML anchor &{event.anchor} rejected — character "
                f"catalogs do not allow anchor definitions "
                f"(amplification guard)."
            )
        return super().compose_node(parent, index)


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
            CharacterCatalogError: on empty path, missing directory,
                oversize file, YAML parse failure (including anchor
                rejection), decode failure, IO failure, non-dict
                top-level, schema validation failure, or duplicate id.
        """
        # Post-impl audit H1: empty string would resolve to CWD.
        if not str(path).strip():
            raise CharacterCatalogError(
                "CharacterLoader: empty path is not a character catalog; "
                "pass the directory explicitly."
            )

        root = Path(path)
        if not root.exists() or not root.is_dir():
            raise CharacterCatalogError(f"CharacterLoader: {str(root)!r} is not a directory")

        catalog: dict[str, CharacterDefinition] = {}
        # Post-impl audit L2: track originating filename so the
        # duplicate-id error names both files.
        id_sources: dict[str, str] = {}

        # Post-impl audit M5: sort by lowercased name so catalog
        # load order is deterministic across platforms. macOS
        # APFS (case-insensitive by default) vs Linux ext4
        # (case-sensitive) would otherwise produce different
        # iteration orders for ``Alice.yaml`` vs ``alice.yaml``.
        # Ties break on the original name preserving stable
        # ordering when two files differ only in case — which
        # on case-insensitive filesystems can't happen anyway.
        for file in sorted(root.iterdir(), key=lambda p: (p.name.lower(), p.name)):
            # Post-impl audit H4: a directory named "alice.yaml"
            # matches the suffix but open() would leak
            # ``IsADirectoryError``. Require a regular file.
            if not file.is_file():
                continue
            if file.suffix.lower() not in (".yaml", ".yml"):
                continue

            # Post-impl audit H5/L4: file-size cap before open.
            try:
                size = file.stat().st_size
            except OSError as exc:
                raise CharacterCatalogError(
                    f"CharacterLoader: {file.name}: stat failed: {exc}"
                ) from exc
            if size > _MAX_FILE_SIZE_BYTES:
                raise CharacterCatalogError(
                    f"CharacterLoader: {file.name}: size {size} bytes "
                    f"exceeds {_MAX_FILE_SIZE_BYTES}-byte cap. Split the "
                    f"catalog or reduce the file."
                )

            try:
                with file.open("r", encoding="utf-8") as fh:
                    data: Any = yaml.load(fh, Loader=_NoAnchorSafeLoader)
            except (yaml.YAMLError, UnicodeDecodeError, OSError) as exc:
                # Post-impl audit H3/H4: broader catch wraps every
                # file-level failure into the documented exception
                # contract.
                raise CharacterCatalogError(
                    f"CharacterLoader: {file.name}: {type(exc).__name__}: {exc}"
                ) from exc

            if data is None:
                # Post-impl audit M1: a 0-byte / comment-only YAML
                # file is almost always an author mistake — log a
                # warning but don't raise, to keep the commented-out
                # drafts use case working.
                import logging

                logging.getLogger(__name__).warning(
                    "CharacterLoader: skipping empty character file %s",
                    file.name,
                )
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
                prior = id_sources.get(char.id, "<unknown>")
                raise CharacterCatalogError(
                    f"CharacterLoader: duplicate character id {char.id!r} "
                    f"in {file.name} (previously loaded from {prior})"
                )
            catalog[char.id] = char
            id_sources[char.id] = file.name

        return catalog
