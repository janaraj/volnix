"""Template loader for reading and writing world definition YAML files.

Provides YAML I/O, schema validation, and ``extends`` resolution for
world definitions that inherit from other templates.
"""

from __future__ import annotations

from volnix.templates.registry import TemplateRegistry


class TemplateLoader:
    """Loads, saves, and validates world definition YAML files."""

    def load_yaml(self, path: str) -> dict:
        """Load a world definition from a YAML file.

        Args:
            path: Filesystem path to the YAML file.

        Returns:
            Parsed world definition dictionary.
        """
        ...

    def save_yaml(self, world_def: dict, path: str) -> None:
        """Save a world definition to a YAML file.

        Args:
            world_def: The world definition to serialise.
            path: Destination filesystem path.
        """
        ...

    def validate_world_def(self, world_def: dict) -> list[str]:
        """Validate a world definition against the expected schema.

        Args:
            world_def: The world definition to validate.

        Returns:
            A list of validation error strings; empty if valid.
        """
        ...

    def resolve_extends(self, world_def: dict, registry: TemplateRegistry) -> dict:
        """Resolve ``extends`` references by merging parent template output.

        Args:
            world_def: World definition that may contain an ``extends`` key.
            registry: Template registry for looking up parent templates.

        Returns:
            Fully resolved world definition with inheritance applied.
        """
        ...
